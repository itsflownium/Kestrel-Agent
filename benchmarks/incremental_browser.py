"""Paired graph versus one-action planning; same model, adapter and dynamic fixture."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import random
import socket
import tempfile
import time

import uvicorn
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route

from browser_agent import observed_browser_text
from kestrel_agent.browser import create_browser_server
from kestrel_agent.config import Settings, load_secrets, redact
from kestrel_agent.connections import Connection
from kestrel_agent.engine import Engine
from kestrel_agent.store import Store


def grade(record):
    expected=[{'operation':'prepare'},{'operation':'submit','code':record['confirmation_code']}]
    observed=any(record['receipt'] in observed_browser_text(item) for item in record.get('observations',[]))
    allowed={'mcp','load_skill','list_skills','inspect_image','read_evidence','search_evidence','choose','generate','discover_tools','inspect_tool'}
    scoped=all(item.get('tool') in allowed and (item.get('tool')!='mcp' or (item.get('arguments') or {}).get('server')=='direct:browser') for item in record.get('observations',[]))
    return (record.get('status')=='completed' and record.get('operations')==expected and observed and scoped
            and record.get('answer','').strip()==record['receipt'] and not record.get('unexpected_files'))


async def run(strategy, fixture_seed):
    rng=random.Random(fixture_seed)
    code=f'{rng.getrandbits(32):08X}'
    receipt='RECEIPT-'+f'{rng.getrandbits(32):08X}'
    operations=[]
    html='''<!doctype html><title>Shipping request</title><body><main id="stage">
    <h1>Shipping request</h1><button id="prepare">Prepare request</button></main>
    <script>
    const stage=document.getElementById('stage');
    document.getElementById('prepare').onclick=()=>{
      stage.innerHTML='<p>Preparing request...</p>';
      fetch('/prepare',{method:'POST'}).then(r=>r.json()).then(v=>{
        stage.innerHTML='<h1>Confirm request</h1><p>Confirmation code: '+v.code+'</p><label for="code">Confirmation code</label><input id="code"><button id="submit">Submit request</button><p id="result">Not submitted</p>';
        document.getElementById('submit').onclick=()=>{
          const value=document.getElementById('code').value;
          stage.innerHTML='<p>Submitting request...</p>';
          fetch('/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:value})}).then(r=>r.json()).then(v=>{
            stage.innerHTML='<h1>Result</h1><p>'+v.message+'</p>';
          });
        };
      });
    };
    </script></body>'''
    async def page(request): return HTMLResponse(html)
    async def prepare(request):
        operations.append({'operation':'prepare'})
        await asyncio.sleep(.25)
        return JSONResponse({'code':code})
    async def submit(request):
        value=await request.json()
        operations.append({'operation':'submit','code':value.get('code')})
        await asyncio.sleep(.25)
        return JSONResponse({'message':receipt if value.get('code')==code else 'Rejected: wrong confirmation code'})
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen()
    port=listener.getsockname()[1]
    mcp=create_browser_server(port,headless=True).streamable_http_app()
    app=Starlette(routes=[Route('/fixture',page),Route('/prepare',prepare,methods=['POST']),Route('/submit',submit,methods=['POST']),Mount('/',app=mcp)],lifespan=mcp.router.lifespan_context)
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'))
    server_task=asyncio.create_task(server.serve(sockets=[listener]))
    record={'strategy':strategy,'fixture_seed':fixture_seed,'confirmation_code':code,'receipt':receipt,'passed':False}
    previous_home=os.environ.get('KESTREL_HOME')
    try:
        async with asyncio.timeout(5):
            while not server.started: await asyncio.sleep(.01)
        with tempfile.TemporaryDirectory(prefix='kestrel-incremental-') as directory:
            root=Path(directory);workspace=root/'workspace';workspace.mkdir()
            os.environ['KESTREL_HOME']=str(root/'state')
            settings=Settings(agent_mode='standard',model='gpt-6-astra',effort='medium',network=True,shell=False,max_model_calls=20,max_minutes=5,max_steps=40,
                mcp_connections={'browser':Connection(url=f'http://127.0.0.1:{port}/mcp',read_only_tools=['browser_tabs','browser_snapshot','browser_screenshot'])})
            store=Store(settings);sid=store.create(workspace)
            async def confirm(description): return description.startswith('Call connected tool direct:browser/browser_')
            def emit(kind,message):
                if kind in {'plan','warning','done','usage'}: print(strategy+' '+kind+': '+redact(message),flush=True)
            engine=Engine(settings,workspace,store,sid,emit,confirm)
            engine._incremental_experiment=strategy=='incremental'
            started=time.monotonic()
            try:
                engine.mcp_tools=await engine.runtime.connections.catalog()
                prompt=f'Open http://127.0.0.1:{port}/fixture in the connected browser. Prepare the shipping request exactly once, enter the confirmation code displayed on the resulting page into its field, and submit the request exactly once. Verify the resulting receipt and reply with only its exact receipt identifier. Use current observations because the interface changes after each action. Do not edit files or use other services.'
                record['prompt']=prompt
                async with asyncio.timeout(320): record['answer']=await engine.run(prompt)
            except Exception as error: record['error']=redact(type(error).__name__+': '+str(error))
            finally:
                record.update(elapsed_seconds=round(time.monotonic()-started,3),status=engine.state.get('status'),usage=engine.state.get('usage'),
                    observations=engine.state.get('observations',[]),events=store.history(sid,200),operations=operations,
                    unexpected_files=[str(p.relative_to(workspace)) for p in workspace.rglob('*')])
                record['passed']=grade(record)
                await engine.close();store.close()
    finally:
        if previous_home is None: os.environ.pop('KESTREL_HOME',None)
        else: os.environ['KESTREL_HOME']=previous_home
        server.should_exit=True
        await asyncio.wait_for(server_task,15);listener.close()
    return record


async def main(args):
    load_secrets()
    rng=random.Random(args.seed)
    report={'kind':'paired-dynamic-browser-controller','model':'gpt-6-astra','effort':'medium','mode':'standard',
            'seed':args.seed,'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'runs':[]}
    for repeat in range(args.repeat):
        fixture_seed=rng.randrange(1,2**31)
        strategies=['graph','incremental'] if args.strategy=='both' else [args.strategy]
        rng.shuffle(strategies)
        for strategy in strategies:
            result=await run(strategy,fixture_seed)
            result['repeat']=repeat
            report['runs'].append(result)
            args.output.write_text(redact(json.dumps(report,indent=2,default=str))+'\n')
            print(json.dumps({key:result.get(key) for key in ['strategy','repeat','passed','elapsed_seconds','status','error','operations']}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--strategy',choices=['both','graph','incremental'],default='both')
    parser.add_argument('--seed',type=int,default=52913)
    parser.add_argument('--repeat',type=int,choices=range(1,5),default=2)
    parser.add_argument('--output',type=Path,required=True)
    asyncio.run(main(parser.parse_args()))
