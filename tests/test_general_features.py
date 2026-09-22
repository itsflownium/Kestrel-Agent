import asyncio
import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from jsonschema import ValidationError

from kestrel_agent.config import Settings
from kestrel_agent.connections import Connection, ConnectionPool
from kestrel_agent.execution import docker_argv
from kestrel_agent.setup import configure
from kestrel_agent.workflow_templates import read, compile_workflow, install, load


def test_workflow_parameters_remain_typed_and_do_not_execute(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'home'))
    source = Path(__file__).parents[1]/'examples/workflows/read-document.json'
    name = install(source)
    workflow = load(name)
    plan, version = compile_workflow(workflow, {'path': 'report with spaces.md'})
    assert plan.actions[0].arguments() == {'path': 'report with spaces.md'}
    assert len(version) == 64 and not (tmp_path/'report with spaces.md').exists()
    for values in [{}, {'path': 123}, {'path': 'x', 'extra': True}]:
        with pytest.raises(ValidationError):
            compile_workflow(workflow, values)
    with pytest.raises(ValueError):
        install(source)
    invalid = copy.deepcopy(workflow)
    invalid['actions'][0]['tool'] = 'invented_tool'
    with pytest.raises(ValueError):
        compile_workflow(invalid, {'path': 'x'})


def test_workflow_remote_schema_and_cycles_rejected(tmp_path):
    source = Path(__file__).parents[1]/'examples/workflows/read-document.json'
    value = json.loads(source.read_text())
    value['parameters']['properties']['path'] = {'$ref': 'https://invalid.example/schema'}
    target = tmp_path/'workflow.json'
    target.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='references'):
        read(target)
    value = read(source)
    value['actions'][0]['depends_on'] = ['source']
    with pytest.raises(ValueError, match='dependency'):
        compile_workflow(value, {'path': 'x'})


@pytest.mark.asyncio
async def test_setup_cancel_and_validation_leave_original_unchanged():
    settings = Settings(agent_mode='standard')
    before = settings.model_dump()
    async def ask(label, default):
        if label.startswith('Reasoning'):
            raise EOFError()
        return 'new-model' if label.startswith('Model ID') else default
    with pytest.raises(EOFError):
        await configure(settings, ask, lambda text: None)
    assert settings.model_dump() == before
    async def bad(label, default):
        return 'bogus' if label.startswith('Command execution') else default
    with pytest.raises(ValueError):
        await configure(settings, bad, lambda text: None)
    assert settings.model_dump() == before


@pytest.mark.asyncio
async def test_setup_api_docker_and_optional_jev():
    answers = {'Provider': 'deepseek', 'Model ID': 'user-selected-model', 'Command execution': 'docker',
               'Decision mode': 'jev', 'Allow network': 'no'}
    async def ask(label, default):
        return next((value for key, value in answers.items() if label.startswith(key)), default)
    settings = await configure(Settings(agent_mode='standard'), ask, lambda text: None)
    assert settings.model == 'user-selected-model'
    assert settings.execution_backend == 'docker' and settings.agent_mode == 'jev' and not settings.network


def test_docker_scope_network_and_no_implicit_pull(tmp_path):
    sub = tmp_path/'nested'
    sub.mkdir()
    args = docker_argv(Settings(network=False, permission='read-only'), tmp_path, ['python', 'script.py'], str(sub), 'test-container')
    assert '--pull=never' in args and '--read-only' in args
    assert args[args.index('--network')+1] == 'none'
    assert args[args.index('--mount')+1].endswith('dst=/workspace,readonly')
    assert args[args.index('--workdir')+1] == '/workspace/nested'
    assert args[-2:] == ['python:3.13-slim', 'script.py']
    assert 'docker.sock' not in ' '.join(args)
    with pytest.raises(PermissionError):
        docker_argv(Settings(), tmp_path, ['pwd'], str(tmp_path.parent), 'test-container')


@pytest.mark.parametrize('url', ['http://remote.example/mcp', 'https://user:secret@host/mcp', 'https://host/mcp?token=secret', 'file:///tmp/mcp'])
def test_connection_requires_explicit_safe_endpoint(url):
    with pytest.raises(ValueError):
        Connection(url=url)


@pytest.mark.asyncio
async def test_connected_schema_rejects_invalid_arguments_before_dispatch():
    pool = ConnectionPool(Settings(mcp_connections={'demo': Connection(url='http://localhost:8000/mcp')}))
    pool.schemas['demo'] = {'count': {'type': 'object', 'properties': {'n': {'type': 'integer'}}, 'required': ['n'], 'additionalProperties': False}}
    pool.request = AsyncMock()
    with pytest.raises(ValidationError):
        await pool.call('demo', 'count', {'n': 'bad'})
    with pytest.raises(ValueError, match='catalog'):
        await pool.call('demo', 'nonexistent', {})
    pool.request.assert_not_called()


@pytest.mark.asyncio
async def test_missing_mcp_token_fails_promptly_without_connection(monkeypatch):
    monkeypatch.delenv('KESTREL_TEST_MISSING_TOKEN', raising=False)
    settings = Settings(mcp_connections={'demo': Connection(url='http://localhost:8000/mcp', bearer_env='KESTREL_TEST_MISSING_TOKEN')})
    pool = ConnectionPool(settings)
    try:
        with pytest.raises(RuntimeError, match='unavailable'):
            await asyncio.wait_for(pool.request('demo', 'list'), 2)
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_mcp_schema_cannot_trigger_remote_retrieval():
    pool = ConnectionPool(Settings(mcp_connections={'demo': Connection(url='http://localhost:8000/mcp')}))
    pool.schemas['demo'] = {'read': {'$ref': 'https://example.invalid/secret-schema'}}
    pool.request = AsyncMock()
    with pytest.raises(Exception, match='Unresolvable'):
        await pool.call('demo', 'read', {})
    pool.request.assert_not_called()
