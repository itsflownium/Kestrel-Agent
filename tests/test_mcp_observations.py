import json
from unittest.mock import AsyncMock

import pytest
from typer.testing import CliRunner

from kestrel_agent.cli import app
from kestrel_agent.config import Settings
from kestrel_agent.connections import Connection, is_observation
from kestrel_agent.engine import Engine
from kestrel_agent.reconciliation import checkpoint, repair_state
from kestrel_agent.schema import Action, Plan
from kestrel_agent.store import Store


def action(name, tool='observe'):
    return Action(id=name, tool='mcp', arguments_json=json.dumps({'server': 'direct:fixture', 'tool': tool, 'arguments': {}}),
        depends_on=[], purpose='Inspect current state', condition='always')


def settings(**kwargs):
    return Settings(agent_mode='standard', mcp_connections={'fixture': Connection(url='http://localhost:8000/mcp', read_only_tools=['observe'])}, **kwargs)


@pytest.mark.asyncio
async def test_observations_refresh_but_effects_still_cannot_repeat(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'state'))
    config = settings()
    store = Store(config)
    confirm = AsyncMock(return_value=True)
    engine = Engine(config, tmp_path, store, store.create(tmp_path), lambda *args: None, confirm)
    engine.state.update(results={}, statuses={})
    engine.runtime.mcp_call = AsyncMock(side_effect=[{'value': 'before'}, {'value': 'after'}, {'saved': True}])
    try:
        await engine.perform(action('first'))
        await engine.perform(action('second'))
        assert engine.state['results']['second'] == {'value': 'after'}
        assert engine.state['completed_effects'] == []
        assert confirm.await_count == 2
        await engine.perform(action('write', 'submit'))
        await engine.perform(action('duplicate', 'submit'))
        assert engine.state['statuses']['write'] == 'completed'
        assert engine.state['statuses']['duplicate'] == 'error'
        assert 'already completed' in engine.state['results']['duplicate']['error']
        assert engine.runtime.mcp_call.await_count == 3
        assert len(engine.state['completed_effects']) == 1
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('options', [{'network': False}, {'permission': 'read-only'}, {}])
async def test_observation_classification_never_grants_permission(tmp_path, monkeypatch, options):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'state'))
    config = settings(**options)
    store = Store(config)
    engine = Engine(config, tmp_path, store, store.create(tmp_path), lambda *args: None, AsyncMock(return_value=False))
    engine.state.update(results={}, statuses={})
    engine.runtime.mcp_call = AsyncMock()
    try:
        await engine.perform(action('read'))
        assert engine.state['statuses']['read'] == 'error'
        engine.runtime.mcp_call.assert_not_called()
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
async def test_failed_observation_can_retry_without_uncertain_effect_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'state'))
    config = settings()
    store = Store(config)
    confirm = AsyncMock(return_value=True)
    engine = Engine(config, tmp_path, store, store.create(tmp_path), lambda *args: None, confirm)
    engine.state.update(results={}, statuses={})
    engine.runtime.mcp_call = AsyncMock(side_effect=[ConnectionError('interrupted read'), {'value': 'fresh'}])
    try:
        await engine.perform(action('failed'))
        assert engine.state['statuses']['failed'] == 'error'
        assert engine.state['uncertain_effects'] == []
        await engine.perform(action('retry'))
        assert engine.state['results']['retry'] == {'value': 'fresh'}
        assert confirm.await_count == 2
        assert engine.state.get('effect_receipts', []) == []
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
async def test_repair_refreshes_observations_and_retains_independent_effects():
    from types import SimpleNamespace
    plan = Plan(mode='plan', message='', actions=[action('read'), action('write', 'submit')], success_criteria=[])
    state = {'statuses': {'read': 'completed', 'write': 'completed'}, 'results': {'read': {'value': 'old'}, 'write': {'saved': True}}}
    checkpoint(state, plan)
    assert await repair_state(state, plan, SimpleNamespace(settings=settings())) == ['write']
    assert 'read' not in state['results']


@pytest.mark.asyncio
async def test_old_observations_stay_stale_after_configuration_changes():
    from types import SimpleNamespace
    plan = Plan(mode='plan', message='', actions=[action('read')], success_criteria=[])
    state = {'statuses': {'read': 'completed'}, 'results': {'read': {'value': 'old'}}, 'action_effects': {'read': False}}
    checkpoint(state, plan)
    config = settings()
    config.mcp_connections['fixture'].read_only_tools = []
    assert await repair_state(state, plan, SimpleNamespace(settings=config)) == []
    assert state['action_effects'] == {}


def test_classification_requires_exact_enabled_local_configuration():
    config = settings()
    assert is_observation(config, {'server': 'direct:fixture', 'tool': 'observe'})
    for server, tool in [('fixture', 'observe'), ('direct:other', 'observe'), ('direct:fixture', 'submit')]:
        assert not is_observation(config, {'server': server, 'tool': tool, 'readOnlyHint': True})
    config.mcp_connections['fixture'].enabled = False
    assert not is_observation(config, {'server': 'direct:fixture', 'tool': 'observe'})
    for names in [[''], [' observe'], ['observe', 'observe']]:
        with pytest.raises(ValueError):
            Connection(url='http://localhost:8000/mcp', read_only_tools=names)


def test_cli_persists_explicit_read_tools_without_auto_allow(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'state'))
    result = CliRunner().invoke(app, ['connections', 'add', 'fixture', 'http://localhost:8000/mcp', '--read-tool', 'observe', '--read-tool', 'status'])
    assert result.exit_code == 0, result.output
    saved = Settings.load()
    assert saved.mcp_connections['fixture'].read_only_tools == ['observe', 'status']
    assert saved.mcp_auto_allow == []


@pytest.mark.asyncio
async def test_chat_can_configure_and_clear_observation_tools(tmp_path, monkeypatch):
    import io
    from rich.console import Console
    from kestrel_agent.ui import Terminal
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'state'))
    terminal = object.__new__(Terminal)
    terminal.settings = settings()
    terminal.console = Console(file=io.StringIO(), width=100)
    terminal.emit = lambda *args: None
    await terminal.command('/connections reads fixture observe status')
    assert Settings.load().mcp_connections['fixture'].read_only_tools == ['observe', 'status']
    await terminal.command('/connections reads fixture')
    assert Settings.load().mcp_connections['fixture'].read_only_tools == []
