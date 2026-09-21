"""Independent labels, split isolation, and recorded local promotion evidence."""
import hashlib
import json
import sqlite3


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def input_id(example):
    return digest({key: example[key] for key in ('state', 'question', 'options')})


def labeled_examples(examples):
    result = []
    for original in examples:
        if not isinstance(original, dict):
            raise ValueError('Each example must be an object.')
        example = dict(original)
        if not all(key in example for key in ('state', 'question', 'options')):
            raise ValueError('Each example requires state, question, and options.')
        if not isinstance(example['question'], str) or not example['question'].strip():
            raise ValueError('Question must be a nonempty string.')
        if not isinstance(example['options'], dict) or not example['options'] or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in example['options'].items()
        ):
            raise ValueError('Options must be a nonempty label-to-description object.')
        if not isinstance(example.get('family'), str) or not example['family'].strip():
            raise ValueError('Optimization examples require a nonempty family identifier.')
        label = example.get('label', {})
        if not isinstance(label, dict):
            raise ValueError('Label must be an object.')
        if label.get('kind') == 'exact_match':
            required = {'actual', 'expected', 'on_match', 'on_mismatch'}
            if not required <= label.keys():
                raise ValueError('Exact-match labels require actual, expected, on_match, and on_mismatch.')
            expected = label['on_match'] if digest(label['actual']) == digest(label['expected']) else label['on_mismatch']
            if example.get('expected', expected) != expected:
                raise ValueError('Declared label contradicts the supplied outcome.')
            example['expected'] = expected
        elif label.get('kind') == 'human':
            if not all(isinstance(label.get(k), str) and label[k].strip() for k in ('reviewer', 'reason')):
                raise ValueError('Human labels require reviewer and reason.')
        else:
            raise ValueError('Use an exact-match outcome label or a documented human label, not an agent verdict.')
        if example.get('expected') not in example['options']:
            raise ValueError('Outcome label must name an available option.')
        result.append(example)
    return result


def isolated_splits(train, validation, test):
    seen_inputs, seen_families = set(), set()
    for name, examples in [('train', train), ('validation', validation), ('test', test)]:
        inputs = {input_id(e) for e in examples}
        families = {e['family'] for e in examples}
        if len(inputs) != len(examples):
            raise ValueError(f'Duplicate inputs within {name}.')
        if inputs & seen_inputs or families & seen_families:
            raise ValueError('Train, validation, and test must have disjoint inputs and task families.')
        seen_inputs |= inputs
        seen_families |= families


def initialize(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS prompt_test_inputs(id TEXT PRIMARY KEY, run TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS prompt_test_families(id TEXT PRIMARY KEY, run TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS prompt_evaluations(id TEXT PRIMARY KEY, body TEXT NOT NULL);
    ''')


def reserve_test(db, run, examples):
    initialize(db)
    try:
        with db:
            db.executemany('INSERT INTO prompt_test_inputs VALUES(?,?)', [(input_id(e), run) for e in examples])
            db.executemany('INSERT INTO prompt_test_families VALUES(?,?)', [(family, run) for family in sorted({e['family'] for e in examples})])
    except sqlite3.IntegrityError as error:
        raise ValueError('This test input or family was already consumed. Supply a new untouched test set.') from error


def save_report(db, run, report):
    initialize(db)
    with db:
        db.execute('INSERT INTO prompt_evaluations VALUES(?,?)', (run, json.dumps(report, sort_keys=True)))


def promotion_report(db, candidate, current_instructions):
    initialize(db)
    row = db.execute('SELECT body FROM prompt_evaluations WHERE id=?', (candidate.get('evaluation_id'),)).fetchone()
    if row is None:
        raise ValueError('Candidate requires a recorded independent test evaluation; validation-only candidates cannot be promoted.')
    report = json.loads(row[0])
    if report['component'] != candidate.get('component') or report['candidate_hash'] != digest(candidate.get('instructions')):
        raise ValueError('Candidate does not match the evaluated prompt.')
    if report['baseline_hash'] != digest(current_instructions):
        raise ValueError('Active prompt changed since evaluation; evaluate against the current baseline.')
    if report['validation_candidate']['accuracy'] < report['validation_baseline']['accuracy']:
        raise ValueError('Candidate regressed on validation.')
    before, after = report['test_baseline']['results'], report['test_candidate']['results']
    if not before or len(before) != len(after):
        raise ValueError('Independent test evidence is incomplete.')
    if any(a['expected'] != b['expected'] for a, b in zip(before, after)):
        raise ValueError('Independent test labels do not align.')
    if any(a['correct'] and not b['correct'] for a, b in zip(before, after)):
        raise ValueError('Candidate regressed on a previously correct independent test example.')
    if report['test_candidate']['accuracy'] < report['test_baseline']['accuracy']:
        raise ValueError('Candidate regressed on independent test accuracy.')
    return report
