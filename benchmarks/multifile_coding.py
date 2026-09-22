"""Frozen multi-file coding task and independent behavioral checks.

The agent receives only fixture() files and the user prompt, never CHECK.
"""
import hashlib
from pathlib import Path

SPEC = '''Repair the ledgerreport package across parser.py, summary.py and __main__.py.

read_rows(lines) in parser.py accepts a single-pass iterable of CSV text lines and returns a list of dictionaries. The header must contain exactly id, team, amount, status, in any order, with no duplicates. Header-only input returns []; missing/empty or wrong headers raise ValueError. Each row must have exactly four fields. Strip whitespace from every value. id/team must be nonempty, ids must be unique across ALL rows, and status must be exactly settled, pending or cancelled. amount must match -?[0-9]+(?:\\.[0-9]{1,2})? and be converted to Decimal, never float. Invalid input raises ValueError, including invalid amounts on non-settled rows. Preserve row order and Unicode/quoted CSV fields.

summarize(rows) in summary.py accepts a single-pass iterable of parsed rows. Return a dictionary of team -> fixed-two-decimal STRING total for settled rows only. Include a team with a zero total if it has settled rows, omit teams with only other statuses. Do not mutate rows; use exact decimal arithmetic.

python -B -m ledgerreport INPUT OUTPUT reads UTF-8 CSV and writes the summary as a UTF-8 JSON object. On success exit 0 and print exactly SAVED followed by newline. On invalid input or filesystem error exit 2, write an error: message to stderr and no stdout, preserve any existing output, and leave no temporary output files. On valid input replace OUTPUT atomically using a temporary file in its directory and os.replace; never truncate the destination before parsing/serialization succeeds. Do not create missing output directories. INPUT and OUTPUT are distinct existing/nonexisting regular file paths; same-path/symlink behavior is outside this task.

Edit only ledgerreport/parser.py, ledgerreport/summary.py and ledgerreport/__main__.py. Keep public names/signatures. Standard library only. Run python3 -B check_example.py and any further checks without leaving files behind. Do not modify this specification, the example checker or __init__.py. Do not create __pycache__ files (use -B). Report what changed and what checks you actually ran.
'''


def fixture():
    return {'id':'multifile_ledger', 'revision':1, 'prompt':'Implement the behavior specified in SPEC.md. Fix all three package modules and verify the result.',
            'files':{'SPEC.md':SPEC,
                     'ledgerreport/__init__.py':'"""Small ledger reporting package."""\n',
                     'ledgerreport/parser.py':'''import csv

def read_rows(lines):
    return [dict(row, amount=float(row['amount'])) for row in csv.DictReader(lines)]
''',
                     'ledgerreport/summary.py':'''def summarize(rows):
    totals = {}
    for row in rows:
        totals[row['team']] = totals.get(row['team'], 0) + row['amount']
    return totals
''',
                     'ledgerreport/__main__.py':'''import json
import sys
from .parser import read_rows
from .summary import summarize

with open(sys.argv[2], 'w') as output:
    with open(sys.argv[1]) as source:
        json.dump(summarize(read_rows(source)), output)
print('DONE')
''',
                     'check_example.py':'''from decimal import Decimal
from ledgerreport.parser import read_rows
from ledgerreport.summary import summarize
rows = read_rows(iter(['id,team,amount,status\\n', 'a,East,0.10,settled\\n', 'b,East,0.20,settled\\n', 'c,West,99,pending\\n']))
assert rows[0]['amount'] == Decimal('0.10')
assert summarize(iter(rows)) == {'East': '0.30'}
print('EXAMPLE PASS')
'''}, 'editable_files':['ledgerreport/parser.py','ledgerreport/summary.py','ledgerreport/__main__.py']}


