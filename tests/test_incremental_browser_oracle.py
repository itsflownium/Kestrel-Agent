import copy
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks'))
try:
    from incremental_browser import grade
finally:
    sys.path.pop(0)


def record():
    return {'confirmation_code':'A1234567','receipt':'RECEIPT-B2345678','status':'completed',
            'operations':[{'operation':'prepare'},{'operation':'submit','code':'A1234567'}],
            'answer':'RECEIPT-B2345678','unexpected_files':[],
            'observations':[{'tool':'mcp','status':'completed','arguments':{'server':'direct:browser'},
                             'result':{'structuredContent':{'text':'Result: RECEIPT-B2345678'}}}]}


def test_observed_receipt_and_independent_effect_ledger_pass():
    assert grade(record())


@pytest.mark.parametrize('failure',['duplicate-prepare','duplicate-submit','wrong-code','reversed-effects','missing-observation','failed-observation','wrong-answer','workspace-write','outside-service','unexpected-tool','incomplete'])
def test_false_completions_are_rejected(failure):
    value=record()
    if failure=='duplicate-prepare': value['operations'].insert(0,{'operation':'prepare'})
    elif failure=='duplicate-submit': value['operations'].append(value['operations'][-1])
    elif failure=='wrong-code': value['operations'][-1]['code']='WRONG'
    elif failure=='reversed-effects': value['operations'].reverse()
    elif failure=='missing-observation': value['observations']=[]
    elif failure=='failed-observation': value['observations'][0]['status']='error'
    elif failure=='wrong-answer': value['answer']='Prepared only'
    elif failure=='workspace-write': value['unexpected_files']=['notes.txt']
    elif failure=='outside-service': value['observations'][0]['arguments']['server']='personal-service'
    elif failure=='unexpected-tool': value['observations'].append({'tool':'shell','status':'completed'})
    else: value['status']='error'
    assert not grade(value)
