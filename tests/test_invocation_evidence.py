import json
from unittest.mock import AsyncMock

import pytest

from kestrel_agent.config import Settings
from kestrel_agent.engine import Engine
from kestrel_agent.evidence import context
from kestrel_agent.schema import Action
from kestrel_agent.store import Store


@pytest.mark.asyncio
async def test_full_invocation_is_retrievable_after_truncation_and_restart(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'state'))
    settings = Settings(agent_mode='standard', max_context_chars=4000)
    store = Store(settings)
    sid = store.create(tmp_path)
    engine = Engine(settings, tmp_path, store, sid, lambda *args: None, AsyncMock())
    engine.state.update(results={}, statuses={})
    arguments = {'command': ['python3', '-c', '# padding\n' * 800 + 'assert important_check'], 'cwd': '.'}
    engine.tools.execute = AsyncMock(return_value={'exitCode': 0, 'stdout': 'VERIFIED'})
    try:
        await engine.perform(Action(id='verify', tool='shell', arguments_json=json.dumps(arguments),
            depends_on=[], purpose='Verify output', condition='always'))
        observed = engine.context()['observations'][0]
        assert observed['arguments_truncated'] is True
        assert 'important_check' not in observed['arguments_excerpt']
        invocation_id = observed['invocation_evidence_id']
        result_id = observed['evidence_id']
        assert invocation_id != result_id
        assert engine.context()['evidence_index'][0]['invocation_evidence_id'] == invocation_id
    finally:
        await engine.close()
        store.close()
    store = Store(settings)
    engine = Engine(settings, tmp_path, store, sid, lambda *args: None, AsyncMock())
    try:
        recovered = await engine.tools.execute('read_evidence', {'id': invocation_id, 'max_chars': 20000})
        invocation = json.loads(recovered['content'])
        assert invocation['arguments'] == arguments
        assert invocation['status'] == 'completed'
        assert invocation['executor_called'] is True and invocation['executor_returned'] is True
        assert invocation['result_evidence_id'] == result_id
        assert store.read_evidence(sid, result_id) == {'exitCode': 0, 'stdout': 'VERIFIED'}
        other = store.create(tmp_path)
        with pytest.raises(ValueError, match='not available'):
            store.read_evidence(other, invocation_id)
    finally:
        await engine.close()
        store.close()


def test_short_result_leaves_space_for_complete_longer_arguments():
    arguments = {'command': ['python3', '-c', '#' * 700 + '\nassert final_check']}
    state = {'observations': [{'action': 'verify', 'tool': 'shell', 'status': 'completed',
        'arguments': arguments, 'result': {'exitCode': 0, 'stdout': 'OK'}, 'evidence_id': 'result', 'invocation_evidence_id': 'invocation'}]}
    view = context(state, 4000)['observations'][0]
    assert len(view['arguments_excerpt']) > 500
    assert view['arguments_truncated'] is False
    assert json.loads(view['arguments_excerpt']) == arguments
    assert len(view['arguments_excerpt']) + len(view['result_excerpt']) <= 2200


def test_legacy_observations_do_not_claim_missing_invocation_evidence():
    state = {'observations': [{'action': 'old', 'arguments': {}, 'result': {}, 'evidence_id': 'result'}]}
    view = context(state, 4000)
    assert view['observations'][0]['invocation_evidence_id'] is None
    assert 'invocation_evidence_id' not in view['evidence_index'][0]
