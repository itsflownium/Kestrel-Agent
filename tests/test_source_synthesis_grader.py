import json
import pytest
from benchmarks.source_synthesis import fixture, expected, grade_sources


@pytest.mark.parametrize('seed', [19073, 73921, 12, 498])
def test_authority_versioning_and_unknown_field(seed):
    case = fixture(seed)
    truth = expected(case['files'])
    assert grade_sources(case['files'], json.dumps(truth), 'SAVED')
    assert truth['customer_count'] == {'value':None,'source':None,'quote':None}
    for key in ['launch_date','budget_usd','owner']:
        assert truth[key]['quote'] in case['files'][truth[key]['source']].splitlines()
        assert 'Status: APPROVED' in case['files'][truth[key]['source']]
    assert truth['budget_usd']['source'] != truth['owner']['source']


@pytest.mark.parametrize('mutation', ['value','citation','quote','unknown','float','bool','extra','reply'])
def test_incorrect_or_unsupported_claims_fail(mutation):
    case = fixture()
    value = expected(case['files'])
    answer = 'SAVED'
    if mutation == 'value': value['owner']['value'] = 'Invented'
    elif mutation == 'citation': value['owner']['source'] = value['budget_usd']['source']
    elif mutation == 'quote': value['owner']['quote'] += ' not actually quoted'
    elif mutation == 'unknown': value['customer_count']['value'] = 999
    elif mutation == 'float': value['budget_usd']['value'] = float(value['budget_usd']['value'])
    elif mutation == 'bool': value['budget_usd']['value'] = True
    elif mutation == 'extra': value['summary'] = 'Extra'
    else: answer = 'Proposed, not saved'
    assert not grade_sources(case['files'], json.dumps(value), answer)


def test_duplicate_keys_are_not_accepted():
    case = fixture()
    good = json.dumps(expected(case['files']))
    bad = good[:-1] + ',"owner":' + json.dumps(expected(case['files'])['owner']) + '}'
    assert not grade_sources(case['files'], bad, 'SAVED')


def test_oracle_matches_hand_authored_per_field_authority_example():
    files = {
        'old.md':'Document-ID: old.md\nIssued: 2026-09-01\nStatus: APPROVED\n\n- owner: Alice\n- budget_usd: 100\n- launch_date: 2026-10-01\n',
        'new.md':'Document-ID: new.md\nIssued: 2026-09-10\nStatus: APPROVED\n\n- budget_usd: 200\n',
        'draft.md':'Document-ID: draft.md\nIssued: 2026-09-19\nStatus: DRAFT\n\n- owner: Mallory\n- customer_count: 123\n',
        'future.md':'Document-ID: future.md\nIssued: 2026-09-21\nStatus: APPROVED\n\n- owner: Future\n- customer_count: 456\n',
    }
    assert expected(files) == {
        'owner':{'value':'Alice','source':'old.md','quote':'- owner: Alice'},
        'budget_usd':{'value':200,'source':'new.md','quote':'- budget_usd: 200'},
        'launch_date':{'value':'2026-10-01','source':'old.md','quote':'- launch_date: 2026-10-01'},
        'customer_count':{'value':None,'source':None,'quote':None},
    }
