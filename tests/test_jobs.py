import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest

from kestrel_agent.config import Settings, atomic_write
from kestrel_agent import jobs


def prepared(tmp_path, monkeypatch, *, confirm=True):
    private = tmp_path/'private'
    monkeypatch.setenv('KESTREL_HOME', str(private))
    workspace = tmp_path/'workspace'
    workspace.mkdir(exist_ok=True)
    job_id = uuid.uuid4().hex
    path = private/'jobs'/job_id
    path.mkdir(parents=True)
    settings = Settings(agent_mode='standard', network=False, shell=False, confirm_writes=confirm)
    request = {'request':'Save a file', 'workspace':str(workspace), 'settings':settings.model_dump()}
    record = {'id':job_id,'status':'starting','created':time.time(),'updated':time.time(),'workspace':str(workspace),'session':None}
    atomic_write(path/'request.json', json.dumps(request))
    atomic_write(path/'status.json', json.dumps(record))
    return job_id, path, workspace


class FileEngine:
    def __new__(cls, *args):
        from kestrel_agent.engine import Engine, GATE_PROMPT
        from kestrel_agent.schema import Action, Plan
        from kestrel_agent.scheduler import execute_plan
        plan = Plan(mode='plan', message='Save fixture', success_criteria=[], actions=[Action(id='save',tool='write_file',arguments_json=json.dumps({'path':'result.txt','content':'fixture','expected_sha256':None}),depends_on=[],purpose='Save',condition='always')])
        class ControlledEngine(Engine):
            async def run(self, message):
                return await super().run(message, initial_plan=plan)
            async def _loop(self):
                await execute_plan(self, plan, GATE_PROMPT)
                return 'Fixture finished'
        return ControlledEngine(*args)


def test_background_approval_stops_real_engine_without_writing(tmp_path, monkeypatch):
    job_id, path, workspace = prepared(tmp_path, monkeypatch)
    jobs.run_worker(job_id, FileEngine)
    result = jobs.status(job_id)
    assert result['status'] == 'needs_approval', result
    assert result['session'] and not result['worker_owned']
    assert not (workspace/'result.txt').exists()
    from kestrel_agent.store import Store
    store = Store(Settings())
    try:
        state = json.loads(store.session(result['session'])['state'])
        assert state['status'] == 'interrupted'
    finally:
        store.close()


def test_completed_job_has_real_file_and_does_not_restart(tmp_path, monkeypatch):
    job_id, path, workspace = prepared(tmp_path, monkeypatch, confirm=False)
    jobs.run_worker(job_id, FileEngine)
    result = jobs.status(job_id)
    assert result['status'] == 'completed'
    assert not result['worker_owned']
    assert (workspace/'result.txt').read_text() == 'fixture'
    jobs.run_worker(job_id, lambda *args: pytest.fail('Completed job restarted'))
    assert jobs.status(job_id)['session'] == result['session']


def test_cancel_before_start_never_constructs_engine(tmp_path, monkeypatch):
    job_id, path, workspace = prepared(tmp_path, monkeypatch)
    assert jobs.cancel(job_id)['cancel_requested']
    jobs.run_worker(job_id, lambda *args: pytest.fail('Cancelled job started'))
    assert jobs.status(job_id)['status'] == 'cancelled'
    assert not jobs.status(job_id)['session']


def test_workspace_lock_rejects_competing_worker(tmp_path, monkeypatch):
    job_id, path, workspace = prepared(tmp_path, monkeypatch)
    key = hashlib.sha256(str(workspace.resolve()).encode()).hexdigest()
    with jobs.ownership(path.parents[1]/'job_workspaces'/(key+'.lock')) as owned:
        assert owned
        jobs.run_worker(job_id, lambda *args: pytest.fail('Contending worker started'))
    assert jobs.status(job_id)['status'] == 'failed'
    assert 'Another background job' in jobs.status(job_id)['detail']


def test_stale_pid_is_never_signalled_or_trusted(tmp_path, monkeypatch):
    job_id, path, workspace = prepared(tmp_path, monkeypatch)
    state = json.loads((path/'status.json').read_text())
    state.update(status='running', pid=os.getpid())
    atomic_write(path/'status.json', json.dumps(state))
    monkeypatch.setattr(os, 'kill', lambda *args: pytest.fail('PID-based signal'))
    assert jobs.status(job_id)['status'] == 'lost_worker'
    assert jobs.cancel(job_id)['status'] == 'lost_worker'
    assert (path/'cancel.json').exists()


