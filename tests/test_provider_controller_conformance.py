"""Real HTTP/controller conformance with scripted providers, not model-quality tests."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from unittest.mock import AsyncMock

import pytest

from kestrel_agent.config import Settings
from kestrel_agent.engine import Engine
from kestrel_agent.store import Store


@contextmanager
def provider_fixture(protocol, scenario, expected):
    calls, errors = [], []
    plan_count = 0
    def action(name, tool, arguments, dependencies=()):
        return dict(id=name, tool=tool, arguments_json=json.dumps(arguments),
                    depends_on=list(dependencies), purpose='Complete the requested file transformation', condition='always')
    plan = dict(mode='plan', message='Transform and save the requested source.', actions=[
        action('source', 'read_file', {'path': 'source.txt'}),
        action('transform', 'generate', {'prompt': 'Transform only this source to uppercase:\n${source.raw_text}'}, ['source']),
        action('save', 'write_file', {'path': 'result.txt', 'content': '${transform.content}'}, ['transform']),
    ], success_criteria=['result.txt contains exactly the requested uppercase text.'], final_response_text='SAVED',
        completion_checks=[dict(id='exact_output', requirement='Exact requested output', kind='file_text_equals',
                                source='result.txt', expected_json=json.dumps(expected))])

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            nonlocal plan_count
            try:
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert body['model'] == 'fixture-user-selected-model'
                assert 'tools' not in body  # Controller owns execution.
                if protocol == 'anthropic':
                    assert self.path == '/v1/messages'
                    assert self.headers['x-api-key'] == 'fixture-key'
                    assert self.headers['anthropic-version'] == '2023-06-01'
                else:
                    assert self.path == '/v1/chat/completions'
                    assert self.headers['authorization'] == 'Bearer fixture-key'
                prompt = body['messages'][-1]['content']
                if prompt.startswith('Select exactly'):
                    stage = 'decision'
                    questions = json.loads(prompt.split('\n', 1)[1])['questions']
                    # Deliberately overconfident judgments: exact checks and
                    # permissions must remain authoritative in negative controls.
                    answers = {}
                    for name, question in questions.items():
                        options = question['options']
                        choice = next(value for value in ('met', 'supported', 'execute', 'generate') if value in options)
                        answers[name] = {'choice': choice, 'reason': 'Scripted fixture verdict'}
                    text = json.dumps(answers)
                elif prompt.startswith('Transform only'):
                    stage = 'generation'
                    assert prompt.endswith('café 東京\nsecond line\n')
                    text = expected if scenario != 'wrong_output' else expected + 'UNREQUESTED\n'
                else:
                    stage = 'planning'
                    plan_count += 1
                    text = json.dumps(plan if plan_count == 1 else dict(mode='clarify',
                        message='The required output is not established; inspect the failed check.',
                        actions=[], success_criteria=[]))
                calls.append({'stage': stage, 'path': self.path})
                native = scenario == 'native_tool_request' and stage == 'planning'
                if protocol == 'anthropic':
                    response = {'content': ([{'type': 'tool_use', 'id': 'forbidden', 'name': 'write_file', 'input': {}}]
                                if native else [{'type': 'text', 'text': text}]),
                                'stop_reason': 'tool_use' if native else 'end_turn',
                                'usage': {'input_tokens': 11, 'output_tokens': 3}}
                else:
                    response = {'choices': [{'finish_reason': 'tool_calls' if native else 'stop',
                        'message': {'content': text, **({'tool_calls': [{'id': 'forbidden'}]} if native else {})}}],
                        'usage': {'prompt_tokens': 11, 'completion_tokens': 3}}
                encoded = json.dumps(response).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            except Exception as error:
                errors.append(repr(error))
                self.send_error(500)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1', calls, errors
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', ['openai-compatible', 'anthropic'])
@pytest.mark.parametrize('scenario', ['success', 'wrong_output', 'denied_write', 'native_tool_request'])
async def test_api_provider_controller_boundaries(tmp_path, monkeypatch, protocol, scenario):
    from kestrel_agent import providers
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'private'))
    monkeypatch.setenv('KESTREL_MODEL_API_KEY', 'fixture-key')
    monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
    monkeypatch.setattr(providers, 'AsyncTypeSafeClient', lambda **_: pytest.fail('Standard mode started Jev'))
    workspace = tmp_path/'workspace'
    workspace.mkdir()
    source = 'café 東京\nsecond line\n'
    expected = source.upper()
    (workspace/'source.txt').write_text(source)
    with provider_fixture(protocol, scenario, expected) as (url, calls, errors):
        settings = Settings(provider=protocol, provider_base_url=url, model='fixture-user-selected-model',
                            agent_mode='standard', network=False, shell=False, confirm_writes=True,
                            provider_json_mode='json_schema')
        store = Store(settings)
        confirm = AsyncMock(return_value=scenario != 'denied_write')
        engine = Engine(settings, workspace, store, store.create(workspace), lambda *_: None, confirm)
        engine.runtime.start = AsyncMock(side_effect=AssertionError('API-only task attempted to start Codex'))
        try:
            request = 'Read source.txt and save its uppercase form to result.txt, exactly ' + json.dumps(expected) + '. Reply exactly SAVED after verifying. Do not change source.txt.'
            if scenario == 'native_tool_request':
                with pytest.raises(RuntimeError, match='Provider did not finish'):
                    await engine.run(request)
                assert engine.state['status'] == 'error'
                assert not (workspace/'result.txt').exists()
                assert len(calls) == 1
            else:
                answer = await engine.run(request)
                check = engine.state['completion_checks']['exact_output']
                if scenario == 'success':
                    assert answer == 'SAVED'
                    assert (workspace/'result.txt').read_text() == expected
                    assert check['passed'] is True
                    assert engine.state['status'] == 'completed'
                    assert [call['stage'] for call in calls] == ['planning', 'generation', 'decision']
                    assert engine.state['usage']['generation_calls'] == 2
                    assert engine.state['usage']['decision_calls'] == 1
                    assert engine.state['usage']['generation_input_tokens'] == 22
                    assert engine.state['usage']['decision_input_tokens'] == 11
                else:
                    assert answer != 'SAVED'
                    assert check['passed'] is False
                    assert engine.state['status'] == 'needs_input'
                    if scenario == 'denied_write':
                        assert not (workspace/'result.txt').exists()
                    else:
                        assert (workspace/'result.txt').read_text() != expected
                confirm.assert_awaited_once()
                assert engine.state['usage']['jev_calls'] == 0
            engine.runtime.start.assert_not_called()
            assert not engine.runtime.started
            assert not errors
            assert (workspace/'source.txt').read_text() == source
            assert set(path.name for path in workspace.iterdir()) <= {'source.txt', 'result.txt'}
        finally:
            await engine.close()
            store.close()
