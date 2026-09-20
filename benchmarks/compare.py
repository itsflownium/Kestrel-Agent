"""Small live comparison. Run explicitly; makes paid/subscription model calls."""
import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

from openai_codex import ApprovalMode, Sandbox
from openai_codex.generated.v2_all import ReasoningEffort
from kestrel_agent.config import Settings, load_secrets, redact
from kestrel_agent.engine import Engine
from kestrel_agent.providers import Runtime
from kestrel_agent.store import Store

TASKS = [
 ('arithmetic', 'What is 17 times 23? Reply with only the number.', '391'),
 ('selection', 'Read candidates.json. Choose the cheapest plan with at least 20 GB storage and at least 5 users. Reply with the plan name and monthly price.', 'Cedar'),
]

async def deny(_):
 return False

async def main():
 load_secrets()
 results=[]
 with tempfile.TemporaryDirectory(prefix='kestrel-benchmark-') as directory:
  root=Path(directory)
  os.environ['KESTREL_HOME']=str(root/'state')
  settings=Settings(model='gpt-6-astra', effort='medium', jev_model='jev-latest', permission='read-only', max_minutes=3)
  store=Store(settings)
  for index,(name,prompt,expected) in enumerate(TASKS):
   for arm in (['codex','kestrel'] if index%2==0 else ['kestrel','codex']):
    workspace=root/f'{name}-{arm}'; workspace.mkdir()
    (workspace/'candidates.json').write_text(json.dumps([
     {'name':'Birch','storage_gb':10,'users':8,'monthly_price':5},
     {'name':'Cedar','storage_gb':25,'users':5,'monthly_price':12},
     {'name':'Maple','storage_gb':50,'users':10,'monthly_price':20},
     {'name':'Pine','storage_gb':30,'users':2,'monthly_price':8}]))
    events=[]
    def emit(kind,text):
     events.append({'seconds':round(time.perf_counter()-start,3),'kind':kind,'text':redact(text)})
     print(arm,name,kind,redact(text)[:180],flush=True)
    engine=None
    runtime=None
    start=time.perf_counter()
    record={'task':name,'arm':arm,'model':'gpt-6-astra','effort':'medium'}
    try:
     async with asyncio.timeout(180):
      if arm=='kestrel':
       sid=store.create(workspace)
       engine=Engine(settings,workspace,store,sid,emit,deny)
       answer=await engine.run(prompt)
       record.update(engine.state.get('usage',{}))
      else:
       runtime=Runtime(settings,workspace,emit)
       await runtime.start()
       thread=await runtime.codex.thread_start(model=settings.model,cwd=str(workspace),ephemeral=True,sandbox=Sandbox.read_only,approval_mode=ApprovalMode.deny_all,config={'web_search':'disabled','apps._default.enabled':False},developer_instructions='Complete the user task accurately and concisely. Only read files inside the given workspace. Do not access connected apps or network.')
       result=await thread.run(prompt,effort=ReasoningEffort.medium)
       answer=result.final_response
       record['usage']=str(result.usage) if hasattr(result,'usage') else None
      record.update(answer=answer,passed=expected in answer and (name!='selection' or '12' in answer))
    except Exception as error:
     record.update(error=redact(str(error)),passed=False)
    finally:
     record['seconds']=round(time.perf_counter()-start,3)
     if engine:
      record['codex_calls']=engine.runtime.model_calls
      record['jev_calls']=engine.judge.calls
      await engine.close()
     if runtime: await runtime.close()
    record['events']=events
    results.append(record)
    Path('benchmarks/results.json').write_text(json.dumps(results,indent=2))
    print('RESULT',json.dumps({k:v for k,v in record.items() if k!='events'}),flush=True)
  store.close()

if __name__=='__main__':
 asyncio.run(main())
