"""Live agent discovery from an oversized isolated MCP catalog; no external services."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import time
import uuid

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel
import uvicorn

from kestrel_agent.config import Settings, load_secrets, redact
from kestrel_agent.connections import Connection
from kestrel_agent.engine import Engine
from kestrel_agent.store import Store
from kestrel_agent.tool_discovery import preview


async def main():
    load_secrets()
    order='ORDER-'+uuid.uuid4().hex[:8]
    expected='READY-'+uuid.uuid4().hex[:8]
    calls=[]
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen()
    port=listener.getsockname()[1]
    app=FastMCP('Discovery fixture',host='127.0.0.1',port=port,json_response=True)
    for index in range(100):
        def unrelated() -> str:
            calls.append({'unexpected':True})
            return 'Unrelated report'
        app.add_tool(unrelated,name=f'a_report_{index:03}',description='Unrelated accounting report operation. '*30)
    class ShippingResult(BaseModel):
        order_id: str
        status: str
    @app.tool(description='Look up the current shipping status of an order by its exact order identifier. '*30)
    def z_shipping_status(order_id: str) -> ShippingResult:
        calls.append({'order_id':order_id})
        return ShippingResult(order_id=order_id,status=expected if order_id==order else 'UNKNOWN')
    server=uvicorn.Server(uvicorn.Config(app.streamable_http_app(),log_level='error'))
    server_task=asyncio.create_task(server.serve(sockets=[listener]))
    report={'kind':'large-catalog-discovery-smoke','model':'gpt-6-astra','effort':'medium','agent_mode':'standard','passed':False,
            'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    previous_home=os.environ.get('KESTREL_HOME')
    try:
        async with asyncio.timeout(5):
            while not server.started: await asyncio.sleep(.01)
        with tempfile.TemporaryDirectory(prefix='kestrel-discovery-agent-') as directory:
            root=Path(directory);workspace=root/'workspace';workspace.mkdir()
            os.environ['KESTREL_HOME']=str(root/'state')
            settings=Settings(agent_mode='standard',model='gpt-6-astra',effort='medium',network=True,shell=False,max_model_calls=12,max_minutes=4,
                mcp_connections={'fixture':Connection(url=f'http://127.0.0.1:{port}/mcp',read_only_tools=['z_shipping_status'])})
            store=Store(settings);sid=store.create(workspace)
            async def confirm(description): return description.startswith('Call connected tool direct:fixture/')
            def emit(kind,message):
                if kind in {'plan','warning','done','usage'}: print(kind+': '+redact(message),flush=True)
            engine=Engine(settings,workspace,store,sid,emit,confirm)
            started=time.monotonic()
            try:
                engine.mcp_tools=await engine.runtime.connections.catalog()
                initial=preview(engine.mcp_tools)
                omitted=not any(item['tool']=='z_shipping_status' for item in initial['tools'])
                report.update(initial_catalog_preview=initial,target_omitted=omitted)
                assert omitted, 'Fixture must require discovery of a tool omitted from the initial prompt.'
                prompt=f'Use the connected service to look up the shipping status for order {order}. Reply with only the exact status returned by that service. Do not edit files or use any other services.'
                report['prompt']=prompt
                async with asyncio.timeout(260): report['answer']=await engine.run(prompt)
            except Exception as error: report['error']=redact(type(error).__name__+': '+str(error))
            finally:
                observations=engine.state.get('observations',[])
                discovery=any(o.get('tool')=='discover_tools' and o.get('status')=='completed' for o in observations)
                inspection=any(o.get('tool')=='inspect_tool' and o.get('status')=='completed' and (o.get('result') or {}).get('tool')=='z_shipping_status' for o in observations)
                report.update(elapsed_seconds=round(time.monotonic()-started,3),status=engine.state.get('status'),usage=engine.state.get('usage'),
                    observations=observations,events=store.history(sid,200),calls=calls,expected_status=expected,discovery_observed=discovery,inspection_observed=inspection,
                    unexpected_files=[str(p.relative_to(workspace)) for p in workspace.rglob('*')])
                report['passed']=report['status']=='completed' and discovery and inspection and calls==[{'order_id':order}] and report.get('answer','').strip()==expected and not report['unexpected_files']
                await engine.close();store.close()
    finally:
        if previous_home is None: os.environ.pop('KESTREL_HOME',None)
        else: os.environ['KESTREL_HOME']=previous_home
        server.should_exit=True
        await asyncio.wait_for(server_task,15);listener.close()
        Path('benchmarks/results-tool-discovery-agent.json').write_text(redact(json.dumps(report,indent=2,default=str))+'\n')
    print(json.dumps({key:report.get(key) for key in ['passed','elapsed_seconds','status','error','calls','discovery_observed','inspection_observed']}),flush=True)


if __name__=='__main__': asyncio.run(main())
