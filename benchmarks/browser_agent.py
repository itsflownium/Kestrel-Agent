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


def observed_browser_text(item):
    if item.get('tool') != 'mcp' or item.get('status') != 'completed':
        return ''
    result = item.get('result') or {}
    structured = result.get('structuredContent')
    if isinstance(structured, dict) and isinstance(structured.get('text'), str):
        return structured['text']
    for block in result.get('content') or []:
        if not isinstance(block, dict) or block.get('type') != 'text':
            continue
        try:
            from kestrel_agent.completion import parse_json
            value = parse_json(block.get('text', ''))
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict) and isinstance(value.get('text'), str):
            return value['text']
    return ''


def grade(record):
    target = record['target']
    visible = any('Saved record: ' + target in observed_browser_text(item)
                  for item in record.get('observations', []))
    allowed_scope = record.get('mode') != 'direct-codex' or all(
        item.get('server') == 'kestrel_browser_fixture'
        for item in record.get('observations', []) if item.get('tool') == 'mcp')
    passed = allowed_scope and record.get('status') == 'completed' and record.get('submitted') == [{'name': target}] and not record.get('unexpected_files') and visible and target in (record.get('answer') or '')
    return passed, visible


async def direct_codex(engine, prompt, endpoint):
    from openai_codex import ApprovalMode, Sandbox
    from openai_codex.generated.v2_all import ReasoningEffort
    runtime = engine.runtime
    await runtime.start()
    config = await runtime.rpc('config/read', {'includeLayers':False})
    servers = config.get('config', {}).get('mcp_servers', {}) or {}
    plugins = config.get('config', {}).get('plugins', {}) or {}
    overrides = {'web_search':'disabled', 'apps._default.enabled':False,
        'features.shell_tool':False, 'features.unified_exec':False, 'features.code_mode':False,
        **{f'mcp_servers.{name}.enabled':False for name in servers},
        **{f'plugins.{name}.enabled':False for name in plugins},
        'mcp_servers.kestrel_browser_fixture.enabled':True,
        'mcp_servers.kestrel_browser_fixture.url':endpoint}
    thread = await runtime.codex.thread_start(model=engine.settings.model, cwd=str(engine.workspace),
        ephemeral=True, sandbox=Sandbox.read_only, approval_mode=ApprovalMode.auto_review,
        config=overrides, developer_instructions='Complete the user task using only the provided browser fixture tools. Inspect current page state, act on observed targets, and verify the requested outcome. Do not use other services or edit files.')
    async with asyncio.timeout(240):
        turn = await thread.turn(prompt, effort=ReasoningEffort.medium)
        runtime.active_turn = turn
        try:
            result = await turn.run()
        finally:
            runtime.active_turn = None
    observations = []
    for item in result.items:
        value = getattr(item,'root',item)
        if getattr(value,'type',None) == 'mcpToolCall':
            data = value.model_dump(mode='json',by_alias=True)
            observations.append({'tool':'mcp','status':data['status'], 'arguments':data['arguments'],
                'server':data['server'],'name':data['tool'],'result':data.get('result') or {}, 'error':data.get('error')})
    return result, observations


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
              'fixture_revision':2, 'mode':args.mode, 'model':'gpt-6-astra', 'effort':'medium', 'target':target, 'baseline':'native-codex' if args.mode == 'direct-codex' else None,
              'approval_policy':'auto_review' if args.mode == 'direct-codex' else 'fixture-only-controller-confirmation'}
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
            settings = Settings(agent_mode='standard' if args.mode == 'direct-codex' else args.mode, model='gpt-6-astra', effort='medium', permission='workspace',
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
                if args.mode == 'direct-codex':
                    result, observations = await direct_codex(engine, prompt, f'http://127.0.0.1:{port}/mcp')
                    record['answer'] = result.final_response
                    engine.state['observations'] = observations
                    engine.state['status'] = 'completed' if str(result.status).split('.')[-1] == 'completed' else str(result.status)
                    engine.state['usage'] = {'native_codex_usage':str(result.usage), 'jev_calls':0}
                else:
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
    parser.add_argument('--mode',choices=['jev','standard','direct-codex'],default='jev')
    parser.add_argument('--output',type=Path,required=True)
    asyncio.run(run(parser.parse_args()))
