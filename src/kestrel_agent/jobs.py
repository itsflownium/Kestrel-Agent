"""Detached job ownership and cooperative cancellation (macOS/Linux)."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import threading
import uuid

from .config import Settings, atomic_write, home, load_secrets, redact

TERMINAL = {'completed', 'cancelled', 'needs_approval', 'needs_input', 'failed'}


def directory(job_id):
    if not re.fullmatch('[a-f0-9]{32}', job_id):
        raise ValueError('Expected a complete job ID from kestrel jobs list.')
    path = home()/'jobs'/job_id
    if not path.is_dir() or path.is_symlink():
        raise ValueError('Unknown job ID.')
    return path


@contextmanager
def ownership(path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
        else:
            yield True
    finally:
        os.close(fd)


def owned(path):
    with ownership(path) as acquired:
        return not acquired


def status(job_id):
    path = directory(job_id)
    value = json.loads((path/'status.json').read_text())
    live = owned(path/'worker.lock')
    value['worker_owned'] = live
    if not live and value['status'] in {'running', 'stopping', 'finishing'}:
        value['status'] = 'lost_worker'
        value['detail'] = 'Worker ownership ended without a terminal checkpoint. Inspect the session before continuing; effects may be uncertain.'
    elif not live and value['status'] == 'starting' and time.time() - value['created'] > 60:
        value['status'] = 'lost_worker'
        value['detail'] = 'No worker acquired ownership within the startup window.'
    return value


def list_jobs(limit=100):
    root = home()/'jobs'
    if not root.exists():
        return []
    rows = []
    for path in root.iterdir():
        if re.fullmatch('[a-f0-9]{32}', path.name) and path.is_dir() and not path.is_symlink():
            try:
                rows.append(status(path.name))
            except (OSError, ValueError):
                continue
    ordered = sorted(rows, key=lambda item: item['created'], reverse=True)
    return ordered if limit is None else ordered[:limit]


def cancel(job_id):
    path = directory(job_id)
    current = status(job_id)
    if current['status'] in TERMINAL:
        return current
    atomic_write(path/'cancel.json', json.dumps({'requested':time.time()}))
    return {**current, 'cancel_requested':True,
            'detail':'Cancellation requested. The worker must checkpoint and close before it is stopped.'}


def assert_session_available(session_id):
    for record in list_jobs(limit=None):
        if record.get('session') == session_id and record['worker_owned']:
            raise ValueError(f"Session is owned by background job {record['id']}. Cancel it and wait for worker_owned=false before resuming.")


def start(request, workspace, settings):
    request = request.strip()
    workspace = Path(workspace).resolve()
    if not request or len(request) > 32000:
        raise ValueError('A background task must contain 1–32000 characters.')
    if not workspace.is_dir():
        raise ValueError('A background job requires an existing workspace directory.')
    job_id = uuid.uuid4().hex
    root = home()/'jobs'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root/job_id
    path.mkdir(mode=0o700)
    now = time.time()
    record = {'id':job_id, 'status':'starting', 'created':now, 'updated':now,
              'workspace':str(workspace), 'session':None,
              'detail':'Waiting for the worker to acquire ownership.'}
    atomic_write(path/'request.json', json.dumps({'request':request, 'workspace':str(workspace), 'settings':settings.model_dump()}))
    atomic_write(path/'status.json', json.dumps(record))
    log_fd = os.open(path/'worker.log', os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
    try:
        with os.fdopen(log_fd, 'w') as output:
            worker = subprocess.Popen([sys.executable, '-m', 'kestrel_agent.jobs', job_id],
                                      stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                      env={**os.environ, 'KESTREL_HOME':str(home())},
                                      cwd=workspace, start_new_session=True, close_fds=True)
            # PID is deliberately not used for ownership or cancellation.
            threading.Thread(target=worker.wait, daemon=True).start()
    except Exception:
        record.update(status='failed', detail='Could not launch the background worker.', updated=time.time())
        atomic_write(path/'status.json', json.dumps(record))
        raise
    return job_id


async def execute_job(path, record, request, engine_factory=None):
    from .engine import Engine
    from .store import Store
    settings = Settings.model_validate(request['settings'])
    load_secrets()
    store = Store(settings)
    engine = None
    task = None
    approval = None
    last_phase = 'Starting'
    outcome = {}
    def save(**changes):
        record.update(changes, updated=time.time())
        atomic_write(path/'status.json', json.dumps(record))
    def emit(kind, message):
        nonlocal last_phase
        last_phase = redact(str(message))[:200]
    async def confirm(description):
        nonlocal approval
        approval = redact(description)[:6000]
        # Do not deny and let a model repeatedly repair around that denial.
        # Stop the whole task at the first requested permission instead.
        raise asyncio.CancelledError
    try:
        sid = store.create(Path(request['workspace']), request['request'][:100])
        save(status='running', session=sid, detail='Worker owns this task.')
        engine = (engine_factory or Engine)(settings, Path(request['workspace']), store, sid, emit, confirm)
        task = asyncio.create_task(engine.run(request['request']))
        while not task.done():
            if (path/'cancel.json').exists():
                save(status='stopping', detail='Cancellation requested; waiting for task cleanup.')
                task.cancel()
                break
            save(phase=last_phase)
            await asyncio.wait({task}, timeout=0.5)
        try:
            answer = await task
        except asyncio.CancelledError:
            if approval is not None:
                outcome = {'status':'needs_approval', 'detail':approval}
            else:
                outcome = {'status':'cancelled', 'detail':'Worker cancellation finished. Inspect the checkpoint before resuming.'}
        else:
            if getattr(engine, 'state', {}).get('status') == 'needs_input':
                outcome = {'status':'needs_input', 'answer':redact(answer), 'detail':'The task needs your answer. Reopen its session and use /steer YOUR ANSWER.'}
            else:
                outcome = {'status':'completed', 'answer':redact(answer), 'detail':'Task completed; answer and evidence are in the saved session.'}
    except Exception as error:
        outcome = {'status':'failed', 'detail':redact(str(error))[:1000]}
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        try:
            save(status='finishing', detail='Closing worker resources before the final checkpoint.')
            if engine is not None:
                await engine.close()
        except (Exception, asyncio.CancelledError) as error:
            outcome = {'status':'failed', 'detail':'Worker cleanup failed: ' + redact(str(error))[:800]}
        finally:
            store.close()
            save(**outcome)


def run_worker(job_id, engine_factory=None):
    path = directory(job_id)
    with ownership(path/'worker.lock') as acquired:
        if not acquired:
            return
        record = json.loads((path/'status.json').read_text())
        if record['status'] != 'starting':
            return  # Never restart a crashed/finished job automatically.
        if (path/'cancel.json').exists():
            record.update(status='cancelled', updated=time.time(), detail='Cancelled before execution.')
            atomic_write(path/'status.json', json.dumps(record))
            return
        request = json.loads((path/'request.json').read_text())
        # This prevents two managed background jobs from writing one workspace.
        # It is not a filesystem sandbox and cannot lock out unrelated programs.
        key = hashlib.sha256(str(Path(request['workspace']).resolve()).encode()).hexdigest()
        with ownership(home()/'job_workspaces'/(key+'.lock')) as workspace_acquired:
            if not workspace_acquired:
                record.update(status='failed', updated=time.time(), detail='Another background job owns this workspace; no task actions ran.')
                atomic_write(path/'status.json', json.dumps(record))
                return
            try:
                asyncio.run(execute_job(path, record, request, engine_factory))
            except Exception as error:
                record.update(status='failed', updated=time.time(), detail='Worker startup or cleanup failed: ' + redact(str(error))[:800])
                atomic_write(path/'status.json', json.dumps(record))


if __name__ == '__main__':
    run_worker(sys.argv[1])
