import json
import random
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kestrel_agent.workflow_eval import evaluate_files, Suite, validate_plans
from kestrel_agent.workflow_templates import read
from kestrel_agent.cli import app

ROOT = Path(__file__).parents[1]
TEMPLATE = ROOT/'examples/workflows/copy-text.json'
SUITE = ROOT/'examples/workflows/copy-text.tests.json'


def test_real_fixture_worker_preserves_parent_home_and_passes_oracles(tmp_path, monkeypatch):
    private = tmp_path/'private'
    private.mkdir()
    sentinel = private/'sessions.sqlite3'
    sentinel.write_bytes(b'untouched user storage')
    monkeypatch.setenv('KESTREL_HOME', str(private))
    before = {p.name: p.read_bytes() for p in private.iterdir()}
    result = evaluate_files(TEMPLATE, SUITE)
    assert result['passed'], result
    assert result['positive_cases'] == result['negative_cases'] == 2
    assert result['certification'] == 'not_certified'
    assert len(result['template_sha256']) == len(result['suite_sha256']) == 64
    assert before == {p.name: p.read_bytes() for p in private.iterdir()}


@pytest.mark.parametrize('mutation', ['wrong-artifact', 'wrong-error', 'extra-file', 'failed-contract'])
def test_bad_template_or_expectation_cannot_pass(tmp_path, mutation):
    template = read(TEMPLATE)
    suite = json.loads(SUITE.read_text())
    if mutation == 'wrong-artifact':
        suite['cases'][0]['expected_files']['saved/copy.txt'] = 'incorrect'
    elif mutation == 'wrong-error':
        suite['cases'][2]['expected_errors']['source'] = 'unrelated cause'
    elif mutation == 'extra-file':
        template['actions'].append({'id':'extra', 'tool':'write_file', 'arguments':{'path':'unexpected.txt','content':'extra','expected_sha256':None},'depends_on':[],'condition':'always','purpose':'Unexpected extra file'})
        for case in suite['cases']:
            case['expected_statuses']['extra'] = 'completed'
    else:
        template['completion_checks'] = [{'id':'copy_exact','requirement':'Exact output','kind':'file_text_equals','source':'saved/copy.txt','expected':'wrong'}]
    path = tmp_path/'template.json'
    path.write_text(json.dumps(template))
    fixtures = tmp_path/'suite.json'
    fixtures.write_text(json.dumps(suite))
    result = evaluate_files(path, fixtures)
    assert not result['passed'], result


@pytest.mark.parametrize('path', ['../escape', '/tmp/escape', 'a//b', 'a/./b', 'a\\b'])
def test_fixture_paths_cannot_escape_or_alias(path):
    suite = json.loads(SUITE.read_text())
    suite['cases'][0]['files'] = {path:'bad'}
    with pytest.raises(ValueError):
        Suite.model_validate(suite)


def test_model_or_external_tools_are_rejected_before_worker(tmp_path):
    template = read(TEMPLATE)
    template['actions'][0] = {'id':'source','tool':'shell','arguments':{'command':'touch /tmp/not-allowed'},'depends_on':[],'condition':'always','purpose':'disallowed'}
    with pytest.raises(ValueError):
        validate_plans(template, Suite.model_validate_json(SUITE.read_text()))
    template = read(TEMPLATE)
    template['actions'][0]['condition'] = 'ask a model to decide'
    with pytest.raises(ValueError, match='unconditional'):
        validate_plans(template, Suite.model_validate_json(SUITE.read_text()))


def test_cli_returns_failure_for_bad_fixture(tmp_path):
    suite = json.loads(SUITE.read_text())
    suite['cases'] = suite['cases'][:1]
    suite['cases'][0]['expected_files'] = {}
    path = tmp_path/'bad.json'
    path.write_text(json.dumps(suite))
    result = CliRunner().invoke(app, ['workflows','test',str(TEMPLATE),str(path)])
    assert result.exit_code == 1
    assert json.loads(result.stdout)['passed'] is False


def test_new_parameters_are_executed_with_the_same_template(tmp_path):
    rng = random.Random(67289)
    cases = []
    for index in range(4):
        source, destination = f'input-{rng.randrange(100000)}.txt', f'output-{index}/notes.txt'
        text = ''.join(rng.choice('abcXYZ é東京\t\n ') for _ in range(150 + index)) + '\r\nCRLF stays intact\r\n'
        cases.append({'name':f'generated-{index}','kind':'positive',
                      'parameters':{'source':source,'destination':destination},
                      'files':{source:text},'expected_files':{source:text,destination:text},
                      'expected_statuses':{'source':'completed','copy':'completed'}})
    path = tmp_path/'new-inputs.json'
    path.write_text(json.dumps({'version':1,'cases':cases}))
    report = evaluate_files(TEMPLATE, path)
    assert report['passed'], report
    assert report['positive_cases'] == 4
    assert report['certification'] == 'not_certified'
