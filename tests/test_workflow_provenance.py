import hashlib
from unittest.mock import AsyncMock, Mock

import pytest

from kestrel_agent import learning
from kestrel_agent.config import Settings
from kestrel_agent.store import Store


@pytest.mark.asyncio
@pytest.mark.parametrize('state', [
    {'status': 'error'},
    {'status': 'completed', 'completion_checks': {'saved': {'passed': False}}},
    {'status': 'completed', 'completion_checks': {'saved': {}}},
    {'status': 'completed', 'uncertain_effects': ['unknown-write']},
    {'status': 'completed', 'inflight': {'write': {}}},
    {'status': 'completed', 'statuses': {'write': 'uncertain'}},
])
async def test_unresolved_trace_cannot_propose_recipe(tmp_path, monkeypatch, state):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path / 'state'))
    settings = Settings(agent_mode='standard')
    store = Store(settings)
    runtime = Mock()
    monkeypatch.setattr(learning, 'Runtime', runtime)
    try:
        sid = store.create(tmp_path)
        store.save_state(sid, state)
        with pytest.raises(ValueError):
            await learning.learn_workflow(store, settings, sid, lambda *args: None)
        runtime.assert_not_called()
        assert store.db.execute('SELECT COUNT(*) FROM workflows').fetchone()[0] == 0
    finally:
        store.close()


@pytest.mark.asyncio
async def test_recipe_provenance_survives_reopen_and_activation(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path / 'state'))
    settings = Settings(agent_mode='standard')
    store = Store(settings)
    runtime = Mock(complete=AsyncMock(return_value='# Copy document\nUse parameters, then inspect the output.'), close=AsyncMock())
    monkeypatch.setattr(learning, 'Runtime', Mock(return_value=runtime))
    sid = store.create(tmp_path)
    store.save_state(sid, {'status': 'completed', 'completion_checks': {'output': {'passed': True, 'check': {'kind': 'file_text_equals'}}}})
    source = store.session(sid)['state']
    try:
        wid = await learning.learn_workflow(store, settings, sid, lambda *args: None)
        assert store.search_workflows('copy document') == []
        provenance = store.workflow_provenance(wid)
        assert provenance['source_session'] == sid
        assert provenance['source_state_sha256'] == hashlib.sha256(source.encode()).hexdigest()
        assert provenance['completion_checks']['output']['passed'] is True
        assert provenance['validation'] == 'unverified'
        store.activate(wid)
        rows = store.search_workflows('copy document')
        assert rows[0]['provenance'] == provenance
        assert hashlib.sha256(rows[0]['body'].encode()).hexdigest() == provenance['recipe_sha256']
        # Later changes to a session must not relabel the original source evidence.
        store.save_state(sid, {'status': 'error'})
        assert store.workflow_provenance(wid) == provenance
        runtime.close.assert_awaited_once()
    finally:
        store.close()
    reopened = Store(settings)
    try:
        assert reopened.workflow_provenance(wid) == provenance
        reopened.activate(wid, False)
        assert reopened.search_workflows('copy document') == []
    finally:
        reopened.close()


def test_legacy_recipe_is_explicitly_unverified(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path / 'state'))
    store = Store(Settings())
    try:
        wid = store.add_workflow('Old document', 'Old recipe')
        store.activate(wid)
        # Recreate the prior on-disk schema, then exercise the additive migration.
        store.db.execute('DROP TABLE workflow_provenance')
        store.db.commit()
    finally:
        store.close()
    store = Store(Settings())
    try:
        assert store.search_workflows('document')[0]['provenance'] == {'validation': 'unverified', 'source': 'not recorded'}
    finally:
        store.close()


def test_cli_exposes_unverified_status_and_provenance(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from kestrel_agent.cli import app
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path / 'state'))
    store = Store(Settings())
    try:
        wid = store.add_workflow('Copy document', 'Review the source before copying.')
    finally:
        store.close()
    runner = CliRunner()
    for args, expected in [(['workflows', 'activate', wid], 'unverified planning guidance'),
                           (['workflows', 'list'], 'unverified'),
                           (['workflows', 'show', wid], 'not recorded')]:
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output
        assert expected in result.output


@pytest.mark.asyncio
async def test_empty_recipe_is_not_saved_and_runtime_closes(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path / 'state'))
    settings = Settings()
    store = Store(settings)
    runtime = Mock(complete=AsyncMock(return_value='  '), close=AsyncMock())
    monkeypatch.setattr(learning, 'Runtime', Mock(return_value=runtime))
    try:
        sid = store.create(tmp_path)
        store.save_state(sid, {'status': 'completed'})
        with pytest.raises(ValueError, match='empty'):
            await learning.learn_workflow(store, settings, sid, lambda *args: None)
        runtime.close.assert_awaited_once()
        assert store.db.execute('SELECT COUNT(*) FROM workflows').fetchone()[0] == 0
    finally:
        store.close()
