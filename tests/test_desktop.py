import asyncio
import threading
import pytest
from kestrel_agent.desktop import DesktopAdapter, create_desktop_server


class Backend:
    bundle_id='org.example.fixture'
    def __init__(self):
        self.pid=12
        self.info={'pid':12,'role':'AXButton','subrole':'','label':'Save','value':'',
                   'enabled':True,'secure':False,'pressable':True,'settable':True}
        self.calls=[]
    def scan(self): return self.pid, [('button',self.info.copy())],False
    def press(self,element): self.calls.append(('press',element)); self.info['label']='Saved'
    def fill(self,element,value): self.calls.append(('fill',value)); self.info['value']=value


@pytest.mark.asyncio
async def test_native_action_requires_current_observed_target_and_reobserves():
    backend=Backend(); adapter=DesktopAdapter(backend)
    state=await adapter.observe()
    result=await adapter.act(state['observation'],'e1','press')
    assert result['targets'][0]['label']=='Saved'
    with pytest.raises(ValueError,match='Stale'): await adapter.act(state['observation'],'e1','press')
    assert backend.calls==[('press','button')]
    state=await adapter.observe(); backend.info['label']='Delete'
    with pytest.raises(ValueError,match='changed'): await adapter.act(state['observation'],'e1','press')
    assert len(backend.calls)==1


@pytest.mark.asyncio
@pytest.mark.parametrize('change',[{'enabled':False},{'secure':True},{'pressable':False}])
async def test_unavailable_targets_do_not_dispatch(change):
    backend=Backend(); backend.info.update(change)
    adapter=DesktopAdapter(backend); state=await adapter.observe()
    with pytest.raises((ValueError,PermissionError)):
        await adapter.act(state['observation'],'e1','press')
    assert not backend.calls


@pytest.mark.asyncio
async def test_process_restart_and_unknown_effect_cannot_replay():
    backend=Backend(); adapter=DesktopAdapter(backend); state=await adapter.observe()
    backend.pid=13
    with pytest.raises(ValueError,match='changed'): await adapter.act(state['observation'],'e1','press')
    backend.pid=12
    def failure(element): raise RuntimeError('uncertain outcome')
    backend.press=failure
    with pytest.raises(RuntimeError): await adapter.act(state['observation'],'e1','press')
    with pytest.raises(ValueError,match='Stale'): await adapter.act(state['observation'],'e1','press')


@pytest.mark.asyncio
async def test_cancelled_request_keeps_os_action_serialized():
    backend=Backend(); adapter=DesktopAdapter(backend); state=await adapter.observe()
    entered,release=threading.Event(),threading.Event()
    def slow(element):
        entered.set(); release.wait(3); backend.info['label']='Finished'
    backend.press=slow
    action=asyncio.create_task(adapter.act(state['observation'],'e1','press'))
    await asyncio.to_thread(entered.wait,2)
    action.cancel()
    with pytest.raises(asyncio.CancelledError): await action
    observation=asyncio.create_task(adapter.observe())
    await asyncio.sleep(.05)
    assert not observation.done()
    release.set()
    result=await asyncio.wait_for(observation,3)
    assert result['targets'][0]['label']=='Finished'


def test_desktop_server_requires_private_token():
    with pytest.raises(ValueError,match='token'):
        create_desktop_server('org.example.fixture','',backend=Backend())


@pytest.mark.asyncio
async def test_authenticated_desktop_mcp_transport(monkeypatch):
    import socket
    import httpx
    import uvicorn
    from kestrel_agent.config import Settings
    from kestrel_agent.connections import Connection,ConnectionPool
    listener=socket.socket(); listener.bind(('127.0.0.1',0)); listener.listen()
    port=listener.getsockname()[1]
    token='test-only-'+'x'*40
    monkeypatch.setenv('TEST_DESKTOP_TOKEN',token)
    backend=Backend()
    app=create_desktop_server(backend.bundle_id,token,port,backend=backend).streamable_http_app()
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'))
    job=asyncio.create_task(server.serve(sockets=[listener]))
    pool=ConnectionPool(Settings(provider='openai-compatible',mcp_connections={'desktop':Connection(url=f'http://127.0.0.1:{port}/mcp',bearer_env='TEST_DESKTOP_TOKEN')}))
    try:
        async with asyncio.timeout(5):
            while not server.started:
                await asyncio.sleep(.01)
        async with httpx.AsyncClient() as client:
            for headers in ({},{'Authorization':'Bearer wrong'}):
                response=await client.get(f'http://127.0.0.1:{port}/mcp',headers=headers)
                assert response.status_code in {401,403}
        assert not backend.calls
        catalog=await pool.catalog()
        assert {x['name'] for x in catalog[0]['tools']}=={'desktop_observe','desktop_act'}
        state=(await pool.call('desktop','desktop_observe',{}))['structuredContent']
        result=await pool.call('desktop','desktop_act',{'observation':state['observation'],'target':'e1','operation':'press'})
        assert result['structuredContent']['targets'][0]['label']=='Saved'
        assert backend.calls==[('press','button')]
    finally:
        await pool.close()
        server.should_exit=True
        await asyncio.wait_for(job,5)
        listener.close()


def test_real_mac_permission_denial_before_app_access():
    import sys
    if sys.platform!='darwin': pytest.skip('macOS-specific')
    ax=pytest.importorskip('ApplicationServices')
    if ax.AXIsProcessTrusted(): pytest.skip('Do not inspect personal apps in this permission test')
    from kestrel_agent.desktop import MacAccessibility
    with pytest.raises(PermissionError,match='Accessibility'):
        MacAccessibility('org.example.nonexistent').application()
