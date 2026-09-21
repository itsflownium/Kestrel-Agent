"""Benchmark-only fixtures and an independent saved-artifact oracle."""
import csv
from decimal import Decimal, InvalidOperation
import io
import json
import random


def fixture(seed=431031):
    rng = random.Random(seed)
    rows = [
        ['a', 'North', '1.25', 'settled'], ['b', 'South', '-2.50', 'settled'],
        ['c', 'North', '100', 'pending'], ['a', 'South', '999', 'settled'],
        ['d', 'North', 'bad', 'settled'], ['e', 'South', 'NaN', 'settled'],
        ['f', 'South', 'Infinity', 'settled'], ['g', 'West, café', '0.10', 'settled'],
        ['h', 'West, café', '0.20', 'settled'], ['d', 'North', '75', 'settled'],
        ['c', 'North', '33', 'settled'],
    ]
    for index in range(24):
        rows.append([f'r{index}', rng.choice(['North', 'South', 'West, café']),
                     str(Decimal(rng.randint(-10000, 10000)) / 100),
                     rng.choice(['settled', 'settled', 'pending'])])
    rows += [list(rows[index]) for index in rng.sample(range(len(rows)), 6)]
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['record_id', 'team', 'amount', 'state'])
    writer.writerows(rows)
    return stream.getvalue()


def expected_report(text):
    seen, totals = set(), {}
    included = duplicates = invalid = 0
    for row in csv.DictReader(io.StringIO(text)):
        key = row['record_id']
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        if row['state'] != 'settled':
            continue
        try:
            amount = Decimal(row['amount'])
        except InvalidOperation:
            invalid += 1
            continue
        if not amount.is_finite():
            invalid += 1
            continue
        included += 1
        totals[row['team']] = totals.get(row['team'], Decimal(0)) + amount
    return {'totals_by_team': totals, 'included': included, 'duplicates_ignored': duplicates, 'invalid_settled': invalid}


def grade_artifact(source, artifact, answer):
    def reject(value):
        raise ValueError('Non-finite JSON is not valid output.')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key.')
            result[key] = value
        return result
    expected = expected_report(source)
    actual = json.loads(artifact, parse_float=Decimal, parse_constant=reject, object_pairs_hook=pairs)
    if not isinstance(actual, dict) or actual.keys() != expected.keys():
        return False
    for key in ('included', 'duplicates_ignored', 'invalid_settled'):
        if type(actual[key]) is not int or actual[key] != expected[key]:
            return False
    totals = actual['totals_by_team']
    return (isinstance(totals, dict) and totals.keys() == expected['totals_by_team'].keys()
            and all(type(value) in (int, Decimal) and value == expected['totals_by_team'][key] for key, value in totals.items())
            and answer.strip() == 'SAVED')


def case():
    return {'id': 'data_reconciliation', 'revision': 1,
        'prompt': 'Reconcile ledger.csv in file order. For each record_id, keep only its first row BEFORE any filtering; later rows with that ID are duplicates even if the first row was invalid or pending. Include only first rows whose state is exactly settled and amount is a valid finite decimal number. Sum amount by team with exact decimal arithmetic. Create report.json with exactly these fields: totals_by_team (numeric totals for teams with included rows), included (number of included rows), duplicates_ignored (all later rows with repeated IDs), and invalid_settled (first settled rows with invalid or non-finite amounts). Counts must be integers. Do not modify ledger.csv or create any other files. Verify the saved report and reply exactly SAVED.',
        'files': {'ledger.csv': fixture()}, 'created_files': ['report.json']}
