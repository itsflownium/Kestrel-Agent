"""Explicit live workload benchmark; isolated fixtures, independent graders, no answer lookup in the agent."""
import argparse
import asyncio
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from openai_codex import ApprovalMode, Sandbox
from openai_codex.generated.v2_all import ReasoningEffort
from kestrel_agent.config import Settings, load_secrets, redact
from kestrel_agent.engine import Engine
from kestrel_agent.providers import Runtime
from kestrel_agent.store import Store

CASES = [
    {'id':'code_edit', 'prompt':'Fix stats.py: mean(values) must accept any iterable of numbers, return None for empty input, and correctly average nonempty values. Edit the file; do not just describe a patch. Do not change any other files.',
     'files':{'stats.py':'def mean(values):\n    return sum(values) / len(values)\n'}},
    {'id':'multi_file', 'prompt':'Read policy.md and releases.json. As of 2026-09-15, which release may be deployed to production? Return only JSON with keys release and reason. Respect every policy requirement.',
     'files':{'policy.md':'Production requires signed=true, channel=stable, and release_date no later than the as-of date. Choose the newest eligible release; use release=null if none.\n',
              'releases.json':json.dumps([{'id':'r21','signed':True,'channel':'stable','release_date':'2026-09-10'}, {'id':'r22','signed':False,'channel':'stable','release_date':'2026-09-14'}, {'id':'r23','signed':True,'channel':'beta','release_date':'2026-09-15'}, {'id':'r24','signed':True,'channel':'stable','release_date':'2026-09-18'}])}},
    {'id':'csv_totals', 'prompt':'Read orders.csv. Sum amount by region for paid rows only. Exclude invalid numeric amounts and all other statuses. Return only JSON mapping region to numeric total.',
     'files':{'orders.csv':'region,amount,status\nEU,12.50,paid\nUS,9.25,paid\nEU,8.75,cancelled\nEU,29.00,paid\nUS,-2.25,paid\nEU,invalid,paid\nUS,100,pending\n'}},
    {'id':'tool_recovery', 'prompt':'Run python3 summarize.py. If it fails, inspect the script/help and correct the command arguments, then run it successfully. Do not edit files. Report the actual total emitted by the successful command.',
     'files':{'summarize.py':'import argparse, json\np=argparse.ArgumentParser()\np.add_argument("--input", required=True)\na=p.parse_args()\nprint("TOTAL=" + str(sum(json.load(open(a.input)))))\n', 'numbers.json':'[7, 13, 22]\n'}},
    {'id':'ambiguous_selection','prompt':'Read options.json. Select the cheapest option with capacity at least 20. If two or more eligible options tie for cheapest, reply with exactly TIE. Otherwise reply with only its code.',
     'files':{'options.json':json.dumps([{'code':'P7','capacity':25,'price':9},{'code':'K2','capacity':30,'price':9},{'code':'Z1','capacity':10,'price':2}])}},
    {'id':'table_mean_variant','prompt':'Read readings.json. For records where accepted is yes and minutes is at least 2, calculate the mean of reading by station. Exclude invalid numeric readings. Return only a JSON object mapping station to numeric mean.',
     'files':{'readings.json':json.dumps([
         {'station':'North','reading':'1.2','accepted':'yes','minutes':2},
         {'station':'North','reading':'2.8','accepted':'yes','minutes':4},
         {'station':'North','reading':'bad','accepted':'yes','minutes':3},
         {'station':'South','reading':'-3','accepted':'yes','minutes':2},
         {'station':'South','reading':'7','accepted':'yes','minutes':5},
         {'station':'South','reading':'100','accepted':'no','minutes':8},
         {'station':'North','reading':'80','accepted':'yes','minutes':1}])}},
    {'id':'recovery_variant','prompt':'Run python3 calculate.py. If it fails, inspect the program and correct the arguments using the existing input file, then run it successfully. Do not edit files. Report the actual emitted result.',
     'files':{'calculate.py':'import argparse, json\np=argparse.ArgumentParser()\np.add_argument("--source", required=True)\na=p.parse_args()\nprint("RESULT=" + str(sum(json.load(open(a.source))["values"])))\n', 'batch.json':'{"values":[-4, 8, 13]}\n'}},
    {'id':'table_count_variant','prompt':'Read events.csv. Count rows by queue where status is closed and score is below 4. Return only JSON mapping each queue to its numeric count.',
     'files':{'events.csv':'queue,status,score\nX,closed,-1\nX,closed,2\nX,closed,7\nY,closed,0\nY,open,2\n'}},
    {'id':'table_write_variant','prompt':'Read transactions.csv. Sum net by team for state settled only, then write totals.json with the numeric totals. Reply exactly SAVED after the file is written.',
     'files':{'transactions.csv':'team,net,state\nA,3,settled\nB,-1,settled\nA,4,settled\nB,90,pending\n'},
     'created_files':['totals.json']},
]

