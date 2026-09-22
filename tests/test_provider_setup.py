import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from typer.testing import CliRunner

from kestrel_agent.cli import app
from kestrel_agent.config import Settings
from kestrel_agent.generation import HTTPGenerator, api_key, save_key
from kestrel_agent.provider_presets import PRESETS, credential_envs, select
from kestrel_agent.providers import Runtime
from kestrel_agent.ui import Terminal


@pytest.fixture
def private(monkeypatch, tmp_path):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path / 'private'))
    for name in credential_envs(Settings()):
        monkeypatch.setenv(name, '')
    return tmp_path / 'private'


@pytest.mark.asyncio
@pytest.mark.parametrize('name', [name for name in PRESETS if name != 'codex'])
async def test_named_provider_wire_contract(private, name):
    settings = select(Settings(), name, model='user-selected-model')
    save_key(settings, 'dummy-provider-secret')
    def handler(request):
        preset = PRESETS[name]
        native = name == 'anthropic'
        assert str(request.url) == preset.base_url + ('/messages' if native else '/chat/completions')
        header = 'x-api-key' if native else preset.auth_header
        assert request.headers[header] == ('Bearer ' if header == 'authorization' else '') + 'dummy-provider-secret'
        body = json.loads(request.content)
        assert body['model'] == 'user-selected-model'
        assert body[preset.token_parameter] == settings.provider_max_tokens
        assert 'reasoning_effort' not in body
        if native:
            return httpx.Response(200, json={'stop_reason':'end_turn','content':[{'type':'text','text':'ok'}]})
        return httpx.Response(200, json={'choices':[{'finish_reason':'stop','message':{'content':'ok'}}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert (await HTTPGenerator(settings, client).complete('test'))[0] == 'ok'


def test_switch_resets_transport_and_keeps_endpoint_keys_isolated(private):
    mimo = select(Settings(), 'xiaomei', model='any')
    poolside = select(mimo, 'poolside', model='another')
    assert poolside.provider_auth_header == 'authorization'
    assert poolside.provider_token_parameter == 'max_tokens'
    assert poolside.provider_api_key_env == 'POOLSIDE_API_KEY'
    save_key(mimo, 'mimo-secret')
    assert not api_key(poolside)
    assert not api_key(select(mimo, 'mimo', base_url='https://separate.test/v1'))
    assert select(poolside, 'kimi').provider_profile == 'moonshot'
    assert select(poolside, 'claude').provider == 'anthropic'
    assert select(poolside, 'codex').model is None


def test_cli_provider_asks_for_both_keys_privately(private):
    Settings(agent_mode="jev").save()  # Existing Jev installations keep their mode.
    result = CliRunner().invoke(app, ['provider','poolside','--model','chosen-id'], input='poolside-dummy-secret\napikey_dummy_jev_secret\n')
    assert result.exit_code == 0, result.output
    assert 'Jev API key' in result.output and 'Provider API key' in result.output
    assert 'poolside-dummy-secret' not in result.output and 'apikey_dummy_jev_secret' not in result.output
    settings = Settings.load()
    assert settings.model == 'chosen-id' and settings.provider_profile == 'poolside'
    assert api_key(settings) == 'poolside-dummy-secret'
    assert 'apikey_dummy_jev_secret' in (private/'secrets.env').read_text()
    again = CliRunner().invoke(app, ['provider','poolside','--model','different-id'])
    assert again.exit_code == 0
    assert 'API key' not in again.output


def test_auth_poolside_does_not_switch_model_and_prompts_jev(private):
    Settings(model='existing').save()
    result = CliRunner().invoke(app, ['auth','poolside'], input='poolside-dummy-secret\n\n')
    assert result.exit_code == 0, result.output
    assert Settings.load().model == 'existing'
    assert api_key(select(Settings(), 'poolside')) == 'poolside-dummy-secret'
    assert 'Jev API key' in result.output
    assert not (private/'secrets.env').exists()


def test_cli_custom_endpoint_and_unknown_provider(private):
    result = CliRunner().invoke(app, ['provider','custom','--model','local-id','--base-url','http://localhost:8000/v1'], input='\n\n')
    assert result.exit_code == 0, result.output
    assert Settings.load().provider_base_url == 'http://localhost:8000/v1'
    bad = CliRunner().invoke(app, ['provider','made-up','--model','x'])
    assert bad.exit_code != 0 and 'Unknown provider' in bad.output


@pytest.mark.asyncio
async def test_startup_only_prompts_missing_keys(private, monkeypatch):
    terminal = SimpleNamespace(settings=select(Settings(), 'deepseek'), configure_key=AsyncMock())
    await Terminal.ensure_keys(terminal)
    assert [call.args for call in terminal.configure_key.await_args_list] == [(False,), (True,)]
    terminal.configure_key.reset_mock()
    save_key(terminal.settings, 'dummy-secret')
    monkeypatch.setenv('TYPESAFE_API_KEY', 'apikey_dummy')
    await Terminal.ensure_keys(terminal)
    terminal.configure_key.assert_not_called()
    monkeypatch.delenv('TYPESAFE_API_KEY')
    terminal.settings = Settings()
    await Terminal.ensure_keys(terminal)
    terminal.configure_key.assert_awaited_once_with(True)


@pytest.mark.asyncio
async def test_all_provider_keys_removed_from_shell_environment(private, tmp_path):
    settings = select(Settings(), 'poolside')
    runtime = Runtime(settings, tmp_path, lambda *args:None)
    runtime.rpc = AsyncMock(return_value={'exitCode':0})
    try:
        await runtime.command(['true'], str(tmp_path), 'test')
        scrubbed = runtime.rpc.call_args.args[1]['env']
        assert all(scrubbed[preset.key_env] is None for preset in PRESETS.values())
        assert scrubbed['TYPESAFE_API_KEY'] is None
    finally:
        await runtime.close()
