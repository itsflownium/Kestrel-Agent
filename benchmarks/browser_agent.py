"""Live, explicitly invoked browser task; server-side outcome oracle, no baseline claim."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import time
import uuid
from contextlib import asynccontextmanager

import uvicorn
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route

from kestrel_agent.browser import create_browser_server
from kestrel_agent.config import Settings, load_secrets, redact
from kestrel_agent.connections import Connection
from kestrel_agent.engine import Engine
from kestrel_agent.store import Store


def grade(record):
    target = record['target']
    visible = any(item.get('tool') == 'mcp' and item.get('status') == 'completed' and
        item.get('result', {}).get('structuredContent', {}).get('text', '').find('Saved record: ' + target) >= 0
        for item in record.get('observations', []))
    passed = record.get('status') == 'completed' and record.get('submitted') == [{'name': target}] and not record.get('unexpected_files') and visible and target in record.get('answer', '')
    return passed, visible


async def run(args):
    load_secrets()
    target = 'Record-' + uuid.uuid4().hex[:8]
    submitted = []
    async def page(request):
        return HTMLResponse('''<!doctype html><title>Registration fixture</title>
        <label for="record">Record name</label><input id="record">
        <button onclick="fetch('/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:document.querySelector('#record').value})}).then(r=>r.json()).then(v=>document.querySelector('#result').textContent=v.message)">Save record</button>
        <p id="result">No record submitted</p>''')
    async def submit(request):
        value = await request.json()
        submitted.append(value)
        return JSONResponse({'message': 'Saved record: ' + str(value.get('name'))})
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    listener.listen()
    mcp = create_browser_server(port=port, headless=True).streamable_http_app()
    app = Starlette(routes=[Route('/fixture', page), Route('/submit', submit, methods=['POST']), Mount('/', app=mcp)], lifespan=mcp.router.lifespan_context)
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    server_task = asyncio.create_task(server.serve(sockets=[listener]))
    record = {'kind':'live-browser-smoke', 'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'fixture_revision':2, 'mode':args.mode, 'model':'gpt-6-astra', 'effort':'medium', 'target':target, 'baseline':None}
    try:
        async with asyncio.timeout(10):
            while not server.started:
                await asyncio.sleep(.01)
        with tempfile.TemporaryDirectory(prefix='kestrel-browser-task-') as temp:
            root = Path(temp)
            workspace = root/'workspace'
            workspace.mkdir()
            previous_home = os.environ.get('KESTREL_HOME')
            os.environ['KESTREL_HOME'] = str(root/'state')
            settings = Settings(agent_mode=args.mode, model='gpt-6-astra', effort='medium', permission='workspace',
                network=True, shell=False, max_model_calls=12, max_minutes=4,
                mcp_connections={'browser':Connection(url=f'http://127.0.0.1:{port}/mcp')})
            store = Store(settings)
            sid = store.create(workspace)
            async def confirm(description):
                return description.startswith('Call connected tool direct:browser/browser_')
            def emit(kind, message):
                if kind in {'warning','plan','done','usage'}:
                    print(kind + ': ' + redact(message), flush=True)
            engine = Engine(settings, workspace, store, sid, emit, confirm)
            start = time.monotonic()
            try:
                # Controlled tool access: this fixture's real catalog only, no personal connectors.
                engine.mcp_tools = await engine.runtime.connections.catalog()
                prompt = (f'Using the connected browser, open http://127.0.0.1:{port}/fixture. '
                          f'Enter {target} in Record name and save the record exactly once. '
                          'Verify the visible saved message and report the record name. Do not edit files or use other services.')
                record['prompt'] = prompt
                record['answer'] = await engine.run(prompt)
            except Exception as error:
                record['error'] = redact(str(error))
            finally:
                record['elapsed_seconds'] = round(time.monotonic()-start,3)
                record['usage'] = engine.state.get('usage')
                record['status'] = engine.state.get('status')
                record['submitted'] = submitted
                record['unexpected_files'] = [str(p.relative_to(workspace)) for p in workspace.rglob('*')]
                observations = engine.state.get('observations', [])
                record['observations'] = observations
                record['passed'], record['visible_confirmation_observed'] = grade(record)
                record['events'] = store.history(sid,200)
                await engine.close()
                store.close()
                if previous_home is None:
                    os.environ.pop('KESTREL_HOME',None)
                else:
                    os.environ['KESTREL_HOME'] = previous_home
    finally:
        server.should_exit = True
        await asyncio.wait_for(server_task,15)
        listener.close()
    args.output.write_text(redact(json.dumps(record,indent=2,default=str)))
    print(json.dumps({key:record.get(key) for key in ['passed','elapsed_seconds','status','error','submitted']}),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['jev','standard'],default='jev')
    parser.add_argument('--output',type=Path,required=True)
    asyncio.run(run(parser.parse_args()))
