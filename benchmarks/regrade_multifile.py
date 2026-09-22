"""Regrade retained multi-file artifacts without rerunning either agent."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from kestrel_agent.config import Settings
from kestrel_agent.providers import Runtime
try:
    from benchmarks.multifile_coding import CHECK, grader_hash
except ModuleNotFoundError:
    from multifile_coding import CHECK, grader_hash

# Added after the initial task was frozen: diagnostic coverage of exactness
# beyond default Decimal precision. Never supplied to either agent.
LARGE_CHECK = r'''
import sys
sys.path.insert(0, '.')
from ledgerreport.parser import read_rows
from ledgerreport.summary import summarize
amount = '9' * 80 + '.99'
rows = read_rows(iter(['id,team,amount,status\n', 'a,Huge,' + amount + ',settled\n', 'b,Huge,0.01,settled\n']))
assert summarize(iter(rows)) == {'Huge': '1' + '0' * 80 + '.00'}
print('EXACT LARGE TOTAL PASS')
'''


async def main(source, output):
    records = json.loads(source.read_text())
    results = []
    with tempfile.TemporaryDirectory(prefix='kestrel-multifile-regrade-') as directory:
        root = Path(directory)
        os.environ['KESTREL_HOME'] = str(root/'state')
        for index, record in enumerate(records):
            workspace = root/str(index); workspace.mkdir()
            for name, content in record['artifacts'].items():
                relative = Path(name)
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('Artifact path escaped workspace')
                path = workspace/relative; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(content)
            runtime = Runtime(Settings(network=False,permission='workspace'),workspace,lambda *_:None)
            try:
                async with asyncio.timeout(60):
                    check = await runtime.command([sys.executable,'-I','-B','-c',CHECK],str(workspace),'grade-retained')
                    large = await runtime.command([sys.executable,'-I','-B','-c',LARGE_CHECK],str(workspace),'grade-large-exactness')
                verdict = json.loads(check.get('stdout','')) if check.get('exitCode') == 0 else {}
                results.append({'arm':record['arm'],'repetition':record['repetition'],
                    'original_run_passed':record['passed'],
                    'artifact_checks_passed':verdict == {'passed':True,'checks':334},
                    'large_exactness_passed':large.get('exitCode') == 0 and large.get('stdout','').strip() == 'EXACT LARGE TOTAL PASS',
                    'grader':check,'large_exactness':large,
                    'artifact_sha256':hashlib.sha256(json.dumps(record['artifacts'],sort_keys=True).encode()).hexdigest()})
            finally:
                await runtime.close()
    report = {'source':source.name,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
              'grader_sha256':grader_hash(),'large_check_sha256':hashlib.sha256(LARGE_CHECK.encode()).hexdigest(),
              'note':'Post-run artifact diagnostics do not turn an incomplete or timed-out agent run into a pass. Large-number exactness was added after the initial frozen protocol.',
              'results':results}
    output.write_text(json.dumps(report,indent=2))
    print(json.dumps([{key:r[key] for key in ('arm','repetition','original_run_passed','artifact_checks_passed','large_exactness_passed')} for r in results]))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('output',type=Path)
    args = parser.parse_args()
    asyncio.run(main(args.source,args.output))
