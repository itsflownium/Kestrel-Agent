"""Exercise compiled templates through real scheduling, storage, and file tools.

This deliberately stops before model repair/final-answer generation. A repaired
plan must not turn a failing original template into a certification pass.
"""
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from kestrel_agent.config import Settings
from kestrel_agent.engine import Engine, GATE_PROMPT
from kestrel_agent.scheduler import execute_plan
from kestrel_agent.store import Store
from kestrel_agent.workflow_templates import read, compile_workflow


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['empty', 'unicode', 'spaces', 'missing', 'existing', 'read-only', 'declined', 'outside', 'truncated'])
async def test_copy_template_real_artifacts(tmp_path, monkeypatch, case):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path / 'state'))
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    source = workspace / 'source with spaces.txt'
    destination = workspace / 'nested' / 'copy.txt'
    content = {'empty': '', 'unicode': 'Café 東京 🪶\n', 'spaces': '  first\n\n\tlast  \n'}.get(case, 'original source\n')
    if case == 'truncated':
        content = 'line\n' * 1001
    if case != 'missing':
        source.write_text(content, encoding='utf-8')
    if case == 'existing':
        destination.parent.mkdir()
        destination.write_text('keep existing', encoding='utf-8')
    if case == 'outside':
        destination = tmp_path / 'outside.txt'
    before = source.read_bytes() if source.exists() else None
    settings = Settings(agent_mode='standard', network=False, shell=False,
        permission='read-only' if case == 'read-only' else 'workspace',
        confirm_writes=case == 'declined')
    store = Store(settings)
    confirm = AsyncMock(return_value=False)
    engine = Engine(settings, workspace, store, store.create(workspace), lambda *args: None, confirm)
    # Fail loudly if these unconditional file operations unexpectedly need a model.
    engine.runtime.complete = AsyncMock(side_effect=AssertionError('Unexpected generation'))
    engine.judge.decide = AsyncMock(side_effect=AssertionError('Unexpected decision'))
    value = read(Path(__file__).parents[1] / 'examples/workflows/copy-text.json')
    plan, version = compile_workflow(value, {'source': source.name, 'destination': str(destination)})
    engine.state.update(request='Copy the source into a new destination', statuses={}, results={}, steps=0, observations=[])
    try:
        await execute_plan(engine, plan, GATE_PROMPT)
        success = case in {'empty', 'unicode', 'spaces'}
        assert (engine.state['statuses']['copy'] == 'completed') == success
        if success:
            assert destination.read_bytes() == before
            receipt = engine.state['results']['copy']
            assert receipt['bytes'] == len(before)
        elif case == 'existing':
            assert destination.read_text() == 'keep existing'
        else:
            assert not destination.exists()
        assert (source.read_bytes() if source.exists() else None) == before
        saved = json.loads(store.session(engine.sid)['state'])
        assert saved['statuses'] == engine.state['statuses']
        assert len(version) == 64
        engine.runtime.complete.assert_not_called()
        engine.judge.decide.assert_not_called()
        if case == 'declined':
            confirm.assert_awaited_once()
    finally:
        await engine.close()
        store.close()
