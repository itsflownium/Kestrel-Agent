import base64
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image
from kestrel_agent.vision import validate_image, ImageCache, MAX_BYTES
from kestrel_agent.config import Settings
from kestrel_agent.generation import HTTPGenerator


def png(color='red'):
    stream=io.BytesIO()
    Image.new('RGB',(20,10),color).save(stream,format='PNG')
    return stream.getvalue()


def test_image_validation_and_cache_bounds():
    image=validate_image(png())
    assert (image.width,image.height,image.mime)==(20,10,'image/png')
    assert image.encoded not in repr(image)
    for data,mime in [(b'not an image',None),(b'x'*(MAX_BYTES+1),None),(png(),'image/jpeg')]:
        with pytest.raises(ValueError): validate_image(data,mime)
    cache=ImageCache(); first=None
    for index in range(10):
        result=cache.ingest({'content':[{'type':'image','mimeType':'image/png','data':base64.b64encode(png((index,0,0))).decode()}]})
        block=result['content'][0]
        assert 'data' not in block
        first=first or block['image_id']
        assert cache.get(block['image_id']).sha256==block['sha256']
    assert len(cache.entries)==8
    with pytest.raises(ValueError,match='expired'): cache.get(first)
    bad=cache.ingest({'content':[{'type':'image','mimeType':'image/png','data':'invalid'}]})
    assert 'unavailable_to_model' in bad['content'][0] and 'data' not in bad['content'][0]


def test_connector_image_aliases_are_locally_validated_and_unambiguous():
    def block(color):
        return {'type': 'image', 'mimeType': 'image/png', 'data': base64.b64encode(png(color)).decode()}
    cache = ImageCache()
    single = cache.ingest({'content': [{'type': 'text', 'text': 'Viewport'}, block('red')]})
    assert single['image_id'] == single['image_refs'][0]['image_id']
    assert single['image_refs'][0]['content_index'] == 1
    assert cache.get(single['image_id']).data == png('red')
    multiple = cache.ingest({'content': [block('red'), block('blue')], 'image_id': 'remote-guess'})
    assert 'image_id' not in multiple
    assert [cache.get(ref['image_id']).data for ref in multiple['image_refs']] == [png('red'), png('blue')]
    assert multiple['images_may_be_truncated'] is False
    invalid = cache.ingest({'image_id': single['image_id'], 'image_refs': single['image_refs'], 'content': [
        {'type': 'image', 'mimeType': 'image/png', 'data': 'invalid', 'image_id': single['image_id'], 'width': 20}]})
    assert 'image_id' not in invalid and invalid['image_refs'] == []
    assert 'image_id' not in invalid['content'][0] and 'width' not in invalid['content'][0]
    assert invalid['images_may_be_truncated'] is True
    oversized_batch = cache.ingest({'content': [block((i, 0, 0)) for i in range(10)]})
    assert len(oversized_batch['image_refs']) == 8
    assert oversized_batch['images_may_be_truncated'] is True
    assert 'image_id' not in oversized_batch['content'][0]
    assert all(cache.get(ref['image_id']) for ref in oversized_batch['image_refs'])


@pytest.mark.asyncio
@pytest.mark.parametrize('provider',['openai-compatible','anthropic'])
async def test_http_transmits_pixels_in_correct_protocol(provider,tmp_path,monkeypatch):
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    monkeypatch.setenv('KESTREL_MODEL_API_KEY','dummy')
    image=validate_image(png())
    def handler(request):
        body=json.loads(request.content)
        content=body['messages'][-1]['content']
        if provider=='anthropic':
            assert content[0]['source']=={'type':'base64','media_type':'image/png','data':image.encoded}
            return httpx.Response(200,json={'stop_reason':'end_turn','content':[{'type':'text','text':'red'}]})
        assert content[0]['image_url']['url']==image.url
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'red'}}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result=await HTTPGenerator(Settings(provider=provider,model='vision-model'),client).complete('Color?',images=[image])
    assert result[0]=='red'


@pytest.mark.asyncio
async def test_inspection_uses_pixels_respects_paths_and_labels_interpretation(tmp_path,monkeypatch):
    from kestrel_agent.tools import ToolExecutor
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    workspace=tmp_path/'workspace'; workspace.mkdir()
    (workspace/'image.png').write_bytes(png())
    runtime=SimpleNamespace(complete=AsyncMock(return_value='Red rectangle'))
    tool=ToolExecutor(Settings(),workspace,runtime,None,None,'test',AsyncMock())
    result=await tool.execute('inspect_image',{'source':'image.png','question':'What color?'})
    assert result['evidence_kind']=='model_image_interpretation'
    assert result['sha256']==runtime.complete.call_args.kwargs['images'][0].sha256
    assert 'data' not in result
    (tmp_path/'outside.png').write_bytes(png())
    with pytest.raises(PermissionError):
        await tool.execute('inspect_image',{'source':'../outside.png','question':'Read'})
    assert runtime.complete.await_count==1


@pytest.mark.asyncio
async def test_codex_sends_image_input_and_does_not_reuse_image_context(tmp_path):
    from openai_codex import ImageInput, TextInput
    from kestrel_agent.providers import Runtime
    async def events():
        yield SimpleNamespace(method='item/completed',payload=SimpleNamespace(item=SimpleNamespace(type='agentMessage',text='red',phase='final_answer')))
        yield SimpleNamespace(method='turn/completed',payload=SimpleNamespace(turn=SimpleNamespace(status='completed')))
    handle=SimpleNamespace(stream=events,interrupt=AsyncMock())
    thread=SimpleNamespace(turn=AsyncMock(return_value=handle))
    runtime=Runtime(Settings(generation_session='task'),tmp_path,lambda *_:None)
    runtime.start=AsyncMock()
    runtime.account=AsyncMock(return_value={'account':{'id':'dummy'}})
    runtime.rpc=AsyncMock(return_value={'config':{}})
    runtime.codex.thread_start=AsyncMock(return_value=thread)
    try:
        await runtime.complete('Color?',images=[validate_image(png())])
        inputs=thread.turn.call_args.args[0]
        assert isinstance(inputs[0],TextInput) and isinstance(inputs[1],ImageInput)
        assert inputs[1].url.startswith('data:image/png;base64,')
        await runtime.complete('Text only')
        assert runtime.codex.thread_start.await_count==2
        assert thread.turn.call_args.args[0]=='Text only'
    finally:
        await runtime.close()
