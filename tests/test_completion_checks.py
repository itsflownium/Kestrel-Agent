import json
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from kestrel_agent.completion import CompletionCheck, evaluate, register
from kestrel_agent.config import Settings
from kestrel_agent.engine import Engine
from kestrel_agent.schema import Plan
from kestrel_agent.store import Store


def check(**kwargs):
    return CompletionCheck(**(dict(id='exit', requirement='Command exits zero', kind='result_equals', source='${run.exitCode}', expected_json='0') | kwargs))


@pytest.mark.parametrize('overrides', [dict(source='literal'), dict(expected_json='NaN'), dict(expected_json='{"a":1,"a":2}'), dict(kind='file_text_equals', source='out', expected_json='1')])
def test_invalid_contracts(overrides):
    with pytest.raises(ValidationError):
        check(**overrides)


@pytest.mark.asyncio
@pytest.mark.parametrize('status,value,passes', [('completed', 0, True), ('error', 2, False), ('uncertain', 0, False), ('skip', 0, False), ('completed', False, False)])
async def test_exact_results_and_definite_execution(status, value, passes):
    state = {'statuses': {'run': status}, 'results': {'run': {'exitCode': value}}}
    register(state, [check()])
    failed = await evaluate(state, None, {'exit'})
    assert (not failed) == passes


@pytest.mark.asyncio
async def test_expected_nonzero_outcome_can_pass_without_reclassifying_command():
    state = {'statuses': {'run': 'error'}, 'results': {'run': {'exitCode': 2}}}
    register(state, [check(expected_json='2')])
    assert not await evaluate(state, None, {'exit'})
    assert state['statuses']['run'] == 'error'


def test_contract_cannot_be_weakened_on_repair():
    state = {}
    register(state, [check()])
    with pytest.raises(ValueError, match='Cannot weaken'):
        register(state, [check(expected_json='2')])
    register(state, [check(source='${retry.exitCode}')])
    assert state['completion_checks']['exit']['check']['source'] == '${retry.exitCode}'


@pytest.mark.asyncio
async def test_omitting_failed_check_does_not_erase_it():
    state = {}
    register(state, [check()])
    register(state, [])
    assert 'exit' in await evaluate(state, None, set())


@pytest.mark.asyncio
async def test_files_are_fresh_permission_checked_and_require_complete_text(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'state'))
    settings = Settings()
    store = Store(settings)
    engine = Engine(settings, tmp_path, store, store.create(tmp_path), lambda *a: None, AsyncMock())
    artifact = tmp_path/'out.json'
    artifact.write_text('{"a": 1}')
    state = {}
    register(state, [check(kind='file_json_equals', source='out.json', expected_json='{"a":1}')])
    try:
        assert not await evaluate(state, engine.tools, {'exit'})
        artifact.write_text('{"a":2}')
        assert await evaluate(state, engine.tools, set())
        artifact.write_text('x'*40001)
        assert await evaluate(state, engine.tools, set())
        register(state, [check(id='outside', kind='file_text_equals', source='/etc/passwd', expected_json='"x"')])
        assert 'outside' in await evaluate(state, engine.tools, {'outside'})
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
async def test_jev_success_cannot_override_contract_failure(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'state'))
    settings = Settings()
    store = Store(settings)
    engine = Engine(settings, tmp_path, store, store.create(tmp_path), lambda *a: None, AsyncMock())
    engine.state.update(request='Read exact text', steps=0, observations=[], plan=None)
    plan = Plan.model_validate(dict(mode='plan', message='Read', actions=[dict(id='run', tool='read_file', arguments_json='{"path":"in.txt"}', depends_on=[], purpose='Read', condition='always')], success_criteria=[], completion_checks=[check(source='${run.raw_text}', expected_json='"required"').model_dump()]))
    clarification = Plan(mode='clarify', message='The observed text differs.', actions=[], success_criteria=[])
    engine.make_plan = AsyncMock(side_effect=[plan, clarification])
    async def perform(action):
        engine.state['steps'] += 1
        engine.state['statuses']['run'] = 'completed'
        engine.state['results']['run'] = {'raw_text': 'different'}
    engine.perform = perform
    engine.judge.decide = AsyncMock(side_effect=[{'run': {'choice': 'execute'}}, {'original_task': {'choice': 'met'}}])
    engine.runtime.complete = AsyncMock(side_effect=AssertionError('Must not generate successful final answer'))
    try:
        assert await engine._loop() == clarification.message
        assert not engine.state['completion_checks']['exit']['passed']
        assert engine.make_plan.await_count == 2
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
async def test_checkpointed_failure_blocks_direct_answer_and_rebind_can_recover(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'state'))
    settings = Settings()
    store = Store(settings)
    sid = store.create(tmp_path)
    store.save_state(sid, {'request': 'Run successfully', 'steps': 1, 'observations': [], 'completion_checks': {
        'exit': {'check': check().model_dump(), 'passed': False, 'reason': 'Wrong exit code'}}})
    engine = Engine(settings, tmp_path, store, sid, lambda *a: None, AsyncMock())
    engine.make_plan = AsyncMock(side_effect=[Plan(mode='answer', message='Success', actions=[], success_criteria=[]),
        Plan(mode='clarify', message='Need input to repair.', actions=[], success_criteria=[])])
    engine.judge.decide = AsyncMock(side_effect=AssertionError('Cannot override deterministic failure'))
    try:
        assert await engine._loop() == 'Need input to repair.'
        register(engine.state, [check(source='${retry.exitCode}')])
        engine.state.update(statuses={'retry': 'completed'}, results={'retry': {'exitCode': 0}})
        assert not await evaluate(engine.state, engine.tools, {'exit'})
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('text,passed', [('{"b":2,"a":1}', True), ('{"a":1,"b":3}', False), ('{"a":1,"a":1,"b":2}', False), ('{"a":NaN}', False), ('not json', False)])
async def test_json_checks_reject_ambiguous_or_invalid_output(text, passed):
    state = {'statuses': {'run': 'completed'}, 'results': {'run': {'stdout': text}}}
    register(state, [check(kind='result_json_equals', source='${run.stdout}', expected_json='{"a":1,"b":2}')])
    assert (not await evaluate(state, None, {'exit'})) == passed


@pytest.mark.asyncio
@pytest.mark.parametrize('value,note,expected', [
    ({'accepted': True, 'count': 3, 'tags': ['oak', 'pine']}, b'ready\n', True),
    ({'accepted': 1, 'count': 3, 'tags': ['oak', 'pine']}, b'ready\n', False),
    ({'accepted': True, 'count': 3, 'tags': ['pine', 'oak']}, b'ready\n', False),
    ({'accepted': True, 'count': 3, 'tags': ['oak', 'pine']}, b'ready\n\n', False),
])
async def test_artifact_benchmark_oracle_checks_types_order_and_bytes(tmp_path, value, note, expected):
    from benchmarks.workloads import grade
    (tmp_path/'receipt.json').write_text(json.dumps(value))
    (tmp_path/'note.txt').write_bytes(note)
    passed, _ = await grade('exact_artifact', 'SAVED', tmp_path, None, [], [])
    assert passed is expected
