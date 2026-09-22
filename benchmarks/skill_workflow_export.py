"""Offline verification of bundled workflow evaluation and exact-version export."""
import hashlib
import json
import os
from pathlib import Path
import random
import tempfile

from kestrel_agent.config import Settings
from kestrel_agent.skill_registry import SkillRegistry
from kestrel_agent.skill_evaluation import evaluate, export
from kestrel_agent.store import Store
from kestrel_agent.workflow_templates import load


def main():
    rng=random.Random(784261)
    cases=[]
    for index in range(4):
        source=f'input-{rng.randrange(1000000)}.txt'
        destination=f'out-{index}/copy.txt'
        value=''.join(rng.choice('abXYZ é東京\t\n') for _ in range(80+index*37))+'\r\nend\r\n'
        cases.append({'name':f'varied-{index}','kind':'positive','parameters':{'source':source,'destination':destination},
            'files':{source:value},'expected_files':{source:value,destination:value},
            'expected_statuses':{'source':'completed','copy':'completed'}})
    cases.extend([
        {'name':'missing-input','kind':'negative','parameters':{'source':'missing.txt','destination':'copy.txt'},
         'files':{},'expected_files':{},'expected_statuses':{'source':'error','copy':'blocked'},'expected_errors':{'source':'No such file'}},
        {'name':'existing-output','kind':'negative','parameters':{'source':'input.txt','destination':'copy.txt'},
         'files':{'input.txt':'New content','copy.txt':'Keep existing content'},
         'expected_files':{'input.txt':'New content','copy.txt':'Keep existing content'},
         'expected_statuses':{'source':'completed','copy':'error'},'expected_errors':{'copy':'expected_sha256'}}])
    previous=os.environ.get('KESTREL_HOME')
    result={'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'fixture_seed':784261,'model_calls':0,'passed':False}
    try:
        with tempfile.TemporaryDirectory(prefix='kestrel-skill-export-smoke-') as directory:
            root=Path(directory);os.environ['KESTREL_HOME']=str(root/'state')
            path=root/'suite.json';path.write_text(json.dumps({'version':1,'cases':cases},ensure_ascii=False))
            settings=Settings(agent_mode='standard',network=False,shell=False)
            store=Store(settings)
            try:
                registry=SkillRegistry(settings,root/'workspace')
                tested=evaluate(registry,'workflow-designer','copy-text',path,store)
                installed=export(registry,'workflow-designer','copy-text',tested['evaluation_id'],store)
                same=load(installed['workflow_name'])==tested['evaluated_template']
                result.update(evaluation=tested,export=installed,installed_template_matches=same,
                    export_executed_task_actions=(root/'workspace').exists(),
                    passed=tested['passed'] and tested['export_eligible'] and same and not (root/'workspace').exists())
            finally: store.close()
    finally:
        if previous is None: os.environ.pop('KESTREL_HOME',None)
        else: os.environ['KESTREL_HOME']=previous
    Path('benchmarks/results-skill-workflow-export.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({key:result[key] for key in ['passed','model_calls','installed_template_matches','export_executed_task_actions']}))


if __name__=='__main__': main()
