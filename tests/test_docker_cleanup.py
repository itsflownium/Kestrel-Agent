"""Process conformance with a fake Docker CLI; not container-isolation tests."""
import asyncio
import json
import os
import sys

import pytest
from kestrel_agent.config import Settings
from kestrel_agent.execution import DockerExecutor


@pytest.fixture
def docker(tmp_path, monkeypatch):
    binary = tmp_path/'docker'
    binary.write_text(f'#!{sys.executable}\n' + '''import sys, os, json, time
from pathlib import Path
args=sys.argv[1:]
with open(os.environ['FAKE_LOG'],'a') as f: f.write(json.dumps(args)+'\\n')
mode=os.environ.get('FAKE_MODE','success')
state=Path(os.environ['FAKE_STATE']); state.mkdir(exist_ok=True)
if args[0]=='context':
    print(json.dumps([{'Name': os.environ.get('FAKE_CONTEXT','fixture'), 'Endpoints': {'docker': {'Host': 'fixture'}}}]))
    sys.exit(0)
if args[0]=='inspect':
    target=state/args[-1]
    if mode=='denied': sys.exit(1)
    if mode=='absent': target.unlink(missing_ok=True)
    if not target.exists(): sys.exit(1)
    print('foreign-owner' if mode=='foreign' else args[-1]); sys.exit(0)
if args[0]=='run':
    target=state/args[args.index('--name')+1]; target.write_text('running')
    if mode=='output':
        sys.stdout.write('x'*70000); sys.stderr.write('y'*70000); sys.exit(7)
    deadline=time.monotonic()+30
    while target.exists() and time.monotonic()<deadline: time.sleep(.02)
if args[0]=='rm':
    if mode in ('denied','absent'): sys.exit(1)
    (state/args[-1]).unlink(missing_ok=True)
    sys.exit(0)
if args[0]=='ps':
    if mode=='denied': sys.exit(1)
    name=args[-1].removeprefix('name=^/').removesuffix('$')
    if (state/name).exists(): print(name)
    sys.exit(0)
''')
    binary.chmod(0o755)
    log=tmp_path/'calls.jsonl'
    monkeypatch.setenv('PATH', str(tmp_path)+os.pathsep+os.environ['PATH'])
    monkeypatch.setenv('FAKE_LOG', str(log))
    monkeypatch.setenv('FAKE_STATE', str(tmp_path/'containers'))
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'kestrel-state'))
    settings=Settings(execution_backend='docker',command_timeout_seconds=1)
    executor=DockerExecutor(settings,tmp_path)
    return executor, log


@pytest.mark.asyncio
async def test_timeout_removes_container_and_reaps_cli(docker):
    executor,log=docker
    with pytest.raises(asyncio.TimeoutError):
        await executor.command(['sleep','30'],str(executor.workspace))
    calls=[json.loads(line) for line in log.read_text().splitlines()]
    assert any(call[0]=='rm' for call in calls)
    assert not executor.active and not executor.pending_cleanup


@pytest.mark.asyncio
async def test_cancel_reports_failed_cleanup_and_close_retries(docker,monkeypatch):
    executor,log=docker
    monkeypatch.setenv('FAKE_MODE','denied')
    task=asyncio.create_task(executor.command(['sleep','30'],str(executor.workspace)))
    for _ in range(100):
        if log.exists() and any(json.loads(line)[0] == 'run' for line in log.read_text().splitlines()): break
        await asyncio.sleep(.01)
    task.cancel()
    with pytest.raises(RuntimeError,match='Could not confirm container cleanup'):
        await task
    assert not executor.active and executor.pending_cleanup
    monkeypatch.setenv('FAKE_MODE','success')
    await executor.close()
    assert not executor.pending_cleanup


@pytest.mark.asyncio
async def test_already_removed_container_requires_successful_absence_check(docker,monkeypatch):
    executor,log=docker
    monkeypatch.setenv('FAKE_MODE','absent')
    await executor._remove('kestrel-test')
    assert [json.loads(line)[0] for line in log.read_text().splitlines()]==['inspect','ps']
    assert not executor.pending_cleanup


@pytest.mark.asyncio
async def test_output_is_drained_bounded_and_exit_preserved(docker,monkeypatch):
    executor,_=docker
    monkeypatch.setenv('FAKE_MODE','output')
    result=await executor.command(['echo','test'],str(executor.workspace))
    assert result['exitCode']==7
    assert result['output_truncated']
    assert len(result['stdout'])==len(result['stderr'])==32000
    assert not executor.active