async def allow(_): return True

def json_answer(text):
    value=text.strip()
    if value.startswith('```'):
        value='\n'.join(value.splitlines()[1:-1])
    return json.loads(value)

def numeric_mapping(value, expected):
    return isinstance(value,dict) and all(type(v) in {int,float} for v in value.values()) and value==expected

async def grade(case,answer,workspace,runtime,events):
    try:
        if case=='code_edit':
            code='import sys; sys.path.insert(0,"."); from stats import mean; assert mean([]) is None; assert mean(iter([])) is None; assert mean((v for v in [2,4,9])) == 5; assert mean([-2,2]) == 0; assert mean([1.5,2.5]) == 2; print("PASS")'
            result=await runtime.command([sys.executable,'-I','-c',code],str(workspace),'grade-code')
            return result.get('exitCode')==0, {'grader':result}
        if case=='multi_file':
            value=json_answer(answer)
            return value.get('release')=='r21' and bool(value.get('reason')), {'parsed':value}
        if case=='csv_totals':
            value=json_answer(answer)
            return numeric_mapping(value,{'EU':41.5,'US':7.0}), {'parsed':value}
        if case=='table_mean_variant':
            value=json.loads(answer)
            return numeric_mapping(value,{'North':2,'South':2}), {'parsed':value}
        if case=='table_count_variant':
            value=json.loads(answer)
            return numeric_mapping(value,{'X':2,'Y':1}), {'parsed':value}
        if case=='table_write_variant':
            value=json.loads((workspace/'totals.json').read_text())
            return numeric_mapping(value,{'A':7,'B':-1}) and answer.strip()=='SAVED', {'saved_json':value}
        if case=='ambiguous_selection':
            return answer.strip()=='TIE', {}
        if case=='tool_recovery':
            output=json.dumps(events)
            return '42' in answer and 'TOTAL=42' in output, {'observed_success':'TOTAL=42' in output}
        if case=='recovery_variant':
            output=json.dumps(events)
            return '17' in answer and 'RESULT=17' in output, {'observed_success':'RESULT=17' in output}
    except Exception as error:
        return False, {'grader_error':redact(str(error))}

