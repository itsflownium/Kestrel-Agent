import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from kestrel_agent.config import Settings
from kestrel_agent.engine import Engine
from kestrel_agent.schema import Action, Plan
from kestrel_agent.store import Store


@pytest.mark.asyncio
async def test_fast_read_descendant_does_not_wait_for_unrelated_slow_read(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path / 'state'))
    settings = Settings(max_parallel_reads=2)
    store = Store(settings)
    engine = Engine(settings, tmp_path, store, store.create(tmp_path), lambda *a: None, AsyncMock())
    engine.state.update(request='Inspect three files', steps=0, observations=[], plan=None)
    child_ran = asyncio.Event()
    def action(name, dependencies=()):
        return Action(id=name, tool='read_file', arguments_json=json.dumps({'path':name}),
            depends_on=list(dependencies), purpose='Inspect source', condition='always')
    engine.make_plan = AsyncMock(return_value=Plan(mode='plan', message='',
        actions=[action('fast'), action('slow'), action('child', ['fast'])], success_criteria=[]))
    async def execute(tool, args):
        if args['path'] == 'slow':
            await child_ran.wait()
        if args['path'] == 'child':
            child_ran.set()
        return {'content': args['path']}
    async def decide(state, questions):
        return {key: {'choice': 'supported' if key == 'support' else 'met' if key == 'original_task' else 'execute'} for key in questions}
    engine.tools.execute = execute
    engine.judge.decide = decide
    engine.runtime.complete = AsyncMock(return_value='Done')
    try:
        assert await asyncio.wait_for(engine._loop(), 3) == 'Done'
        assert child_ran.is_set()
    finally:
        await engine.close()
        store.close()


def configured_engine(tmp_path, monkeypatch, actions, **options):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path / 'state'))
    settings = Settings(**options)
    store = Store(settings)
    engine = Engine(settings, tmp_path, store, store.create(tmp_path), lambda *a: None, AsyncMock())
    engine.state.update(request='Inspect the files', steps=0, observations=[], plan=None)
    engine.make_plan = AsyncMock(return_value=Plan(mode='plan', message='', actions=actions, success_criteria=[]))
    async def decide(state, questions):
        return {key: {'choice': 'supported' if key == 'support' else 'met' if key == 'original_task' else 'generate' if key == 'select_response' else 'execute'} for key in questions}
    engine.judge.decide = decide
    engine.runtime.complete = AsyncMock(return_value='Done')
    return engine, store


def read_action(name):
    return Action(id=name, tool='read_file', arguments_json=json.dumps({'path':name}),
        depends_on=[], purpose='Inspect source', condition='always')


@pytest.mark.asyncio
async def test_concurrency_bound_and_effect_barrier(tmp_path, monkeypatch):
    actions = [read_action('read_' + str(i)) for i in range(6)]
    actions.append(Action(id='effect', tool='shell', arguments_json='{"command":["example"]}',
        depends_on=[], purpose='Run requested action', condition='always'))
    engine, store = configured_engine(tmp_path, monkeypatch, actions, max_parallel_reads=2)
    active, high, completed_reads = 0, 0, 0
    async def execute(tool, args):
        nonlocal active, high, completed_reads
        if tool == 'shell':
            assert active == 0 and completed_reads == 6
            return {'exitCode': 0, 'stdout': 'ok'}
        active += 1
        high = max(high, active)
        try:
            await asyncio.sleep(.01)
            return {'content': args['path']}
        finally:
            active -= 1
            completed_reads += 1
    engine.tools.execute = execute
    try:
        assert await engine._loop() == 'Done'
        assert high == 2
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
async def test_parallel_reads_respect_remaining_step_budget(tmp_path, monkeypatch):
    engine, store = configured_engine(tmp_path, monkeypatch,
        [read_action('read_' + str(i)) for i in range(3)], max_steps=2, max_parallel_reads=4)
    engine.tools.execute = AsyncMock(return_value={'content': 'observed'})
    try:
        with pytest.raises(RuntimeError, match='Step budget'):
            await engine._loop()
        assert engine.tools.execute.await_count == 2
        assert engine.state['steps'] == 2
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
async def test_cancel_joins_all_inflight_reads_before_returning(tmp_path, monkeypatch):
    engine, store = configured_engine(tmp_path, monkeypatch,
        [read_action('first'), read_action('second')], max_parallel_reads=2)
    started = asyncio.Event()
    active = 0
    async def execute(tool, args):
        nonlocal active
        active += 1
        if active == 2:
            started.set()
        try:
            await asyncio.Event().wait()
        finally:
            active -= 1
    engine.tools.execute = execute
    task = asyncio.create_task(engine._loop())
    try:
        await asyncio.wait_for(started.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert active == 0
        assert engine.state['inflight'] == {}
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await engine.close()
        store.close()
