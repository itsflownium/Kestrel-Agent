import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from kestrel_agent.config import Settings
from kestrel_agent.engine import Engine
from kestrel_agent.store import Store


def engine_fixture(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'state'))
    settings = Settings(agent_mode='standard', shell=False, network=False)
    workspace = tmp_path/'work'
    workspace.mkdir()
    store = Store(settings)
    engine = Engine(settings, workspace, store, store.create(workspace), lambda *args:None, AsyncMock())
    return engine, store


@pytest.mark.asyncio
async def test_amend_preserves_evidence_checks_and_uncertain_effects_across_restart(tmp_path, monkeypatch):
    engine, store = engine_fixture(tmp_path, monkeypatch)
    try:
        engine.state.update(request='Save the requested report', status='interrupted',
                            completed_effects=['done'], uncertain_effects=['maybe'],
                            completion_checks={'exact':{'passed':False}},
                            repair_snapshot={'actions':[]}, steps=3, plan={'stale':True},
                            observations=[{'action':'saved'}])
        engine.amend('Also include a concise explanation')
        saved = json.loads(store.session(engine.sid)['state'])
        assert saved['request'].startswith('Save the requested report')
        assert saved['request'].endswith('Also include a concise explanation')
        assert saved['plan'] is None and saved['steps'] == 3
        assert saved['completed_effects'] == ['done']
        assert saved['uncertain_effects'] == ['maybe']
        assert saved['completion_checks'] == {'exact':{'passed':False}}
        assert saved['repair_snapshot'] == {'actions':[]}
        assert saved['observations'] == [{'action':'saved'}]
        assert saved['user_updates'][0]['text'] == 'Also include a concise explanation'
        assert store.conversation(engine.sid)[-1] == {'kind':'user','body':'Also include a concise explanation'}
        resumed = Engine(engine.settings, engine.workspace, store, engine.sid, lambda *args:None, AsyncMock())
        try:
            assert resumed.state['user_updates'] == saved['user_updates']
        finally:
            await resumed.close()
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('status,message', [('running','update'),('completed','update'),('interrupted',''),('interrupted','x'*8001)])
async def test_invalid_updates_do_not_mutate_task(tmp_path, monkeypatch, status, message):
    engine, store = engine_fixture(tmp_path, monkeypatch)
    try:
        engine.state.update(status=status, request='Original task')
        before = json.dumps(engine.state, sort_keys=True)
        with pytest.raises(ValueError):
            engine.amend(message)
        assert json.dumps(engine.state, sort_keys=True) == before
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
async def test_resume_marks_running_and_new_task_clears_old_updates(tmp_path, monkeypatch):
    engine, store = engine_fixture(tmp_path, monkeypatch)
    try:
        engine.state.update(status='interrupted', request='Original task', user_updates=[{'text':'prior'}])
        async def answer():
            assert engine.state['status'] == 'running'
            return 'done'
        engine._loop = answer
        assert await engine.run(None) == 'done'
        from kestrel_agent import fastpath, prefetch
        monkeypatch.setattr(fastpath, 'try_fastpath', AsyncMock(return_value=None))
        monkeypatch.setattr(prefetch, 'prefetch', AsyncMock())
        assert await engine.run('Different task') == 'done'
        assert engine.state['user_updates'] == []
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
async def test_ui_steering_waits_for_cancellation_before_restarting(tmp_path, monkeypatch):
    from kestrel_agent.ui import Terminal
    engine, store = engine_fixture(tmp_path, monkeypatch)
    terminal = Terminal(engine.settings, engine.workspace, store, engine.sid)
    await engine.close()
    stopped, resumed = asyncio.Event(), asyncio.Event()
    terminal.engine.state.update(status='running', request='Original task')
    async def running():
        try:
            await asyncio.Future()
        finally:
            await asyncio.sleep(0)
            terminal.engine.state['status'] = 'interrupted'
            stopped.set()
    async def resume(message):
        assert message is None
        assert stopped.is_set()
        assert terminal.engine.state['request'].endswith('Use a shorter summary')
        resumed.set()
    terminal.work = resume
    terminal.busy = True
    terminal.job = asyncio.create_task(running())
    await asyncio.sleep(0)
    try:
        await terminal.command('/steer Use a shorter summary')
        await terminal.job
        assert resumed.is_set()
        assert len(terminal.engine.state['user_updates']) == 1
    finally:
        await terminal.engine.close()
        store.close()


