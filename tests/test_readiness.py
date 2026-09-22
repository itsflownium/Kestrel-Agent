import asyncio
import io
import os
from pathlib import Path
import sys
from unittest.mock import AsyncMock

import pytest
from rich.console import Console
from typer.testing import CliRunner

from kestrel_agent import readiness
from kestrel_agent.cli import app
from kestrel_agent.config import Settings


def isolate(monkeypatch, tmp_path):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'state'))
    monkeypatch.setattr(readiness.sys, 'platform', 'linux')
    monkeypatch.setattr(readiness.importlib.util, 'find_spec', lambda name: object() if name == 'playwright' else None)
    monkeypatch.setattr(readiness.shutil, 'which', lambda name: '/docker')


@pytest.mark.asyncio
async def test_offline_checks_do_not_probe_runtimes_or_require_jev(tmp_path, monkeypatch):
    isolate(monkeypatch, tmp_path)
    probe = AsyncMock()
    monkeypatch.setattr(readiness, 'command_ready', probe)
    monkeypatch.setattr(readiness, 'chromium_ready', probe)
    rows = await readiness.inspect_readiness(Settings(agent_mode='standard', execution_backend='docker'))
    assert next(r for r in rows if r['name'] == 'Jev')['state'] == 'disabled'
    assert next(r for r in rows if r['name'] == 'Docker')['state'] == 'unverified'
    assert next(r for r in rows if r['name'] == 'Browser')['state'] == 'unverified'
    probe.assert_not_called()


@pytest.mark.asyncio
async def test_api_key_presence_does_not_claim_authentication_or_model_readiness(tmp_path, monkeypatch):
    from kestrel_agent import generation
    isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(generation, 'api_key', lambda settings: 'private-key-do-not-display')
    rows = await readiness.inspect_readiness(Settings(provider='openai-compatible', model=None, agent_mode='standard'))
    assert next(r for r in rows if r['name'] == 'Model selection')['state'] == 'missing'
    assert next(r for r in rows if r['name'] == 'Model authentication')['state'] == 'configured'
    assert 'validity is not checked' in next(r for r in rows if r['name'] == 'Model authentication')['detail']
    assert 'private-key' not in str(rows)


@pytest.mark.asyncio
async def test_desktop_permission_check_does_not_call_application_controls(tmp_path, monkeypatch):
    from types import SimpleNamespace
    isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(readiness.sys, 'platform', 'darwin')
    monkeypatch.setattr(readiness.importlib.util, 'find_spec', lambda name: object())
    monkeypatch.setitem(sys.modules, 'ApplicationServices', SimpleNamespace(AXIsProcessTrusted=lambda: False))
    rows = await readiness.inspect_readiness(Settings(agent_mode='standard'))
    assert next(r for r in rows if r['name'] == 'Desktop Accessibility')['state'] == 'missing'


@pytest.mark.asyncio
@pytest.mark.parametrize('daemon,image', [(False, False), (True, False), (True, True)])
async def test_runtime_checks_distinguish_daemon_and_image_without_running_tasks(tmp_path, monkeypatch, daemon, image):
    isolate(monkeypatch, tmp_path)
    probe = AsyncMock(side_effect=[daemon, image])
    monkeypatch.setattr(readiness, 'command_ready', probe)
    monkeypatch.setattr(readiness, 'chromium_ready', AsyncMock(return_value=True))
    rows = await readiness.inspect_readiness(Settings(execution_backend='docker'), runtime_checks=True)
    assert next(r for r in rows if r['name'] == 'Docker daemon')['state'] == ('ready' if daemon else 'unavailable')
    assert probe.await_count == (2 if daemon else 1)
    if daemon:
        assert next(r for r in rows if r['name'] == 'Docker image')['state'] == ('ready' if image else 'missing')
        assert probe.call_args.args[-2] == '--'
    assert all('run' not in call.args and 'pull' not in call.args for call in probe.call_args_list)


@pytest.mark.asyncio
async def test_probe_failures_are_bounded_and_do_not_echo_sensitive_output(tmp_path, monkeypatch):
    isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(readiness, 'command_ready', AsyncMock(side_effect=TimeoutError('private endpoint detail')))
    monkeypatch.setattr(readiness, 'chromium_ready', AsyncMock(side_effect=RuntimeError('private path')))
    rows = await readiness.inspect_readiness(Settings(execution_backend='docker'), runtime_checks=True)
    assert 'private' not in str(rows)
    assert next(r for r in rows if r['name'] == 'Docker runtime')['state'] == 'unavailable'
    assert next(r for r in rows if r['name'] == 'Browser')['state'] == 'unavailable'


@pytest.mark.asyncio
async def test_process_timeout_kills_and_reaps_probe(tmp_path):
    pid_file = tmp_path/'pid'
    script = 'import os,sys,time; from pathlib import Path; Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(60)'
    with pytest.raises(TimeoutError):
        await readiness.command_ready(sys.executable, '-c', script, str(pid_file))
    pid = int(pid_file.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_cli_doctor_reports_standard_mode_without_jev_warning(tmp_path, monkeypatch):
    isolate(monkeypatch, tmp_path)
    Settings(agent_mode='standard').save()
    result = CliRunner().invoke(app, ['doctor'])
    assert result.exit_code == 0, result.output
    assert 'Standard mode does not require' in result.output
    assert 'Jev key: missing' not in result.output


@pytest.mark.asyncio
async def test_chat_doctor_runtime_uses_explicit_probe_flag(tmp_path, monkeypatch):
    from kestrel_agent.ui import Terminal
    inspect = AsyncMock(return_value=[])
    monkeypatch.setattr(readiness, 'inspect_readiness', inspect)
    terminal = object.__new__(Terminal)
    terminal.settings = Settings()
    terminal.console = Console(file=io.StringIO())
    await terminal.command('/doctor')
    assert inspect.call_args.kwargs['runtime_checks'] is False
    await terminal.command('/doctor runtime')
    assert inspect.call_args.kwargs['runtime_checks'] is True
