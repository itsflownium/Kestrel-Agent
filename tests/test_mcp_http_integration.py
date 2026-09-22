"""Exercise the actual MCP SDK over loopback; no external service/model calls."""
import asyncio
import socket

import pytest
import uvicorn
from pydantic import BaseModel
from mcp.server.fastmcp import FastMCP

from kestrel_agent.config import Settings
from kestrel_agent.connections import Connection, ConnectionPool


@pytest.mark.asyncio
async def test_real_http_catalog_call_and_persistent_session_cleanup():
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    listener.listen()
    server_app = FastMCP('Kestrel fixture', host='127.0.0.1', port=port, json_response=True)
    calls = []
    class CountResult(BaseModel):
        total: int
    @server_app.tool()
    def count(n: int) -> CountResult:
        calls.append(n)
        return CountResult(total=n + 1)
    server = uvicorn.Server(uvicorn.Config(server_app.streamable_http_app(), host='127.0.0.1', port=port, log_level='error'))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    pool = ConnectionPool(Settings(provider='openai-compatible', mcp_connections={'fixture': Connection(url=f'http://127.0.0.1:{port}/mcp')}))
    try:
        async with asyncio.timeout(5):
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(.01)
        catalog = await pool.catalog()
        assert catalog[0]['name'] == 'direct:fixture'
        assert [tool['name'] for tool in catalog[0]['tools']] == ['count']
        worker = pool.workers['fixture']
        result = await pool.call('fixture', 'count', {'n': 4})
        assert result['structuredContent'] == {'total': 5}
        assert calls == [4]
        assert pool.workers['fixture'] is worker
        await pool.close()
        assert worker.done() and not pool.workers
    finally:
        await pool.close()
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        listener.close()
