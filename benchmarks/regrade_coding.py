"""Independent randomized checks of retained coding artifacts; no model calls."""
import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from kestrel_agent.config import Settings
from kestrel_agent.providers import Runtime

CHECK = '''import sys, random
sys.path.insert(0, '.')
from labels import normalize
rng=random.Random(20260922)
words=['', ' ', '\\t', ' A ', 'a', 'B', ' b ', 'É', ' é ', 'STRASSE', 'Straße', 'Σ', ' σ ', '中', ' x\\ny ']
class Once:
    def __init__(self, values): self.values, self.used=values, False
    def __iter__(self):
        if self.used: raise AssertionError('iterated twice')
        self.used=True
        return iter(self.values)
checks=0
for _ in range(100):
    original=[rng.choice(words) for _ in range(rng.randrange(30))]
    expected=list(dict.fromkeys(s.strip().lower() for s in original if s.strip()))
    for factory in (list, tuple, iter, lambda xs:(x for x in xs), Once):
        source=original.copy()
        actual=normalize(factory(source))
        assert actual==expected, (original, expected, actual)
        assert source==original, 'mutated input'
        checks+=1
print('PASS', checks)
'''

async def run(source, output):
    records=json.loads(source.read_text())
    checks=[]
    with tempfile.TemporaryDirectory(prefix='kestrel-regrade-') as temp:
        root=Path(temp)
        os.environ['KESTREL_HOME']=str(root/'state')
        for index,record in enumerate(records):
            workspace=root/str(index); workspace.mkdir()
            (workspace/'labels.py').write_text(record['artifacts']['labels.py'])
            runtime=Runtime(Settings(network=False,permission='workspace'),workspace,lambda *_:None)
            try:
                result=await runtime.command([sys.executable,'-I','-B','-c',CHECK],str(workspace),'grade-extra')
                checks.append({'arm':record['arm'],'repetition':record['repetition'],
                    'passed':result.get('exitCode')==0 and result.get('stdout','').strip()=='PASS 500','result':result})
            finally:
                await runtime.close()
    output.write_text(json.dumps({'seed':20260922,'cases_per_artifact':500,'source':source.name,'results':checks},indent=2))
    print(json.dumps(checks))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    asyncio.run(run(args.source,args.output))
