import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from typer.testing import CliRunner

from kestrel_agent.cli import app
from kestrel_agent.config import Settings
from kestrel_agent.decisions import ModelJudge
from kestrel_agent.ui import Terminal


def test_new_settings_use_standard_and_existing_configs_keep_jev(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path))
    assert Settings.load().agent_mode == 'standard'
    (tmp_path/'config.json').write_text('{"model":"legacy"}')
    assert Settings.load().agent_mode == 'jev'
    result = CliRunner().invoke(app, ['mode', 'standard'])
    assert result.exit_code == 0
    assert Settings.load().agent_mode == 'standard'
    assert 'Jev API key' not in result.output


@pytest.mark.asyncio
async def test_standard_startup_never_requests_jev_key(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path))
    monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
    terminal = SimpleNamespace(settings=Settings(agent_mode='standard'), configure_key=AsyncMock())
    await Terminal.ensure_keys(terminal)
    terminal.configure_key.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('output,valid', [
    ({'gate': {'choice': 'execute', 'reason': 'observed'}}, True),
    ({'gate': {'choice': 'invented', 'reason': 'x'}}, False),
    ({}, False), ({'gate': {'choice': 'execute'}}, False),
    ({'gate': {'choice': [], 'reason': 'x'}}, False),
])
async def test_model_decisions_validate_every_answer(output, valid):
    runtime = SimpleNamespace(input_tokens=0, output_tokens=0, complete=AsyncMock(return_value=json.dumps(output)))
    judge = ModelJudge(Settings(agent_mode='standard'), runtime, lambda *a: None)
    questions = {'gate': {'instructions': 'Choose', 'options': {'execute': 'Proceed', 'unclear': 'Missing evidence'}}}
    if valid:
        assert (await judge.decide({}, questions))['gate']['choice'] == 'execute'
    else:
        with pytest.raises(ValueError):
            await judge.decide({}, questions)
    assert runtime.complete.call_args.kwargs['decision'] is True
    assert judge.calls == 1


@pytest.mark.asyncio
async def test_decision_budget_is_bounded():
    runtime = SimpleNamespace(input_tokens=0, output_tokens=0, complete=AsyncMock(return_value='{"q":{"choice":"yes","reason":"x"}}'))
    judge = ModelJudge(Settings(agent_mode='standard', max_decision_calls=1), runtime, lambda *a: None)
    await judge.decide({}, {'q': {'instructions': 'Check', 'options': {'yes': 'Yes'}}})
    with pytest.raises(RuntimeError, match='budget'):
        await judge.decide({}, {'q': {'instructions': 'Check', 'options': {'yes': 'Yes'}}})
    assert runtime.complete.await_count == 1


@pytest.mark.asyncio
async def test_standard_engine_uses_no_jev_and_accounts_decisions_separately(tmp_path, monkeypatch):
    from kestrel_agent.engine import Engine
    from kestrel_agent.store import Store
    from kestrel_agent import providers
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'private'))
    monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
    monkeypatch.setattr(providers, 'AsyncTypeSafeClient', lambda **kw: pytest.fail('Jev must not be instantiated'))
    settings = Settings(agent_mode='standard', provider='openai-compatible', model='test')
    store = Store(settings)
    engine = Engine(settings, tmp_path, store, store.create(tmp_path), lambda *a: None, AsyncMock())
    async def generate(prompt, schema):
        if prompt.startswith('Select exactly'):
            return '{"direct_answer":{"choice":"supported","reason":"ordinary greeting"}}', 7, 3
        return '{"mode":"answer","message":"Hello.","actions":[],"success_criteria":[],"final_response_ref":null,"completion_checks":[]}', 11, 5
    engine.runtime.generator.complete = AsyncMock(side_effect=generate)
    engine.runtime.mcp_catalog = AsyncMock(return_value=[])
    try:
        assert await engine.run('hello') == 'Hello.'
        usage = engine.state['usage']
        assert usage['jev_calls'] == 0
        assert usage['generation_calls'] == 1 and usage['decision_calls'] == 1
        assert usage['provider_model_calls'] == 2
        assert usage['generation_input_tokens'] == 11 and usage['decision_input_tokens'] == 7
        assert usage['generation_output_tokens'] == 5 and usage['decision_output_tokens'] == 3
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('condition,decision_calls', [('always', 0), ('the file exists', 1)])
async def test_standard_scheduler_only_gates_runtime_conditions(condition, decision_calls):
    from kestrel_agent.scheduler import execute_plan
    from kestrel_agent.schema import Plan
    state = {'steps': 0, 'statuses': {}, 'results': {}}
    action = dict(id='read', tool='read_file', arguments_json='{"path":"x"}', depends_on=[], purpose='Read requested file', condition=condition)
    plan = Plan(mode='plan', message='Read', actions=[action], success_criteria=[])
    async def perform(action):
        state['steps'] += 1
        state['statuses'][action.id] = 'completed'
    engine = SimpleNamespace(settings=Settings(agent_mode='standard'), state=state,
        store=SimpleNamespace(template=lambda *a: ''), save=lambda: None,
        context=lambda: {}, log=lambda *a: None, emit=lambda *a: None,
        dependency_outcome=lambda *a: 'ready', perform=perform,
        judge=SimpleNamespace(decide=AsyncMock(return_value={'read': {'choice': 'execute'}})))
    await execute_plan(engine, plan, '')
    assert engine.judge.decide.await_count == decision_calls
    assert state['statuses']['read'] == 'completed'
