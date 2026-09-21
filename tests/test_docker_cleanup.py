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
if args[0]=='run':
    if mode=='output':
        sys.stdout.write('x'*70000); sys.stderr.write('y'*70000); sys.exit(7)
    time.sleep(30)
if args[0]=='rm':
    sys.exit(1 if mode in ('denied','absent') else 0)
if args[0]=='ps':
    sys.exit(1 if mode=='denied' else 0)
''')
    binary.chmod(0o755)
    log=tmp_path/'calls.jsonl'
    monkeypatch.setenv('PATH', str(tmp_path)+os.pathsep+os.environ['PATH'])
    monkeypatch.setenv('FAKE_LOG', str(log))
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
        if log.exists(): break
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
    assert [json.loads(line)[0] for line in log.read_text().splitlines()]==['rm','ps']
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
