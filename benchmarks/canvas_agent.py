"""Explicit live autonomous Engine canvas task; isolated fixture, no baseline claim."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import time
import uuid

import uvicorn
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route

from kestrel_agent.browser import create_browser_server
from kestrel_agent.config import Settings, load_secrets, redact
from kestrel_agent.connections import Connection
from kestrel_agent.engine import Engine
from kestrel_agent.store import Store


async def main():
    load_secrets()
    nonce = uuid.uuid4().hex[:8].upper()
    records = []
    html = '''<body style="margin:0"><canvas id="c" width="760" height="440"></canvas><script>
    const c=document.getElementById('c'),g=c.getContext('2d');
    g.fillStyle='white';g.fillRect(0,0,760,440);g.font='22px sans-serif';
    g.fillStyle='green';g.fillRect(400,200,170,65);g.fillStyle='white';g.fillText('Confirm',430,240);
    g.fillStyle='red';g.fillRect(90,70,170,65);g.fillStyle='white';g.fillText('Reject',125,110);
    c.onclick=e=>{const kind=e.offsetX>=400&&e.offsetX<570&&e.offsetY>=200&&e.offsetY<265?'green':'other';
    fetch('/record',{method:'POST',body:JSON.stringify({kind})}).then(r=>r.json()).then(v=>{
    if(v.code){g.fillStyle='black';g.fillText('SAVED '+v.code,40,390);}});};
    </script></body>'''
    async def page(request): return HTMLResponse(html)
    async def record(request):
        value = await request.json()
        records.append(value)
        return JSONResponse({'code':nonce if value == {'kind':'green'} else None})
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen()
    port=listener.getsockname()[1]
    mcp=create_browser_server(port,headless=True).streamable_http_app()
    app=Starlette(routes=[Route('/fixture',page),Route('/record',record,methods=['POST']),Mount('/',app=mcp)],lifespan=mcp.router.lifespan_context)
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'))
    server_task=asyncio.create_task(server.serve(sockets=[listener]))
    report={'kind':'autonomous-canvas-smoke','model':'gpt-6-astra','effort':'medium','agent_mode':'standard','passed':False,
            'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    previous_home=os.environ.get('KESTREL_HOME')
    try:
        async with asyncio.timeout(10):
            while not server.started: await asyncio.sleep(.01)
        with tempfile.TemporaryDirectory(prefix='kestrel-canvas-agent-') as directory:
            root=Path(directory);workspace=root/'workspace';workspace.mkdir()
            os.environ['KESTREL_HOME']=str(root/'state')
            settings=Settings(agent_mode='standard',model='gpt-6-astra',effort='medium',network=True,shell=False,
                max_model_calls=14,max_minutes=4,mcp_connections={'browser':Connection(url=f'http://127.0.0.1:{port}/mcp',
                read_only_tools=['browser_tabs','browser_snapshot','browser_screenshot'])})
            store=Store(settings);sid=store.create(workspace)
            async def confirm(description): return description.startswith('Call connected tool direct:browser/browser_')
            def emit(kind,message):
                if kind in {'plan','warning','done','usage'}: print(kind+': '+redact(message),flush=True)
            engine=Engine(settings,workspace,store,sid,emit,confirm)
            started=time.monotonic()
            try:
                engine.mcp_tools=await engine.runtime.connections.catalog()
                prompt=f'Open http://127.0.0.1:{port}/fixture in the connected browser. Click the green Confirm rectangle exactly once. Read the code displayed after SAVED and report it. Use fresh screenshots and image inspection for this canvas. Do not edit files or use other services.'
                report['prompt']=prompt
                async with asyncio.timeout(260): report['answer']=await engine.run(prompt)
            except Exception as error: report['error']=redact(type(error).__name__+': '+str(error))
            finally:
                observations=engine.state.get('observations',[])
                readback=any(item.get('tool')=='inspect_image' and nonce in str((item.get('result') or {}).get('content','')) for item in observations)
                report.update(elapsed_seconds=round(time.monotonic()-started,3),status=engine.state.get('status'),usage=engine.state.get('usage'),
                    records=records,expected_code=nonce,observations=observations,events=store.history(sid,200),
                    unexpected_files=[str(p.relative_to(workspace)) for p in workspace.rglob('*')],readback_observed=readback)
                report['passed']=report['status']=='completed' and records==[{'kind':'green'}] and readback and nonce in report.get('answer','') and not report['unexpected_files']
                await engine.close();store.close()
    finally:
        if previous_home is None: os.environ.pop('KESTREL_HOME',None)
        else: os.environ['KESTREL_HOME']=previous_home
        server.should_exit=True
        await asyncio.wait_for(server_task,15)
        listener.close()
        Path('benchmarks/results-canvas-agent.json').write_text(redact(json.dumps(report,indent=2,default=str))+'\n')
    print(json.dumps({key:report.get(key) for key in ['passed','elapsed_seconds','status','error','records','readback_observed']}),flush=True)


if __name__=='__main__': asyncio.run(main())
