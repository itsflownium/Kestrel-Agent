"""Explicit fault-injection recovery smoke; not a comparative performance test."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import secrets
import tempfile
import time

from kestrel_agent.config import Settings, load_secrets, redact
from kestrel_agent.engine import Engine
from kestrel_agent.schema import Action, Plan
from kestrel_agent.store import Store
try:
    from benchmarks.verification import manifest, scope_changes
except ModuleNotFoundError:
    from verification import manifest, scope_changes


async def main(output):
    load_secrets()
    nonce = secrets.token_hex(12)
    source = Path(__file__).resolve().parents[1]/'src/kestrel_agent'
    record = {'kind':'injected-invalid-reference-recovery','model':'gpt-6-astra','effort':'medium',
              'source_sha256':hashlib.sha256(b''.join(p.read_bytes() for p in sorted(source.glob('*.py')))).hexdigest(),
              'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    with tempfile.TemporaryDirectory(prefix='kestrel-reference-recovery-') as directory:
        root = Path(directory); workspace = root/'workspace'; workspace.mkdir()
        os.environ['KESTREL_HOME'] = str(root/'state')
        package = root/'state'/'skills'/'binding-fixture'; package.mkdir(parents=True)
        body = 'Use this procedure to preserve supplied text exactly.\n\nFixture marker: '+nonce+'\nUnicode note: 東京 / café\n'
        (package/'SKILL.md').write_text('---\nname: binding-fixture\ndescription: Preserve exact text from supplied guidance.\n---\n'+body)
        settings=Settings(agent_mode='standard',model=record['model'],effort='medium',network=False,
                          permission='workspace',confirm_writes=False,max_minutes=3,max_model_calls=6)
        store=Store(settings); sid=store.create(workspace)
        events=[]; started=time.monotonic()
        def emit(kind,text):
            events.append({'kind':kind,'text':redact(str(text)),'seconds':round(time.monotonic()-started,3)})
            if kind!='output': print(kind,redact(str(text))[:180],flush=True)
        async def allow(_): return True
        engine=Engine(settings,workspace,store,sid,emit,allow)
        prompt='Load the binding-fixture skill and save exactly its returned guidance text into guide.txt, preserving whitespace and Unicode. Do not change or create any other workspace files. Verify the saved file and reply exactly SAVED.'
        # Only the first plan is supplied by the test harness. The real controller
        # must observe this bad field, leave the target untouched, and replan.
        plan=Plan(mode='plan',message='Load the supplied guidance and save it.',actions=[
            Action(id='skill',tool='load_skill',arguments_json=json.dumps({'name':'binding-fixture'}),depends_on=[],purpose='Read supplied guidance',condition='always'),
            Action(id='save',tool='write_file',arguments_json=json.dumps({'path':'guide.txt','content':'${skill.content}'}),depends_on=['skill'],purpose='Save exact guidance',condition='always')],
            success_criteria=['guide.txt contains exactly the loaded skill guidance and no other files changed.'])
        before=manifest(workspace)
        try:
            answer=await engine.run(prompt,initial_plan=plan)
            record['answer']=answer
        except Exception as error:
            record.update(error_type=type(error).__name__,error=redact(str(error)))
        finally:
            record.update(seconds=round(time.monotonic()-started,3),generation_calls=engine.runtime.model_calls,
                          decision_calls=engine.judge.calls,jev_calls=0,events=events,
                          observations=json.loads(redact(json.dumps(engine.state.get('observations',[]),default=str))))
            record['trace']=[dict(row) for row in store.db.execute('SELECT kind,body FROM events WHERE session=? ORDER BY id',(sid,))]
            attempts=[o for o in engine.state.get('observations',[]) if o.get('action')=='save' and o.get('status')=='error']
            rejected=[store.read_evidence(sid,o['invocation_evidence_id']) for o in attempts]
            target=workspace/'guide.txt'
            result=target.read_bytes() if target.is_file() and not target.is_symlink() else None
            loaded=[o['result'] for o in engine.state.get('observations',[]) if o.get('tool')=='load_skill' and o.get('status')=='completed']
            expected=loaded[0]['guidance'].encode() if loaded else None
            violations=scope_changes(before,manifest(workspace),created=['guide.txt'])
            record.update(scope_violations=violations,expected_sha256=hashlib.sha256(expected).hexdigest() if expected else None,
                          saved_sha256=hashlib.sha256(result).hexdigest() if result else None,
                          failed_binding_not_dispatched=bool(rejected) and all(r['executor_called'] is False and r['executor_returned'] is False for r in rejected),
                          diagnostic_names_guidance=bool(attempts) and 'guidance' in attempts[0]['result'].get('error',''))
            record['passed']=bool(record.get('answer')=='SAVED' and result==expected and expected and not violations
                                  and record['failed_binding_not_dispatched'] and record['diagnostic_names_guidance'])
            try:
                await engine.close()
            except Exception as error:
                record.update(cleanup_error=redact(str(error)),passed=False)
            finally:
                store.close()
    output.write_text(json.dumps(record,indent=2))
    print(json.dumps({key:record.get(key) for key in ['passed','seconds','generation_calls','decision_calls','error_type','failed_binding_not_dispatched','diagnostic_names_guidance','scope_violations']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('benchmarks/results-reference-recovery.json'))
    asyncio.run(main(parser.parse_args().output))
