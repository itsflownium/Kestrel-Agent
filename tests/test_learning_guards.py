import copy
import sqlite3

import pytest

from kestrel_agent.learning_guards import (
    digest, isolated_splits, labeled_examples, promotion_report, reserve_test, save_report,
)


def example(family='one', question='Ready?'):
    return dict(state={}, question=question, options={'yes': 'Accept', 'no': 'Reject'},
                expected='yes', family=family,
                label={'kind': 'human', 'reviewer': 'tester', 'reason': 'Observed outcome'})


def test_outcome_labels_are_derived_with_type_sensitive_equality():
    row = example()
    row.pop('expected')
    row['label'] = dict(kind='exact_match', actual=True, expected=1, on_match='yes', on_mismatch='no')
    assert labeled_examples([row])[0]['expected'] == 'no'
    row['expected'] = 'yes'
    with pytest.raises(ValueError, match='contradicts'):
        labeled_examples([row])


@pytest.mark.parametrize('change', [
    {'family': ''}, {'label': None}, {'label': {'kind': 'agent'}},
    {'label': {'kind': 'human'}}, {'options': []}, {'question': ''},
    {'expected': 'unknown'},
])
def test_invalid_labels_fail_closed(change):
    with pytest.raises(ValueError):
        labeled_examples([example() | change])


def test_invalid_example_shape():
    for value in [None, [], {}, {'family': 'a'}]:
        with pytest.raises(ValueError):
            labeled_examples([value])


def test_family_and_input_isolation():
    a, b, c = example(), example('two', 'Next?'), example('three', 'Done?')
    isolated_splits([a], [b], [c])
    for train, validation, test in [([a, a], [b], [c]), ([a], [b | {'family': 'one'}], [c]),
                                     ([a], [b], [a | {'family': 'new', 'expected': 'no'}])]:
        with pytest.raises(ValueError):
            isolated_splits(train, validation, test)


def test_consumed_test_families_and_atomic_reservation():
    db = sqlite3.connect(':memory:')
    reserve_test(db, 'first', [example()])
    with pytest.raises(ValueError, match='consumed'):
        reserve_test(db, 'second', [example('new', 'New?'), example('one', 'Different?')])
    assert db.execute('SELECT COUNT(*) FROM prompt_test_inputs').fetchone()[0] == 1
    reserve_test(db, 'third', [example('new', 'New?')])
    with pytest.raises(ValueError):
        reserve_test(db, 'fourth', [example('other')])


def report():
    score = {'accuracy': 1, 'results': [{'expected': 'yes', 'correct': True}]}
    return dict(component='verify', candidate_hash=digest('new'), baseline_hash=digest('old'),
                validation_baseline=copy.deepcopy(score), validation_candidate=copy.deepcopy(score),
                test_baseline=copy.deepcopy(score), test_candidate=copy.deepcopy(score))


def candidate():
    return dict(component='verify', instructions='new', evaluation_id='run', validation_accuracy=999)


def test_recorded_report_and_exact_prompt_required():
    db = sqlite3.connect(':memory:')
    with pytest.raises(ValueError, match='recorded'):
        promotion_report(db, candidate(), 'old')
    save_report(db, 'run', report())
    assert promotion_report(db, candidate(), 'old')['component'] == 'verify'
    with pytest.raises(ValueError, match='match'):
        promotion_report(db, candidate() | {'instructions': 'edited'}, 'old')
    with pytest.raises(ValueError, match='changed'):
        promotion_report(db, candidate(), 'different')
    with pytest.raises(sqlite3.IntegrityError):
        save_report(db, 'run', report())


@pytest.mark.parametrize('kind', ['validation', 'paired', 'empty', 'misaligned'])
def test_regression_or_incomplete_evidence_blocks_promotion(kind):
    db = sqlite3.connect(':memory:')
    evidence = report()
    if kind == 'validation':
        evidence['validation_candidate']['accuracy'] = 0
    elif kind == 'paired':
        evidence['test_candidate']['results'][0]['correct'] = False
    elif kind == 'empty':
        evidence['test_candidate']['results'] = []
    else:
        evidence['test_candidate']['results'][0]['expected'] = 'no'
    save_report(db, 'run', evidence)
    with pytest.raises(ValueError):
        promotion_report(db, candidate(), 'old')


def test_optimizer_keeps_final_test_out_of_selection_and_requires_explicit_activation(tmp_path, monkeypatch):
    import json
    import sys
    from types import SimpleNamespace
    from kestrel_agent import learning
    from kestrel_agent.config import Settings
    from kestrel_agent.store import Store

    monkeypatch.setenv('KESTREL_HOME', str(tmp_path / 'home'))
    paths = []
    for name in ('train', 'validation', 'test'):
        path = tmp_path / f'{name}.jsonl'
        path.write_text(json.dumps(example(name, name)))
        paths.append(path)
    calls = []

    def optimize(**kwargs):
        assert [e['family'] for e in kwargs['trainset']] == ['train']
        assert [e['family'] for e in kwargs['valset']] == ['validation']
        calls.append('selected')
        return SimpleNamespace(best_candidate={'instructions': 'new'})

    async def evaluate(settings, examples, instructions, emit):
        assert calls[0] == 'selected'
        calls.append((examples[0]['family'], instructions))
        return {'accuracy': 1, 'examples': 1, 'results': [{'expected': 'yes', 'actual': 'yes', 'correct': True}]}

    monkeypatch.setitem(sys.modules, 'gepa', SimpleNamespace(optimize=optimize))
    monkeypatch.setattr(learning, 'evaluate', evaluate)
    settings = Settings()
    destination = learning.optimize(settings, paths[0], paths[1], 'verify', 10, lambda *a: None, test_path=paths[2])
    assert [entry[0] for entry in calls[1:]] == ['validation', 'validation', 'test', 'test']
    store = Store(settings)
    try:
        assert store.template('verify', learning.VERIFY_PROMPT) == learning.VERIFY_PROMPT
        promotion_report(store.db, json.loads(destination.read_text()), learning.VERIFY_PROMPT)
    finally:
        store.close()
    with pytest.raises(ValueError, match='consumed'):
        learning.optimize(settings, paths[0], paths[1], 'verify', 10, lambda *a: None, test_path=paths[2])