def test_worker_lock_is_authoritative_across_processes_and_cancel_cleans_up(tmp_path, monkeypatch):
    job_id, path, workspace = prepared(tmp_path, monkeypatch)
    script = '''
import asyncio, sys
from pathlib import Path
from kestrel_agent.jobs import run_worker
class WaitingEngine:
    def __init__(self, settings, workspace, store, sid, emit, confirm):
        self.workspace = workspace
    async def run(self, message):
        await asyncio.Future()
    async def close(self):
        (self.workspace/'closed.txt').write_text('closed')
run_worker(sys.argv[1], WaitingEngine)
'''
    process = subprocess.Popen([sys.executable,'-c',script,job_id], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            state = jobs.status(job_id)
            if state['status'] == 'running' and state['worker_owned']:
                break
            assert process.poll() is None, process.communicate()
            time.sleep(.05)
        else:
            pytest.fail('Worker never acquired ownership')
        jobs.cancel(job_id)
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr
        assert jobs.status(job_id)['status'] == 'cancelled'
        assert not jobs.status(job_id)['worker_owned']
        assert (workspace/'closed.txt').read_text() == 'closed'
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_job_ids_cannot_escape_storage(tmp_path, monkeypatch):
    prepared(tmp_path, monkeypatch)
    for value in ['../elsewhere', '/tmp', 'abc', 'f'*33]:
        with pytest.raises(ValueError):
            jobs.status(value)


def test_old_live_session_is_protected_beyond_list_page(tmp_path, monkeypatch):
    job_id, path, workspace = prepared(tmp_path, monkeypatch)
    original = json.loads((path/'status.json').read_text())
    original.update(session='owned-session', status='running', created=1)
    atomic_write(path/'status.json', json.dumps(original))
    for index in range(101):
        newer = path.parent/uuid.uuid4().hex
        newer.mkdir()
        atomic_write(newer/'status.json', json.dumps({**original,'id':newer.name,'session':None,'status':'completed','created':index+2}))
    with jobs.ownership(path/'worker.lock'):
        assert len(jobs.list_jobs()) == 100
        with pytest.raises(ValueError, match='owned by background job'):
            jobs.assert_session_available('owned-session')
    jobs.assert_session_available('owned-session')


def test_start_uses_private_files_and_detached_worker(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'private'))
    workspace = tmp_path/'work'
    workspace.mkdir()
    calls = []
    class Worker:
        def wait(self):
            return 0
    def launch(args, **kwargs):
        calls.append((args, kwargs))
        return Worker()
    monkeypatch.setattr(subprocess, 'Popen', launch)
    job_id = jobs.start('Inspect the supplied project', workspace, Settings(agent_mode='standard'))
    path = jobs.directory(job_id)
    assert calls[0][0][-1] == job_id
    assert 'Inspect the supplied project' not in str(calls[0][0])
    assert calls[0][1]['start_new_session'] and calls[0][1]['close_fds']
    assert calls[0][1]['stdin'] == subprocess.DEVNULL
    for name in ['request.json', 'status.json', 'worker.log']:
        assert (path/name).stat().st_mode & 0o777 == 0o600
    assert path.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize('failure', [RuntimeError('cleanup failed'), asyncio.CancelledError('cleanup failed')])
def test_cleanup_failure_is_not_reported_as_completed(tmp_path, monkeypatch, failure):
    job_id, path, workspace = prepared(tmp_path, monkeypatch)
    class BrokenCleanup:
        def __init__(self, *args):
            pass
        async def run(self, message):
            return 'done'
        async def close(self):
            raise failure
    jobs.run_worker(job_id, BrokenCleanup)
    assert jobs.status(job_id)['status'] == 'failed'
    assert 'cleanup failed' in jobs.status(job_id)['detail']


def test_clarification_is_needs_input_not_completed(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock
    from kestrel_agent.engine import Engine
    from kestrel_agent.schema import Plan
    from kestrel_agent import fastpath, prefetch
    job_id, path, workspace = prepared(tmp_path, monkeypatch)
    monkeypatch.setattr(fastpath, 'try_fastpath', AsyncMock(return_value=None))
    monkeypatch.setattr(prefetch, 'prefetch', AsyncMock())
    def factory(*args):
        engine = Engine(*args)
        engine.make_plan = AsyncMock(return_value=Plan(mode='clarify',message='Which file should I use?',actions=[],success_criteria=[]))
        return engine
    jobs.run_worker(job_id, factory)
    report = jobs.status(job_id)
    assert report['status'] == 'needs_input'
    assert report['answer'] == 'Which file should I use?'
    from kestrel_agent.store import Store
    store = Store(Settings())
    try:
        engine = Engine(Settings(agent_mode='standard'), workspace, store, report['session'], lambda *args:None, AsyncMock())
        assert engine.state['status'] == 'needs_input'
        engine.amend('Use notes.txt')
        assert engine.state['request'].endswith('Use notes.txt')
        asyncio.run(engine.close())
    finally:
        store.close()
