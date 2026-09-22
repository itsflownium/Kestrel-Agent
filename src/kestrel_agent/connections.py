"""User-configured Streamable HTTP MCP connections for every model provider."""
from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Connection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    url: str
    bearer_env: str | None = Field(default=None, pattern=r'^[A-Za-z_][A-Za-z0-9_]*$')
    enabled: bool = True
    read_only_tools: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def valid_url(self):
        if len(set(self.read_only_tools)) != len(self.read_only_tools) or any(
            not name or name != name.strip() or len(name) > 128 for name in self.read_only_tools
        ):
            raise ValueError('Read-only tool names must be unique, nonempty exact names of up to 128 characters.')
        parsed = urlsplit(self.url)
        if not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.query:
            raise ValueError('Use an MCP endpoint without embedded credentials, query, or fragment.')
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1', '::1'}):
            raise ValueError('MCP requires HTTPS, except localhost HTTP servers.')
        return self


def is_observation(settings, arguments):
    """Only explicit local configuration can classify a remote call as a read.

    This controls replay accounting, never permission checks or auto-approval.
    Remote catalog annotations and tool names alone are not trusted declarations.
    """
    server, tool = arguments.get('server'), arguments.get('tool')
    if not isinstance(server, str) or not server.startswith('direct:'):
        return False
    connection = settings.mcp_connections.get(server[len('direct:'):])
    return bool(connection and connection.enabled and tool in connection.read_only_tools)


class ConnectionPool:
    """Each worker owns its SDK context in one task, including shutdown."""
    def __init__(self, settings):
        self.settings = settings
        self.workers = {}
        self.queues = {}
        self.schemas = {}
        from .vision import ImageCache
        self.images = ImageCache()

    async def _worker(self, name, queue):
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        import httpx
        config = self.settings.mcp_connections[name]
        pending = None
        try:
            headers = {}
            if config.bearer_env:
                token = os.environ.get(config.bearer_env)
                if not token:
                    raise ValueError(f'Missing MCP credential environment variable: {config.bearer_env}')
                headers['Authorization'] = 'Bearer ' + token
            async with AsyncExitStack() as stack:
                client = await stack.enter_async_context(httpx.AsyncClient(headers=headers, timeout=30, follow_redirects=False, trust_env=False))
                read, write, _ = await stack.enter_async_context(streamable_http_client(config.url, http_client=client))
                session = await stack.enter_async_context(ClientSession(read, write))
                await asyncio.wait_for(session.initialize(), 30)
                while True:
                    item = await queue.get()
                    if item is None:
                        break
                    operation, arguments, pending = item
                    if pending.cancelled():
                        pending = None
                        continue
                    try:
                        if operation == 'list':
                            entries, cursor = [], None
                            for _ in range(20):
                                page = await asyncio.wait_for(session.list_tools(cursor=cursor), 30)
                                entries.extend(t.model_dump(mode='json', by_alias=True) for t in page.tools)
                                cursor = page.nextCursor
                                if not cursor:
                                    break
                            else:
                                raise ValueError('MCP catalog pagination exceeds 20 pages.')
                            result = entries
                        else:
                            response = await asyncio.wait_for(session.call_tool(arguments[0], arguments=arguments[1]), self.settings.command_timeout_seconds)
                            result = response.model_dump(mode='json', by_alias=True)
                            result = self.images.ingest(result)
                        if not pending.done():
                            pending.set_result(result)
                    except Exception as error:
                        if not pending.done():
                            pending.set_exception(error)
                    finally:
                        pending = None
        except BaseException as error:
            if pending is not None and not pending.done():
                pending.set_exception(RuntimeError('MCP connection interrupted; action outcome may be unknown.'))
            while not queue.empty():
                item = queue.get_nowait()
                if item and not item[2].done():
                    item[2].set_exception(RuntimeError(f'MCP connection unavailable: {type(error).__name__}'))
            if isinstance(error, asyncio.CancelledError):
                raise

    async def request(self, name, operation, arguments=None):
        if not self.settings.network:
            raise PermissionError('Connected tools require network access.')
        config = self.settings.mcp_connections.get(name)
        if not config or not config.enabled:
            raise ValueError('Unknown or disabled MCP connection.')
        task = self.workers.get(name)
        if task is None or task.done():
            queue = self.queues[name] = asyncio.Queue()
            self.workers[name] = asyncio.create_task(self._worker(name, queue))
        future = asyncio.get_running_loop().create_future()
        await self.queues[name].put((operation, arguments, future))
        try:
            return await asyncio.wait_for(future, self.settings.command_timeout_seconds + 60)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            # Never replay a dispatched external action after cancellation or timeout.
            self.workers[name].cancel()
            await asyncio.gather(self.workers[name], return_exceptions=True)
            raise

    async def catalog(self):
        entries = []
        if not self.settings.network:
            return entries
        for name, config in self.settings.mcp_connections.items():
            if not config.enabled:
                continue
            try:
                tools = await self.request(name, 'list')
                self.schemas[name] = {t['name']: t.get('inputSchema', {}) for t in tools}
                entries.append({'name': 'direct:' + name, 'tools': tools})
            except Exception as error:
                entries.append({'name': 'direct:' + name, 'tools': [], 'error': type(error).__name__})
        return entries

    async def call(self, name, tool, arguments):
        if name not in self.schemas:
            await self.catalog()
        schema = self.schemas.get(name, {}).get(tool)
        if schema is None:
            raise ValueError('Tool is not in the connected server catalog.')
        from jsonschema.validators import validator_for
        from referencing import Registry
        from referencing.exceptions import NoSuchResource
        def no_remote_schema(uri):
            raise NoSuchResource(ref=uri)
        validator = validator_for(schema)
        validator.check_schema(schema)
        validator(schema, registry=Registry(retrieve=no_remote_schema)).validate(arguments)
        return await self.request(name, 'call', (tool, arguments))

    async def close(self):
        for name, worker in list(self.workers.items()):
            if not worker.done():
                await self.queues[name].put(None)
        if self.workers:
            try:
                await asyncio.wait_for(asyncio.gather(*self.workers.values(), return_exceptions=True), 10)
            except asyncio.TimeoutError:
                for worker in self.workers.values():
                    worker.cancel()
                await asyncio.gather(*self.workers.values(), return_exceptions=True)
        self.workers.clear()
        self.queues.clear()
        self.schemas.clear()
        self.images.entries.clear()
