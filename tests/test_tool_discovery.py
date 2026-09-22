import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from kestrel_agent.config import Settings
from kestrel_agent.tool_discovery import discover, encoded, entries, inspect, preview
from kestrel_agent.tools import ToolExecutor


def catalog(count=100):
    return [{'name': 'direct:many', 'tools': [
        {'name': f'tool_{i:03}', 'description': f'Operation {i} for reports and analysis.',
         'inputSchema': {'type':'object', 'properties':{f'field_{j}':{'type':'string'} for j in range(10)}, 'additionalProperties':False},
         'outputSchema': {'type':'object', 'properties':{'receipt':{'type':'string'}}}}
        for i in range(count)]}]


def test_preview_is_bounded_valid_json_and_late_tool_is_discoverable():
    tools=catalog()
    before=json.dumps(tools)
    assert len(before)>12000
    result=preview(tools)
    assert len(encoded(result))<=12000
    assert json.loads(encoded(result))==result
    assert result['omitted_tools']>0
    found=discover(tools,query='tool_099')
    assert found['total_matches']==1
    assert found['tools'][0]['tool']=='tool_099'
    definition=inspect(tools,'direct:many','tool_099')
    assert definition['complete']
    assert definition['definition']['inputSchema']==tools[0]['tools'][-1]['inputSchema']
    assert definition['definition']['outputSchema']==tools[0]['tools'][-1]['outputSchema']
    assert json.dumps(tools)==before


def test_search_paginates_without_duplicates_and_uses_full_description():
    tools=catalog(35)
    tools[0]['tools'][-1]['description']='x'*500+' specialneedle'
    names=[];offset=0
    while True:
        page=discover(tools,server='direct:many',offset=offset,limit=7)
        names.extend(item['tool'] for item in page['tools'])
        if page['next_offset'] is None: break
        offset=page['next_offset']
    assert names==[f'tool_{i:03}' for i in range(35)]
    found=discover(tools,query='SPECIALNEEDLE')
    assert found['tools'][0]['tool']=='tool_034'
    assert found['tools'][0]['description_truncated']
    assert discover(tools,server='other')['total_matches']==0
    assert discover(tools,query='tool_001 nonexistent')['total_matches']==0


def test_native_map_keys_are_dispatch_names_and_servers_are_separate():
    tools=[{'name':'native','tools':{'dispatch_name':{'name':'display_name','inputSchema':{'type':'object'}}}},
           {'name':'direct:other','tools':[{'name':'dispatch_name','inputSchema':{'type':'object'}}]}]
    assert {item['server'] for item in discover(tools)['tools']}=={'native','direct:other'}
    assert inspect(tools,'native','dispatch_name')['definition']['name']=='dispatch_name'
    with pytest.raises(ValueError,match='not in'):
        inspect(tools,'native','display_name')
    with pytest.raises(ValueError,match='duplicate'):
        entries(tools+[tools[0]])


def test_large_schema_chunks_reassemble_exactly_and_detect_changed_snapshot():
    tools=catalog(2)
    tools[0]['tools'][0]['description']='界'*30000
    summary=preview(tools)
    assert summary['tools'][0]['definition_complete'] is False
    assert summary['tools'][1]['definition_complete'] is True
    first=inspect(tools,'direct:many','tool_000',max_chars=7000)
    assert not first['complete'] and 'definition' not in first
    content=first['content'];offset=first['next_offset']
    while offset is not None:
        chunk=inspect(tools,'direct:many','tool_000',offset=offset,max_chars=7000,expected_sha256=first['definition_sha256'])
        content+=chunk['content'];offset=chunk['next_offset']
    assert json.loads(content)==tools[0]['tools'][0]
    with pytest.raises(ValueError,match='requires'):
        inspect(tools,'direct:many','tool_000',offset=7000)
    tools[0]['tools'][0]['inputSchema']={'type':'string'}
    with pytest.raises(ValueError,match='changed'):
        inspect(tools,'direct:many','tool_000',offset=7000,expected_sha256=first['definition_sha256'])


def test_discovery_errors_are_visible_but_not_fake_tools():
    result=preview([{'name':'direct:unavailable','tools':[], 'error':'ConnectionError'}])
    assert result['total_tools']==0
    assert result['discovery_errors']==[{'server':'direct:unavailable','error':'ConnectionError'}]


@pytest.mark.asyncio
async def test_discovery_dispatch_is_read_only_cached_and_permissioned(tmp_path,monkeypatch):
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    runtime=SimpleNamespace(mcp_catalog=AsyncMock(return_value=catalog()),mcp_call=AsyncMock())
    confirm=AsyncMock()
    tool=ToolExecutor(Settings(permission='read-only'),tmp_path,runtime,None,None,'test',confirm)
    result=await tool.execute('discover_tools',{'query':'tool_099'})
    assert result['tools'][0]['tool']=='tool_099'
    definition=await tool.execute('inspect_tool',{'server':'direct:many','tool':'tool_099'})
    assert definition['complete']
    runtime.mcp_catalog.assert_awaited_once()
    runtime.mcp_call.assert_not_awaited();confirm.assert_not_awaited()
    with pytest.raises(PermissionError,match='MCP actions'):
        await tool.execute('mcp',{'server':'direct:many','tool':'tool_099'})
    tool.settings.network=False
    with pytest.raises(PermissionError,match='network'):
        await tool.execute('discover_tools',{})
    runtime.mcp_catalog.assert_awaited_once()


@pytest.mark.asyncio
async def test_planner_uses_valid_catalog_preview_and_shares_snapshot(tmp_path,monkeypatch):
    from kestrel_agent.engine import Engine
    from kestrel_agent.store import Store
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    store=Store(Settings());sid=store.create(tmp_path)
    engine=Engine(Settings(),tmp_path,store,sid,lambda *_:None,AsyncMock())
    engine.state['request']='What tools are available?'
    engine.runtime.mcp_catalog=AsyncMock(return_value=catalog())
    engine.runtime.complete=AsyncMock(return_value=json.dumps({'mode':'answer','message':'Available tools','actions':[],'success_criteria':[]}))
    try:
        await engine.make_plan()
        prompt=engine.runtime.complete.call_args.args[0]
        line=next(line for line in prompt.splitlines() if line.startswith('CONNECTED TOOLS'))
        payload=json.loads(line.partition(': ')[2])
        assert payload['total_tools']==100 and payload['omitted_tools']>0
        found=await engine.tools.execute('discover_tools',{'query':'tool_099'})
        assert found['tools'][0]['tool']=='tool_099'
        engine.runtime.mcp_catalog.assert_awaited_once()
    finally:
        await engine.close();store.close()
