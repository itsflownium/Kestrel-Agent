import hashlib
import json
from unittest.mock import AsyncMock

import pytest

from kestrel_agent.config import Settings
from kestrel_agent.engine import Engine
from kestrel_agent.reconciliation import checkpoint, effect_identity, repair_state, unresolved_effect
from kestrel_agent.schema import Action, Plan
from kestrel_agent.store import Store


def action(id='run', tool='shell', args=None, dependencies=None):
    return Action(id=id, tool=tool, arguments_json=json.dumps(args or {'command': ['python3', 'job.py']}),
                  depends_on=dependencies or [], purpose='Perform requested work', condition='always')


def plan(actions):
    return Plan(mode='plan', message='Work', actions=actions, success_criteria=[])


def test_effect_identity_normalizes_only_known_equivalent_forms(tmp_path):
    a = effect_identity('shell', {'command': ['python3', 'job.py']}, tmp_path)
    b = effect_identity('shell', {'command': ['python3', './job.py'], 'cwd': str(tmp_path)}, tmp_path)
    assert a == b
    c = effect_identity('shell', {'command': ['python3', './job.py', '--fixed']}, tmp_path)
    assert a[0] != c[0] and a[1] == c[1]
    assert effect_identity('write_file', {'path': './x', 'content': 'a'}, tmp_path) == effect_identity('write_file', {'path': str(tmp_path/'x'), 'content': 'a', 'expected_sha256': 'old'}, tmp_path)
    assert effect_identity('shell', {'command': ['echo', './x']}, tmp_path)[0] != effect_identity('shell', {'command': ['echo', 'x']}, tmp_path)[0]


@pytest.mark.parametrize('audit,related', [(None, True), ({'unchanged_at_boundaries': None}, True), ({'unchanged_at_boundaries': False}, True), ({'unchanged_at_boundaries': True}, False)])
def test_failed_effects_guard_equivalent_and_potentially_partial_retries(audit, related):
    state = {'effect_receipts': [{'fingerprint': 'one', 'family': 'script', 'status': 'error', 'workspace_audit': audit}]}
    assert unresolved_effect(state, 'one', 'script')
    assert bool(unresolved_effect(state, 'new-arguments', 'script')) == related
    assert not unresolved_effect(state, 'new', 'different-script')


@pytest.mark.asyncio
async def test_repair_retains_successful_subgraph_and_invalidates_changed_sources(tmp_path):
    read = action('read', 'read_file', {'path': 'input.txt'})
    write = action('write', 'write_file', {'path': 'output.txt', 'content': '${read.raw_text}'}, ['read'])
    failed = action('failed')
    original = plan([read, write, failed])
    state = {'results': {'read': {'path': str(tmp_path/'input.txt'), 'sha256': 'source'}, 'write': {'path': str(tmp_path/'output.txt'), 'sha256': 'output'}},
             'statuses': {'read': 'completed', 'write': 'completed', 'failed': 'error'}}
    checkpoint(state, original)
    class Tools:
        changed = False
        def read_file(self, args):
            if args['path'].endswith('input.txt'):
                return {'path': str(tmp_path/'input.txt'), 'sha256': 'changed' if self.changed else 'source'}
            return {'path': str(tmp_path/'output.txt'), 'sha256': 'output'}
    tools = Tools()
    repaired = plan([read, write, action('failed', args={'command': ['python3', 'job.py', '--fixed']})])
    assert await repair_state(state, repaired, tools) == ['read', 'write']
    assert 'failed' not in state['statuses']
    tools.changed = True
    assert await repair_state(state, repaired, tools) == []


@pytest.mark.asyncio
async def test_changed_action_and_descendants_are_not_retained(tmp_path):
    a = action()
    b = action('next', dependencies=['run'])
    state = {'results': {'run': {}, 'next': {}}, 'statuses': {'run': 'completed', 'next': 'completed'}}
    checkpoint(state, plan([a, b]))
    a.purpose = 'A different operation'
    assert await repair_state(state, plan([a, b]), None) == []