async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='benchmarks/results-workloads.json')
    parser.add_argument('--tasks',default='')
    parser.add_argument('--repeat',type=int,default=1,choices=range(1,11))
    args=parser.parse_args()
    tasks=[c for c in CASES if not args.tasks or c['id'] in args.tasks.split(',')]
    load_secrets()
    source=Path(__file__).resolve().parents[1]/'src/kestrel_agent'
    source_hash=hashlib.sha256(b''.join(p.read_bytes() for p in sorted(source.glob('*.py')))).hexdigest()
    results=[]
    with tempfile.TemporaryDirectory(prefix='kestrel-workloads-') as directory:
        root=Path(directory)
        os.environ['KESTREL_HOME']=str(root/'state')
        settings=Settings(model='gpt-6-astra',effort='medium',permission='workspace',network=False,confirm_shell=False,max_minutes=3)
        store=Store(settings)
        for index,case in enumerate(tasks * args.repeat):
            repetition=index // len(tasks) + 1
            for arm in (['kestrel','codex'] if index%2 else ['codex','kestrel']):
                workspace=root/(case['id']+'-'+str(repetition)+'-'+arm); workspace.mkdir()
                for name,body in case['files'].items(): (workspace/name).write_text(body)
                events=[]
                start=time.perf_counter()
                def emit(kind,text):
                    events.append({'seconds':round(time.perf_counter()-start,3),'kind':kind,'text':redact(text)})
                    if kind!='output': print(arm,case['id'],kind,redact(text)[:160],flush=True)
                runtime=Runtime(settings,workspace,emit)
                engine=None
                record={'task':case['id'],'arm':arm,'repetition':repetition,'source_sha256':source_hash,'model':settings.model,'effort':settings.effort,'input_files':case['files'],'prompt':case['prompt']}
                try:
                    async with asyncio.timeout(180):
                        if arm=='kestrel':
                            sid=store.create(workspace)
                            engine=Engine(settings,workspace,store,sid,emit,allow)
                            answer=await engine.run(case['prompt'])
                            record.update(engine.state.get('usage',{}))
                            record['trace']=[dict(row) for row in store.db.execute('SELECT kind,body FROM events WHERE session=?',(sid,))]
                        else:
                            await runtime.start()
                            thread=await runtime.codex.thread_start(model=settings.model,cwd=str(workspace),ephemeral=True,sandbox=Sandbox.workspace_write,approval_mode=ApprovalMode.deny_all,config={'web_search':'disabled','apps._default.enabled':False},developer_instructions='Complete the user task accurately. Use only the supplied workspace files. No connected apps, network, or unrelated files. Report actual observed outcomes.')
                            turn=await thread.turn(case['prompt'],effort=ReasoningEffort.medium)
                            runtime.active_turn=turn
                            result=await turn.run()
                            runtime.active_turn=None
                            answer=result.final_response
                            record['usage']=str(result.usage)
                            for item in result.items:
                                events.append({'kind':'codex_item','text':str(item)})
                    record['seconds']=round(time.perf_counter()-start,3)
                    record['answer']=answer
                    record['passed'],record['grading']=await grade(case['id'],answer,workspace,runtime,events)
                except Exception as error:
                    record.update(seconds=round(time.perf_counter()-start,3),error=redact(str(error)),passed=False)
                finally:
                    if engine:
                        record.update(generation_calls=engine.runtime.model_calls,jev_calls=engine.judge.calls)
                        await engine.close()
                    await runtime.close()
                record['events']=events
                record['artifacts']={p.name:p.read_text() for p in workspace.iterdir() if p.is_file() and p.stat().st_size<100000}
                # Scope is part of task quality, independently of answer correctness.
                unchanged=all(record['artifacts'].get(name)==body for name,body in case['files'].items() if not (case['id']=='code_edit' and name=='stats.py'))
                no_extra_files=set(record['artifacts'])==set(case['files']) | set(case.get('created_files',[]))
                record['scope_passed']=unchanged and no_extra_files
                record['passed']=record['passed'] and record['scope_passed']
                if arm=='kestrel':
                    record['verified_result_reuses']=sum(row['kind']=='verified_result_reuse' for row in record.get('trace',[]))
                    record['table_fastpaths']=sum(row['kind']=='table_fastpath_result' for row in record.get('trace',[]))
                results.append(record)
                Path(args.output).write_text(json.dumps(results,indent=2))
                print('RESULT',json.dumps({k:v for k,v in record.items() if k in {'task','arm','seconds','passed','error','generation_calls','jev_calls','answer','grading'}}),flush=True)
        store.close()

if __name__=='__main__': asyncio.run(main())