@pytest.mark.asyncio
async def test_unresolved_cleanup_prevents_new_execution(docker,monkeypatch):
    executor,log=docker
    monkeypatch.setenv('FAKE_MODE','denied')
    executor.pending_cleanup.add('kestrel-unresolved')
    with pytest.raises(RuntimeError,match='cleanup'):
        await executor.command(['echo','new'],str(executor.workspace))
    assert all(json.loads(line)[0]!='run' for line in log.read_text().splitlines())


@pytest.mark.asyncio
async def test_runtime_closes_other_clients_when_docker_cleanup_fails():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from kestrel_agent.providers import Runtime
    runtime=object.__new__(Runtime)
    runtime.connections=SimpleNamespace(close=AsyncMock())
    runtime.docker=SimpleNamespace(close=AsyncMock(side_effect=RuntimeError('unresolved container')))
    runtime.generator=SimpleNamespace(close=AsyncMock())
    runtime.codex=SimpleNamespace(close=AsyncMock())
    runtime.cancel=AsyncMock()
    runtime.started=True
    with pytest.raises(ExceptionGroup,match='Runtime cleanup failed'):
        await runtime.close()
    runtime.generator.close.assert_awaited_once()
    runtime.cancel.assert_awaited_once()
    runtime.codex.close.assert_awaited_once()
    assert not runtime.started


@pytest.mark.asyncio
async def test_client_exit_still_removes_container_and_clears_receipt(docker, monkeypatch):
    executor, log = docker
    monkeypatch.setenv('FAKE_MODE', 'output')
    result = await executor.command(['echo', 'test'], str(executor.workspace))
    assert result['exitCode'] == 7
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    launched = next(call for call in calls if call[0] == 'run')
    name = launched[launched.index('--name') + 1]
    assert launched[launched.index('--label') + 1] == 'io.kestrel.owner=' + name
    assert any(call == ['rm', '-f', name] for call in calls)
    assert not executor.receipt_path().exists()
    assert not list((executor.workspace/'containers').iterdir())


@pytest.mark.asyncio
async def test_foreign_label_preserves_receipt_and_blocks_replacement(docker, monkeypatch):
    executor, log = docker
    monkeypatch.setenv('FAKE_MODE', 'foreign')
    with pytest.raises(RuntimeError, match='cleanup'):
        await executor.command(['sleep', '30'], str(executor.workspace))
    assert executor.receipt_path().exists()
    previous = log.read_text()
    replacement = DockerExecutor(executor.settings, executor.workspace)
    with pytest.raises(RuntimeError, match='cleanup'):
        await replacement.command(['echo', 'new'], str(executor.workspace))
    new_calls = [json.loads(line) for line in log.read_text()[len(previous):].splitlines()]
    assert all(call[0] not in {'run', 'rm'} for call in new_calls)
    monkeypatch.setenv('FAKE_MODE', 'success')
    await executor.close()


@pytest.mark.asyncio
async def test_changed_daemon_configuration_does_not_discard_pending_receipt(docker, monkeypatch):
    executor, log = docker
    monkeypatch.setenv('FAKE_MODE', 'denied')
    with pytest.raises(RuntimeError, match='cleanup'):
        await executor.command(['sleep', '30'], str(executor.workspace))
    saved = executor.receipt_path().read_bytes()
    previous = log.read_text()
    monkeypatch.setenv('FAKE_MODE', 'output')
    monkeypatch.setenv('FAKE_CONTEXT', 'different-daemon')
    replacement = DockerExecutor(executor.settings, executor.workspace)
    with pytest.raises(RuntimeError, match='cleanup'):
        await replacement.command(['echo', 'new'], str(executor.workspace))
    assert executor.receipt_path().read_bytes() == saved
    assert all(json.loads(line)[0] == 'context' for line in log.read_text()[len(previous):].splitlines())
    monkeypatch.delenv('FAKE_CONTEXT')
    await executor.close()