@pytest.mark.asyncio
async def test_partial_failed_script_requires_retry_approval_even_with_changed_arguments(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'state'))
    store = Store(Settings())
    confirm = AsyncMock(return_value=False)
    engine = Engine(Settings(), tmp_path, store, store.create(tmp_path), lambda *a: None, confirm)
    engine.state.update(steps=0, statuses={}, results={}, observations=[])
    engine.tools.execute = AsyncMock(return_value={'exitCode': 2, 'error': 'failed after mutation', 'workspace_audit': {'unchanged_at_boundaries': False}})
    try:
        await engine.perform(action())
        await engine.perform(action('retry', args={'command': ['python3', './job.py', '--fixed']}))
        assert engine.tools.execute.await_count == 1
        assert confirm.await_count == 1
        assert engine.state['statuses']['retry'] == 'error'
        assert 'not retried' in engine.state['results']['retry']['error']
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
async def test_normalized_completed_effect_cannot_be_replayed(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'state'))
    store = Store(Settings())
    engine = Engine(Settings(), tmp_path, store, store.create(tmp_path), lambda *a: None, AsyncMock())
    engine.state.update(steps=0, statuses={}, results={}, observations=[])
    engine.tools.execute = AsyncMock(return_value={'exitCode': 0})
    try:
        await engine.perform(action())
        await engine.perform(action('duplicate', args={'command': ['python3', './job.py'], 'cwd': str(tmp_path)}))
        assert engine.tools.execute.await_count == 1
        assert 'already completed' in engine.state['results']['duplicate']['error']
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
async def test_engine_replans_only_failed_branch_without_reexecuting_completed_effect(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'state'))
    store = Store(Settings())
    engine = Engine(Settings(), tmp_path, store, store.create(tmp_path), lambda *a: None, AsyncMock(return_value=False))
    a = action('first', args={'command': ['python3', 'first.py']})
    b = action('second', args={'command': ['python3', 'second.py']})
    fixed = action('second', args={'command': ['python3', 'second.py', '--fixed']})
    engine.state.update(request='Run both scripts, repairing missing arguments.', steps=0, statuses={}, results={}, observations=[])
    engine.make_plan = AsyncMock(side_effect=[plan([a, b]), plan([a, fixed])])
    engine.tools.execute = AsyncMock(side_effect=[{'exitCode': 0, 'stdout': 'first done'},
        {'exitCode': 2, 'error': 'missing arguments', 'workspace_audit': {'unchanged_at_boundaries': True}},
        {'exitCode': 0, 'stdout': 'second done'}])
    engine.judge.decide = AsyncMock(side_effect=[{'first': {'choice': 'execute'}}, {'second': {'choice': 'execute'}},
        {'original_task': {'choice': 'not_met'}, 'recovery_second': {'choice': 'not_met'}},
        {'second': {'choice': 'execute'}}, {'original_task': {'choice': 'met'}}, {'support': {'choice': 'supported'}}])
    engine.runtime.complete = AsyncMock(return_value='Both finished.')
    try:
        assert await engine._loop() == 'Both finished.'
        assert engine.tools.execute.await_count == 3
        assert engine.state['steps'] == 3
        assert engine.state['statuses'] == {'first': 'completed', 'second': 'completed'}
        events = [json.loads(row[0]) for row in store.db.execute("SELECT body FROM events WHERE kind='retained_subgraph'")]
        assert events == [{'actions': ['first']}]
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
async def test_process_death_restores_related_effect_guard(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'state'))
    settings = Settings()
    store = Store(settings)
    sid = store.create(tmp_path)
    fingerprint, family = effect_identity('shell', {'command': ['python3', 'job.py']}, tmp_path)
    store.save_state(sid, {'inflight': {'run': {'fingerprint': fingerprint, 'family': family, 'effect': True}}})
    engine = Engine(settings, tmp_path, store, sid, lambda *a: None, AsyncMock())
    try:
        assert fingerprint in engine.state['uncertain_effects']
        assert unresolved_effect(engine.state, 'changed-arguments', family)
        assert not engine.state['inflight']
    finally:
        await engine.close()
        store.close()