CHECK = r'''
import csv, io, json, os, random, subprocess, sys, tempfile
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, '.')
from ledgerreport.parser import read_rows
from ledgerreport.summary import summarize
class Once:
    def __init__(self, values): self.values, self.used = values, False
    def __iter__(self):
        assert not self.used, 'iterated input twice'
        self.used = True
        return iter(self.values)
rng = random.Random(824915)
checks = 0
for trial in range(100):
    keys = ['id','team','amount','status']; rng.shuffle(keys)
    stream = io.StringIO(newline=''); writer = csv.DictWriter(stream, fieldnames=keys)
    writer.writeheader(); expected = []; cents_by_team = {}
    for index in range(rng.randrange(1,30)):
        team = rng.choice(['East','東京','équipe','A,B','quoted "team"'])
        cents = rng.randrange(-99999999999999999, 99999999999999999)
        amount = ('-' if cents < 0 else '') + str(abs(cents)//100) + '.' + f'{abs(cents)%100:02d}'
        status = rng.choice(['settled','pending','cancelled'])
        row = {'id':f'{trial}-{index}', 'team':team, 'amount':amount, 'status':status}
        writer.writerow({key:' '+value+' ' for key,value in row.items()})
        expected.append(dict(row, amount=Decimal(amount)))
        if status == 'settled': cents_by_team[team] = cents_by_team.get(team,0)+cents
    actual = read_rows(Once(stream.getvalue().splitlines(keepends=True)))
    assert actual == expected and all(type(r['amount']) is Decimal for r in actual), 'parsed row mismatch'
    before = deepcopy(actual)
    truth = {team:format(Decimal(cents)/100,'.2f') for team,cents in cents_by_team.items()}
    assert summarize(Once(actual)) == truth, 'wrong aggregate'
    assert actual == before, 'mutated rows'
    checks += 3
for text in ['', 'id,team,amount\na,E,1\n', 'id,team,amount,status,status\na,E,1,settled,settled\n',
             'id,team,amount,status\na,E,1,settled,extra\n', 'id,team,amount,status\na,E,1\n',
             'id,team,amount,status\n,E,1,settled\n', 'id,team,amount,status\na, ,1,settled\n',
             'id,team,amount,status\na,E,1,unknown\n',
             'id,team,amount,status\na,E,1,pending\na,E,2,settled\n']:
    try: read_rows(Once(text.splitlines(keepends=True)))
    except ValueError: pass
    else: raise AssertionError('accepted invalid CSV')
    checks += 1
for amount in ['NaN','Infinity','1e2','+1','1.234','.50','1.','--1','']:
    try: read_rows(iter(['id,team,amount,status\n',f'a,E,{amount},pending\n']))
    except ValueError: pass
    else: raise AssertionError('accepted invalid amount')
    checks += 1
assert read_rows(iter(['status,amount,team,id\n'])) == []
assert summarize(iter([])) == {}
assert summarize(iter([{'team':'Z','amount':Decimal('1.25'),'status':'settled'}, {'team':'Z','amount':Decimal('-1.25'),'status':'settled'}])) == {'Z':'0.00'}
checks += 3
workspace = Path.cwd()
with tempfile.TemporaryDirectory(prefix='grader-', dir=workspace) as temp:
    root = Path(temp); source = root/'input.csv'; target = root/'output.json'
    source.write_text('id,team,amount,status\na,東京,0.10,settled\nb,東京,0.20,settled\nc,E,9,pending\n',encoding='utf-8')
    def run(*args):
        return subprocess.run([sys.executable,'-B','-m','ledgerreport',*map(str,args)],cwd=workspace,capture_output=True,text=True,timeout=10)
    target.write_bytes(b'old bytes')
    result = run(source,target)
    assert result.returncode == 0 and result.stdout == 'SAVED\n' and result.stderr == '', (result.returncode,result.stdout,result.stderr)
    assert json.loads(target.read_text()) == {'東京':'0.30'}
    assert {p.name for p in root.iterdir()} == {'input.csv','output.json'}
    checks += 3
    target.write_bytes(b'preserve this output')
    source.write_text('id,team,amount,status\na,E,1.234,settled\n')
    result = run(source,target)
    assert result.returncode == 2 and result.stdout == '' and result.stderr.startswith('error:'), (result.returncode,result.stdout,result.stderr)
    assert target.read_bytes() == b'preserve this output'
    assert {p.name for p in root.iterdir()} == {'input.csv','output.json'}
    checks += 3
    result = run(root/'absent.csv',target)
    assert result.returncode == 2 and result.stdout == '' and result.stderr.startswith('error:')
    assert target.read_bytes() == b'preserve this output'
    checks += 2
    source.write_text('id,team,amount,status\na,E,1,settled\n')
    result = run(source,root/'missing'/'out.json')
    assert result.returncode == 2 and result.stdout == '' and result.stderr.startswith('error:')
    assert not (root/'missing').exists()
    checks += 2
    # Execute the entrypoint under controlled replacement failure: atomic write
    # must be attempted, and an exception must leave old bytes/no temp files.
    import runpy
    replacements = []
    def fail_replace(*args, **kwargs):
        replacements.append(args)
        assert Path(args[0]).parent.resolve() == target.parent.resolve()
        raise OSError('injected replace failure')
    captured_out, captured_err = io.StringIO(), io.StringIO()
    from contextlib import redirect_stdout, redirect_stderr
    with patch('os.replace',fail_replace), patch.object(sys,'argv',['ledgerreport',str(source),str(target)]), redirect_stdout(captured_out), redirect_stderr(captured_err):
        try: runpy.run_module('ledgerreport',run_name='__main__')
        except SystemExit as exc: code = exc.code
        else: code = 0
    assert replacements and code == 2 and captured_out.getvalue() == '' and captured_err.getvalue().startswith('error:')
    assert target.read_bytes() == b'preserve this output'
    assert {p.name for p in root.iterdir()} == {'input.csv','output.json'}
    checks += 3
print(json.dumps({'passed':True,'checks':checks},sort_keys=True))
'''


def grader_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
