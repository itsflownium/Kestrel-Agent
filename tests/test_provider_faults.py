"""Fault contract checks for both HTTP protocols; no live-provider claims."""
import httpx
import pytest
from kestrel_agent.config import Settings
from kestrel_agent.generation import HTTPGenerator


@pytest.fixture
def config(tmp_path,monkeypatch):
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    monkeypatch.setenv('KESTREL_MODEL_API_KEY','test-private-key')
    return Settings(provider='openai-compatible',model='chosen-model',provider_base_url='https://fixture.test/v1')


@pytest.mark.asyncio
@pytest.mark.parametrize('payload', [
    [], {'choices':[None]}, {'choices':'not-a-list'},
    {'choices':[{'finish_reason':'stop','message':None}]},
    {'choices':[{'finish_reason':'stop','message':{'content':'looks valid','refusal':'refused'}}]},
    {'choices':[{'finish_reason':'stop','message':{'content':'looks valid','tool_calls':[{'id':'1'}]}}]},
    {'choices':[{'finish_reason':'stop','message':{'content':'looks valid','function_call':{'name':'external'}}}]},
])
async def test_malformed_or_non_answer_responses_fail(config,payload):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=payload))) as client:
        with pytest.raises(RuntimeError): await HTTPGenerator(config,client).complete('request')


@pytest.mark.asyncio
@pytest.mark.parametrize('content', [None,[None],[{'type':'text','text':7}],
    [{'type':'text','text':'looks valid'},{'type':'tool_use','name':'external'}],
    [{'type':'refusal'},{'type':'text','text':'looks valid'}]])
async def test_anthropic_invalid_content_fails(config,content):
    config.provider='anthropic'
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'stop_reason':'end_turn','content':content}))) as client:
        with pytest.raises(RuntimeError): await HTTPGenerator(config,client).complete('request')


@pytest.mark.asyncio
@pytest.mark.parametrize('usage',[[],{'prompt_tokens':-1},{'prompt_tokens':True},{'completion_tokens':'12'},{'completion_tokens':None}])
async def test_invalid_usage_is_not_reported_as_real_tokens(config,usage):
    payload={'choices':[{'finish_reason':'stop','message':{'content':'answer'}}],'usage':usage}
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=payload))) as client:
        with pytest.raises(RuntimeError,match='usage'): await HTTPGenerator(config,client).complete('request')


@pytest.mark.asyncio
async def test_redirect_is_not_followed_even_with_redirecting_client(config):
    requests=[]
    def handler(request):
        requests.append(request)
        return httpx.Response(307,headers={'location':'https://other.test/collect'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler),follow_redirects=True) as client:
        with pytest.raises(RuntimeError,match='HTTP 307'): await HTTPGenerator(config,client).complete('private prompt')
    assert len(requests)==1
    assert requests[0].url.host=='fixture.test'


@pytest.mark.asyncio
async def test_invalid_json_error_does_not_include_body(config):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,text='private-provider-body'))) as client:
        with pytest.raises(RuntimeError) as caught: await HTTPGenerator(config,client).complete('request')
    assert 'private-provider-body' not in str(caught.value)