@pytest.mark.asyncio
async def test_live_workspace_owner_is_not_interrupted_by_second_executor(docker, monkeypatch):
    executor, log = docker
    task = asyncio.create_task(executor.command(['sleep', '30'], str(executor.workspace)))
    try:
        for _ in range(100):
            if log.exists() and any(json.loads(line)[0] == 'run' for line in log.read_text().splitlines()): break
            await asyncio.sleep(.01)
        assert not task.done()
        replacement = DockerExecutor(executor.settings, executor.workspace)
        with pytest.raises(RuntimeError, match='owns this workspace'):
            await replacement.command(['echo', 'new'], str(executor.workspace))
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
    assert not executor.receipt_path().exists()


@pytest.mark.asyncio
async def test_next_process_recovers_receipt_after_owner_is_killed(docker, monkeypatch):
    import signal
    from pathlib import Path
    executor, log = docker
    script = '''import asyncio, sys
from pathlib import Path
from kestrel_agent.config import Settings
from kestrel_agent.execution import DockerExecutor
asyncio.run(DockerExecutor(Settings(execution_backend='docker', command_timeout_seconds=30), Path(sys.argv[1])).command(['sleep','30'],sys.argv[1]))
'''
    worker = await asyncio.create_subprocess_exec(sys.executable, '-c', script, str(executor.workspace),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE, start_new_session=True)
    try:
        for _ in range(200):
            if log.exists() and any(json.loads(line)[0] == 'run' for line in log.read_text().splitlines()): break
            if worker.returncode is not None: pytest.fail((await worker.stderr.read()).decode())
            await asyncio.sleep(.01)
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        assert any(call[0] == 'run' for call in calls)
        old = json.loads(executor.receipt_path().read_text())['name']
        worker.kill()
        await asyncio.wait_for(worker.wait(), 5)
        assert (Path(os.environ['FAKE_STATE'])/old).exists()
        monkeypatch.setenv('FAKE_MODE', 'output')
        result = await executor.command(['echo', 'recovered'], str(executor.workspace))
        assert result['exitCode'] == 7
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        runs = [index for index, call in enumerate(calls) if call[0] == 'run']
        removal = calls.index(['rm', '-f', old])
        assert runs[0] < removal < runs[1]
        assert not executor.receipt_path().exists()
        assert not list(Path(os.environ['FAKE_STATE']).iterdir())
    finally:
        try: os.killpg(worker.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        await worker.wait()


@pytest.mark.asyncio
async def test_invalid_receipt_does_not_dispatch_docker(docker):
    executor, log = docker
    receipt = executor.receipt_path()
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({'name': 'unrelated', 'workspace': str(executor.workspace)}))
    with pytest.raises(RuntimeError, match='Invalid Docker cleanup receipt'):
        await executor.command(['echo', 'new'], str(executor.workspace))
    assert not log.exists()
    assert receipt.exists()


@pytest.mark.asyncio
async def test_cancel_during_spawn_reaps_client_before_container_cleanup(docker, monkeypatch):
    executor, log = docker
    create = asyncio.create_subprocess_exec
    spawned = asyncio.Event()
    release = asyncio.Event()
    clients = []
    async def delayed(*args, **kwargs):
        process = await create(*args, **kwargs)
        if args[:2] == ('docker', 'run'):
            clients.append(process)
            # Wait until the fake daemon has accepted the named run.
            for _ in range(100):
                if log.exists() and any(json.loads(line)[0] == 'run' for line in log.read_text().splitlines()): break
                await asyncio.sleep(.01)
            spawned.set()
            await release.wait()
        return process
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', delayed)
    task = asyncio.create_task(executor.command(['sleep', '30'], str(executor.workspace)))
    try:
        await asyncio.wait_for(spawned.wait(), 3)
        task.cancel()
        await asyncio.sleep(.01)
        task.cancel()  # Repeated interrupts still must not orphan the launch.
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 3)
        assert clients and all(process.returncode is not None for process in clients)
        assert not executor.active and not executor.pending_cleanup
        assert not executor.receipt_path().exists()
        assert not list((executor.workspace/'containers').iterdir())
    finally:
        release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_launch_task_does_not_spin_or_start_another_run(docker, monkeypatch):
    executor, log = docker
    create = asyncio.create_subprocess_exec
    async def cancelled_launch(*args, **kwargs):
        if args[:2] == ('docker', 'run'):
            raise asyncio.CancelledError
        return await create(*args, **kwargs)
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', cancelled_launch)
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(executor.command(['sleep', '30'], str(executor.workspace)), 3)
    assert not executor.receipt_path().exists()
    assert all(json.loads(line)[0] != 'run' for line in log.read_text().splitlines())
