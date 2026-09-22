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
async def test_real_http_catalog_call_and_persistent_session_cleanup(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from kestrel_agent.schema import bind
    from kestrel_agent.tools import ToolExecutor
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'state'))
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
    @server_app.tool()
    def picture():
        import io
        from PIL import Image as Raster
        from mcp.server.fastmcp import Image
        buffer = io.BytesIO()
        Raster.new('RGB', (20, 10), 'blue').save(buffer, format='PNG')
        return Image(data=buffer.getvalue(), format='png')
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
        assert [tool['name'] for tool in catalog[0]['tools']] == ['count', 'picture']
        worker = pool.workers['fixture']
        result = await pool.call('fixture', 'count', {'n': 4})
        assert result['structuredContent'] == {'total': 5}
        assert calls == [4]
        assert pool.workers['fixture'] is worker
        picture = await pool.call('fixture', 'picture', {})
        block = next(block for block in picture['content'] if block['type'] == 'image')
        assert 'data' not in block and pool.images.get(block['image_id']).width == 20
        assert picture['image_id'] == block['image_id']
        runtime = SimpleNamespace(connections=pool, complete=AsyncMock(return_value='A blue rectangle.'))
        tool = ToolExecutor(Settings(), tmp_path, runtime, None, None, 'fixture', AsyncMock())
        arguments = bind({'source': '${shot.image_id}', 'question': 'What is visible?'}, {'shot': picture})
        inspection = await tool.execute('inspect_image', arguments)
        sent = runtime.complete.call_args.kwargs['images'][0]
        assert sent.data == pool.images.get(picture['image_id']).data
        assert inspection['sha256'] == sent.sha256
        assert inspection['evidence_kind'] == 'model_image_interpretation'
        await pool.close()
        assert not pool.images.entries
        assert worker.done() and not pool.workers
    finally:
        await pool.close()
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        listener.close()


@pytest.mark.asyncio
async def test_engine_refreshes_configured_observation_over_real_mcp(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock
    from kestrel_agent.engine import Engine
    from kestrel_agent.schema import Action
    from kestrel_agent.store import Store
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'state'))
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    listener.listen()
    app = FastMCP('Observation fixture', host='127.0.0.1', port=port, json_response=True)
    current = {'value': 'before'}
    class Observation(BaseModel):
        value: str
    @app.tool()
    def observe() -> Observation:
        return Observation(value=current['value'])
    server = uvicorn.Server(uvicorn.Config(app.streamable_http_app(), log_level='error'))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    config = Settings(agent_mode='standard', provider='openai-compatible', mcp_connections={
        'fixture': Connection(url=f'http://127.0.0.1:{port}/mcp', read_only_tools=['observe'])})
    store = Store(config)
    confirm = AsyncMock(return_value=True)
    engine = Engine(config, tmp_path, store, store.create(tmp_path), lambda *args: None, confirm)
    engine.state.update(results={}, statuses={})
    try:
        async with asyncio.timeout(5):
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(.01)
        for name, value in [('first', 'before'), ('second', 'after')]:
            current['value'] = value
            await engine.perform(Action(id=name, tool='mcp',
                arguments_json='{"server":"direct:fixture","tool":"observe","arguments":{}}',
                depends_on=[], purpose='Read current state', condition='always'))
            assert engine.state['statuses'][name] == 'completed'
            assert engine.state['results'][name]['structuredContent']['value'] == value
        assert confirm.await_count == 2
        assert engine.state['completed_effects'] == []
    finally:
        await engine.close()
        store.close()
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        listener.close()


@pytest.mark.asyncio
async def test_search_and_inspect_late_tool_then_permissioned_call_over_mcp(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock
    from kestrel_agent.engine import Engine
    from kestrel_agent.schema import Action
    from kestrel_agent.store import Store
    from kestrel_agent.tool_discovery import preview
    import json
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'state'))
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen()
    port=listener.getsockname()[1]
    app=FastMCP('Large catalog fixture', host='127.0.0.1', port=port, json_response=True)
    calls=[]
    for index in range(100):
        def distractor() -> str:
            raise AssertionError('Discovery must not invoke tools.')
        app.add_tool(distractor, name=f'a_report_{index:03}', description='Unrelated reporting operation. '*30)
    class RecordResult(BaseModel):
        record_id: str
        status: str
    @app.tool(description='Find a record by its exact identifier. '*30)
    def z_find_record(record_id: str) -> RecordResult:
        calls.append(record_id)
        return RecordResult(record_id=record_id, status='ready')
    server=uvicorn.Server(uvicorn.Config(app.streamable_http_app(),log_level='error'))
    task=asyncio.create_task(server.serve(sockets=[listener]))
    config=Settings(agent_mode='standard',provider='openai-compatible',mcp_connections={
        'fixture':Connection(url=f'http://127.0.0.1:{port}/mcp')})
    store=Store(config);confirm=AsyncMock(return_value=True)
    engine=Engine(config,tmp_path,store,store.create(tmp_path),lambda *_:None,confirm)
    engine.state.update(results={},statuses={})
    try:
        async with asyncio.timeout(5):
            while not server.started:
                if task.done(): await task
                await asyncio.sleep(.01)
        tools=await engine.runtime.mcp_catalog()
        assert preview(tools)['omitted_tools']>0
        assert not any(item['tool']=='z_find_record' for item in preview(tools)['tools'])
        for name,tool,args in [
            ('search','discover_tools',{'query':'find_record'}),
            ('schema','inspect_tool',{'server':'direct:fixture','tool':'z_find_record'}),
            ('execute','mcp',{'server':'direct:fixture','tool':'z_find_record','arguments':{'record_id':'record-123'}}),
        ]:
            await engine.perform(Action(id=name,tool=tool,arguments_json=json.dumps(args),depends_on=[],purpose='Find the requested record',condition='always'))
            assert engine.state['statuses'][name]=='completed'
        assert engine.state['results']['search']['tools'][0]['tool']=='z_find_record'
        definition=engine.state['results']['schema']['definition']
        assert definition['inputSchema']['properties']['record_id']['type']=='string'
        assert engine.state['results']['execute']['structuredContent']['status']=='ready'
        assert calls==['record-123']
        assert confirm.await_count==1
    finally:
        await engine.close();store.close();server.should_exit=True
        await asyncio.wait_for(task,5);listener.close()
