import json
from decimal import Decimal

import pytest
from benchmarks.data_reconciliation import expected_report, fixture, grade_artifact


SOURCE = 'record_id,team,amount,state\na,X,bad,settled\na,X,10,settled\nb,X,0.10,settled\nc,X,0.20,settled\nd,Y,NaN,settled\ne,Y,4,pending\ne,Y,8,settled\n'
VALID = '{"totals_by_team":{"X":0.30},"included":2,"duplicates_ignored":2,"invalid_settled":2}'


def test_oracle_deduplicates_before_filtering_and_sums_exactly():
    assert expected_report(SOURCE) == {'totals_by_team': {'X': Decimal('0.30')}, 'included': 2, 'duplicates_ignored': 2, 'invalid_settled': 2}
    assert grade_artifact(SOURCE, VALID, 'SAVED')
    assert fixture(1) != fixture(2)
    assert expected_report(fixture())['invalid_settled'] == 3


@pytest.mark.parametrize('field,value', [('included', True), ('included', 2.0), ('duplicates_ignored', 0), ('invalid_settled', 0), ('totals_by_team', {'X': '0.30'}), ('totals_by_team', {'X': 10.3}), ('totals_by_team', {'X': 0.30000000000000004}), ('totals_by_team', {'X': 0.3, 'Y': 0})])
def test_grader_rejects_plausible_but_wrong_reports(field, value):
    wrong = json.loads(VALID)
    wrong[field] = value
    assert not grade_artifact(SOURCE, json.dumps(wrong), 'SAVED')


def test_grader_rejects_nonfinite_duplicate_keys_and_claim_without_artifact():
    for text in [VALID.replace('0.30', 'NaN'), VALID.replace('"included":2', '"included":2,"included":2')]:
        with pytest.raises(ValueError):
            grade_artifact(SOURCE, text, 'SAVED')
    assert not grade_artifact(SOURCE, '{}', 'SAVED')
    assert not grade_artifact(SOURCE, VALID, 'I would save the report.')
