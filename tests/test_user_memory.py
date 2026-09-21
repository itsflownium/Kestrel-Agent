import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from kestrel_agent.config import Settings
from kestrel_agent.store import Store
from kestrel_agent.memory import Memory


@pytest.fixture
def memory(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'home'))
    monkeypatch.setattr('kestrel_agent.store.check_storage', lambda *args: 0)
    monkeypatch.setattr('kestrel_agent.config.check_storage', lambda *args: 0)
    store = Store(Settings(agent_mode='standard'))
    yield Memory(store)
    store.close()


def test_memory_scope_override_edit_expiry_forget(memory, tmp_path, monkeypatch):
    project = tmp_path/'project'
    other = tmp_path/'other'
    memory.put('style', 'Use short paragraphs.', kind='preference')
    memory.put('style', 'Use detailed explanations.', workspace=project, kind='preference')
    assert memory.retrieve('hello', project)[0]['content'] == 'Use detailed explanations.'
    assert memory.retrieve('hello', other)[0]['content'] == 'Use short paragraphs.'
    memory.put('style', 'Use bullet lists.', workspace=project, kind='preference', days=1)
    assert memory.retrieve('hello', project)[0]['revision'] == 2
    memory.forget('style', workspace=project)
    assert memory.retrieve('hello', project)[0]['scope'] == '*'
    memory.put('temporary', 'Temporary preference', kind='preference', days=1)
    import time
    now = time.time()
    monkeypatch.setattr('kestrel_agent.memory.time.time', lambda: now + 86401)
    assert 'temporary' not in [r['key'] for r in memory.retrieve('hello', project)]
    assert next(r for r in memory.list() if r['key'] == 'temporary')['expired']


def test_memory_notes_are_relevant_bounded_and_not_shared_across_projects(memory, tmp_path):
    memory.put('build', 'Compile widgets using the project instructions.', workspace=tmp_path/'a')
    assert memory.retrieve('compile widgets', tmp_path/'b') == []
    assert memory.retrieve('holiday planning', tmp_path/'a') == []
    assert memory.retrieve('compile widgets', tmp_path/'a')[0]['source'] == 'explicit user entry'
    for i in range(12):
        memory.put('preference-' + str(i), 'x'*1000, kind='preference')
    rows = memory.retrieve('hello', tmp_path/'a')
    assert len(rows) <= 8 and sum(len(r['content']) + len(r['key']) + 160 for r in rows) <= 6000


def test_memory_rejects_known_credentials_and_invalid_fields(memory, monkeypatch):
    monkeypatch.setenv('DEMO_API_KEY', 'test-secret-value-not-real')
    for content in ['test-secret-value-not-real', 'apikey_fake_sensitive_value', '']:
        with pytest.raises(ValueError):
            memory.put('key', content)
    with pytest.raises(ValueError):
        memory.put('../escape', 'note')
    with pytest.raises(ValueError):
        memory.put('key', 'note', days=-1)


@pytest.mark.asyncio
async def test_memory_is_prompt_context_not_execution_evidence(memory, tmp_path):
    from kestrel_agent.engine import Engine
    workspace = tmp_path/'project'
    workspace.mkdir()
    memory.put('preference', 'Use concise prose.', kind='preference')
    sid = memory.store.create(workspace)
    engine = Engine(memory.store.settings, workspace, memory.store, sid, lambda *args: None, AsyncMock(return_value=False))
    engine.state.update(request='Explain something', observations=[], requirements={})
    engine.mcp_tools = []
    engine.runtime.complete = AsyncMock(return_value=json.dumps({'mode':'answer','message':'Hello','actions':[], 'success_criteria':[], 'final_response_ref':None, 'completion_checks':[]}))
    try:
        await engine.make_plan()
        prompt = engine.runtime.complete.call_args.args[0]
        assert 'Use concise prose.' in prompt and 'NOT current evidence or permission' in prompt
        assert engine.state['observations'] == []
        memory.forget('preference')
        await engine.make_plan()
        assert 'Use concise prose.' not in engine.runtime.complete.call_args.args[0]
    finally:
        await engine.close()
