"""Positive control and false-pass controls for the unseen coding-task grader."""
import json
import subprocess
import sys

import pytest

from benchmarks.multifile_coding import CHECK, fixture

PARSER = '''import csv, re
from decimal import Decimal

def read_rows(lines):
    reader = csv.reader(lines)
    keys = next(reader, None)
    if keys is None or len(keys) != 4 or set(keys) != {'id','team','amount','status'}: raise ValueError('header')
    result, seen = [], set()
    for fields in reader:
        if len(fields) != 4: raise ValueError('row')
        row = dict(zip(keys, (v.strip() for v in fields)))
        if not row['id'] or not row['team'] or row['id'] in seen: raise ValueError('id/team')
        if row['status'] not in {'settled','pending','cancelled'}: raise ValueError('status')
        if not re.fullmatch(r'-?[0-9]+(?:\\.[0-9]{1,2})?',row['amount']): raise ValueError('amount')
        seen.add(row['id'])
        row['amount'] = Decimal(row['amount'])
        result.append(row)
    return result
'''
SUMMARY = '''from decimal import Decimal

def summarize(rows):
    result = {}
    for row in rows:
        if row['status'] == 'settled': result[row['team']] = result.get(row['team'],Decimal(0)) + row['amount']
    return {key:format(value,'.2f') for key,value in result.items()}
'''
CLI = '''import json, os, sys, tempfile
from pathlib import Path
from .parser import read_rows
from .summary import summarize

def main():
    temp = None
    try:
        with open(sys.argv[1],encoding='utf-8',newline='') as source: body = json.dumps(summarize(read_rows(source)),ensure_ascii=False)
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=Path(sys.argv[2]).parent,delete=False) as output:
            temp = output.name
            output.write(body)
        os.replace(temp,sys.argv[2])
        print('SAVED')
        return 0
    except (ValueError,OSError) as error:
        print('error: '+str(error),file=sys.stderr)
        return 2
    finally:
        if temp and os.path.exists(temp): os.unlink(temp)
if __name__ == '__main__': raise SystemExit(main())
'''


@pytest.mark.parametrize('mutation', ['none','float','all-statuses','truncate-first','no-replace','leak-temp','duplicate-ids','invalid-pending'])
def test_independent_coding_oracle(tmp_path, mutation):
    files = fixture()['files']
    files.update({'ledgerreport/parser.py':PARSER,'ledgerreport/summary.py':SUMMARY,'ledgerreport/__main__.py':CLI})
    if mutation == 'float': files['ledgerreport/parser.py'] = PARSER.replace("Decimal(row['amount'])", "float(row['amount'])")
    if mutation == 'all-statuses': files['ledgerreport/summary.py'] = SUMMARY.replace("row['status'] == 'settled'", 'True')
    if mutation == 'truncate-first': files['ledgerreport/__main__.py'] = CLI.replace('    temp = None', "    Path(sys.argv[2]).write_text('')\n    temp = None")
    if mutation == 'no-replace': files['ledgerreport/__main__.py'] = CLI.replace('os.replace(temp,sys.argv[2])', "Path(sys.argv[2]).write_text(body)")
    if mutation == 'leak-temp': files['ledgerreport/__main__.py'] = CLI.replace('if temp and os.path.exists(temp): os.unlink(temp)', 'pass')
    if mutation == 'duplicate-ids': files['ledgerreport/parser.py'] = PARSER.replace(" or row['id'] in seen", '')
    if mutation == 'invalid-pending': files['ledgerreport/parser.py'] = PARSER.replace("        if not re.fullmatch", "        if row['status'] != 'settled': continue\n        if not re.fullmatch")
    for name, body in files.items():
        path = tmp_path/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(body)
    result = subprocess.run([sys.executable,'-I','-B','-c',CHECK],cwd=tmp_path,text=True,capture_output=True,timeout=30)
    if mutation == 'none':
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {'passed':True,'checks':334}
    else:
        assert result.returncode != 0, mutation