@pytest.mark.asyncio
async def test_steering_keeps_completed_file_effect_without_replay(tmp_path, monkeypatch):
    from kestrel_agent.schema import Action, Plan
    from kestrel_agent.scheduler import execute_plan
    from kestrel_agent.reconciliation import checkpoint, repair_state
    from kestrel_agent.engine import GATE_PROMPT
    engine, store = engine_fixture(tmp_path, monkeypatch)
    write = Action(id='save', tool='write_file', arguments_json=json.dumps({'path':'saved.txt','content':'keep exactly','expected_sha256':None}), depends_on=[], purpose='Save once', condition='always')
    read = Action(id='inspect', tool='read_file', arguments_json=json.dumps({'path':'saved.txt'}), depends_on=['save'], purpose='Inspect', condition='always')
    plan = Plan(mode='plan', message='Save and inspect', actions=[write,read], success_criteria=[])
    waiting = asyncio.Event()
    original_execute = engine.tools.execute
    writes = []
    async def execute(tool, args):
        if tool == 'read_file':
            waiting.set()
            await asyncio.Future()
        if tool == 'write_file':
            writes.append(args['path'])
        return await original_execute(tool, args)
    engine.tools.execute = execute
    async def first_loop():
        try:
            await execute_plan(engine, plan, GATE_PROMPT)
        finally:
            checkpoint(engine.state, plan)
            engine.save()
    engine._loop = first_loop
    task = asyncio.create_task(engine.run('Save and inspect', initial_plan=plan))
    try:
        await asyncio.wait_for(waiting.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        engine.amend('The saved file is enough; explain it briefly')
        revised = Plan(mode='plan', message='Keep saved file', actions=[write], success_criteria=[])
        async def resumed_loop():
            assert engine.state['request'].endswith('explain it briefly')
            retained = await repair_state(engine.state, revised, engine.tools)
            assert retained == ['save']
            await execute_plan(engine, revised, GATE_PROMPT)
            return 'Saved once and retained.'
        engine._loop = resumed_loop
        assert await engine.run(None) == 'Saved once and retained.'
        assert writes == ['saved.txt']
        assert (engine.workspace/'saved.txt').read_text() == 'keep exactly'
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await engine.close()
        store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('control', ['steer', 'cancel', 'exit'])
async def test_chat_controls_cancel_pending_approval(tmp_path, monkeypatch, control):
    from kestrel_agent.ui import Terminal
    engine, store = engine_fixture(tmp_path, monkeypatch)
    terminal = Terminal(engine.settings, engine.workspace, store, engine.sid)
    await engine.close()
    terminal.engine.state.update(status='running', request='Original task')
    resumed = asyncio.Event()
    async def running():
        try:
            await terminal.confirm('An action awaiting permission')
        finally:
            terminal.engine.state['status'] = 'interrupted'
            terminal.busy = False
    async def resume(message):
        assert terminal.pending_approval is None
        assert terminal.engine.state['request'].endswith('Inspect before changing anything')
        resumed.set()
    terminal.work = resume
    terminal.ensure_keys = AsyncMock()
    terminal.welcome = lambda:None
    terminal.job = asyncio.create_task(running())
    terminal.busy = True
    calls = 0
    async def prompt(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            while terminal.pending_approval is None:
                await asyncio.sleep(0)
            return '/steer Inspect before changing anything' if control == 'steer' else '/' + control
        if control == 'steer':
            await asyncio.wait_for(resumed.wait(), 5)
        else:
            assert terminal.job.done()
        raise EOFError
    terminal.prompt.prompt_async = prompt
    try:
        await asyncio.wait_for(terminal.chat(), 10)
        assert resumed.is_set() == (control == 'steer')
        assert terminal.pending_approval is None
    finally:
        await terminal.engine.close()
        store.close()


@pytest.mark.asyncio
async def test_completion_race_does_not_restart_finished_work(tmp_path, monkeypatch):
    from kestrel_agent.ui import Terminal
    engine, store = engine_fixture(tmp_path, monkeypatch)
    terminal = Terminal(engine.settings, engine.workspace, store, engine.sid)
    await engine.close()
    terminal.engine.state.update(status='running', request='Original task')
    async def completes_during_cancel():
        try:
            await asyncio.Future()
        finally:
            terminal.engine.state['status'] = 'completed'
    terminal.job = asyncio.create_task(completes_during_cancel())
    terminal.work = AsyncMock()
    await asyncio.sleep(0)
    try:
        with pytest.raises(ValueError, match='unfinished task'):
            await terminal.command('/steer Do more work')
        assert terminal.engine.state['request'] == 'Original task'
        assert not terminal.engine.state.get('user_updates')
        terminal.work.assert_not_called()
    finally:
        await terminal.engine.close()
        store.close()
