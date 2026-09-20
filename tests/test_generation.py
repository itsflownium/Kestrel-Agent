import json
import stat
from unittest.mock import AsyncMock

import httpx
import pytest

from kestrel_agent.config import Settings
from kestrel_agent.generation import HTTPGenerator, endpoint, save_key, api_key
from kestrel_agent.providers import Runtime


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'private'))
    monkeypatch.setenv('KESTREL_MODEL_API_KEY', 'test-provider-key')
    return tmp_path


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['prompt', 'json_object', 'json_schema'])
async def test_compatible_request_and_usage(setup, mode):
    def handler(request):
        assert request.url == 'https://example.test/v1/chat/completions'
        assert request.headers['authorization'] == 'Bearer test-provider-key'
        body = json.loads(request.content)
        assert body['model'] == 'arbitrary-model'
        assert 'tools' not in body
        assert ('response_format' in body) == (mode != 'prompt')
        return httpx.Response(200, json={'choices':[{'finish_reason':'stop','message':{'content':'```json\n{"ok":true}\n```'}}], 'usage':{'prompt_tokens':11,'completion_tokens':4}})
    settings=Settings(provider='openai-compatible', provider_base_url='https://example.test/v1', model='arbitrary-model', provider_json_mode=mode)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result=await HTTPGenerator(settings,client).complete('A request', {'type':'object','properties':{'ok':{'type':'boolean'}}})
    assert result == ('{"ok":true}',11,4)


@pytest.mark.asyncio
async def test_anthropic_messages(setup):
    def handler(request):
        assert request.url.path == '/v1/messages'
        assert request.headers['x-api-key'] == 'test-provider-key'
        assert request.headers['anthropic-version'] == '2023-06-01'
        body=json.loads(request.content)
        assert isinstance(body['system'],str)
        assert body['messages'][0]['role']=='user'
        return httpx.Response(200,json={'stop_reason':'end_turn','content':[{'type':'text','text':'hello'}],'usage':{'input_tokens':8,'output_tokens':2}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await HTTPGenerator(Settings(provider='anthropic',model='user-chosen-model'),client).complete('Hi') == ('hello',8,2)


@pytest.mark.asyncio
async def test_http_generation_does_not_start_codex(setup):
    runtime=Runtime(Settings(provider='openai-compatible',model='custom-model'),setup,lambda *args:None)
    runtime.start=AsyncMock(side_effect=AssertionError('Codex must not start for HTTP generation'))
    runtime.generator.complete=AsyncMock(return_value=('answer',10,3))
    try:
        assert await runtime.complete('request')=='answer'
        assert runtime.model_calls==1 and runtime.input_tokens==10
        assert await runtime.mcp_catalog()==[]
        with pytest.raises(ValueError,match='research'):
            await runtime.complete('Search',research=True)
    finally:
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('reason',['length','tool_calls','content_filter'])
async def test_incomplete_outputs_rejected(setup,reason):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'choices':[{'finish_reason':reason,'message':{'content':'partial'}}]}))) as client:
        with pytest.raises(RuntimeError,match='did not finish'):
            await HTTPGenerator(Settings(provider='openai-compatible',model='x'),client).complete('request')


def test_credentials_scoped_and_private(setup,monkeypatch):
    monkeypatch.delenv('KESTREL_MODEL_API_KEY')
    first=Settings(provider='openai-compatible',provider_base_url='https://first.test/v1')
    second=Settings(provider='openai-compatible',provider_base_url='https://second.test/v1')
    save_key(first,'private-key')
    assert api_key(first)=='private-key' and api_key(second)==''
    assert stat.S_IMODE((setup/'private/providers.json').stat().st_mode)==0o600


@pytest.mark.parametrize('url',['http://remote.test/v1','https://secret@remote.test/v1','https://remote.test/v1?key=secret'])
def test_unsafe_endpoints_rejected(url):
    with pytest.raises(ValueError): endpoint(Settings(provider_base_url=url))


@pytest.mark.asyncio
async def test_error_does_not_echo_server_secret(setup):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(401,text='test-provider-key'))) as client:
        with pytest.raises(RuntimeError) as error:
            await HTTPGenerator(Settings(provider='openai-compatible',model='x'),client).complete('request')
    assert 'test-provider-key' not in str(error.value)


@pytest.mark.asyncio
async def test_engine_uses_http_provider_for_validated_plan(setup):
    from kestrel_agent.engine import Engine
    from kestrel_agent.store import Store
    settings=Settings(provider='openai-compatible', model='custom-model')
    store=Store(settings)
    engine=Engine(settings,setup,store,store.create(setup),lambda *args:None,AsyncMock(return_value=False))
    engine.judge.decide=AsyncMock(return_value={'route':{'choice':'model'}})
    engine.runtime.generator.complete=AsyncMock(return_value=(json.dumps({'mode':'answer','message':'Provider worked','actions':[],'success_criteria':[]}),20,10))
    try:
        assert await engine.run('Explain a concept')=='Provider worked'
        assert not engine.runtime.started
        assert engine.state['usage']['provider']=='openai-compatible'
        assert engine.state['usage']['generation_calls']==1
        assert 'codex_calls' not in engine.state['usage']
    finally:
        await engine.close()
        store.close()
