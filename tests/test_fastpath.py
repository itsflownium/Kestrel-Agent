import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from kestrel_agent.fastpath import arithmetic_answer, try_fastpath


@pytest.mark.parametrize(('prompt', 'expected'), [
    ('What is 17 times 23? Reply with only the number.', '391'),
    ('Calculate 12.5 times 8.', '100'),
    ('Compute -5 plus 3', '-2'),
    ('1 / 0', None),
    ('1 / 3', None),
    ('1 / 8', '0.125'),
    ('17 * 23 then delete the file', None),
    ('Explain 17 times 23', None),
    ('__import__("os")', None),
])
def test_arithmetic_is_bounded(prompt, expected):
    assert arithmetic_answer(prompt) == expected


@pytest.mark.asyncio
async def test_arithmetic_still_requires_jev_route():
    judge = SimpleNamespace(decide=AsyncMock(return_value={'route': {'choice': 'model'}}))
    engine = SimpleNamespace(judge=judge, log=lambda *args: None, emit=lambda *args: None)
    assert await try_fastpath(engine, '17 * 23') is None
    judge.decide.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_selection_verification_falls_back(tmp_path):
    path = tmp_path / 'data.json'
    path.write_text('[{"name":"A"}]')
    judge = SimpleNamespace(decide=AsyncMock(side_effect=[
        {'route': {'choice': 'selection'}, 'candidate': {'choice': 'item_0'}, 'format': {'choice': 'record'}},
        {'sufficient': {'choice': 'no'}},
    ]))
    tools = SimpleNamespace(path=lambda _: path, execute=AsyncMock(return_value={'data': [{'name': 'A'}]}))
    engine = SimpleNamespace(judge=judge, tools=tools, log=lambda *args: None, emit=lambda *args: None)
    assert await try_fastpath(engine, 'Choose a record from data.json') is None
    assert judge.decide.await_count == 2


@pytest.mark.asyncio
async def test_output_fields_come_from_input_schema(tmp_path):
    path = tmp_path / 'records.json'
    row = {'identifier_custom': 'Z-718', 'fee_annual_eur': 37}
    path.write_text(json.dumps([row]))
    async def decide(state, questions):
        if 'route' in questions:
            def key_for(question, value):
                return next(key for key, label in questions[question]['options'].items() if label == value)
            return {'route': {'choice': 'selection'}, 'candidate': {'choice': 'item_0'},
                    'format': {'choice': 'two_fields'},
                    'first_field': {'choice': key_for('first_field', 'identifier_custom')},
                    'second_field': {'choice': key_for('second_field', 'fee_annual_eur')}}
        return {'sufficient': {'choice': 'yes'}}
    engine = SimpleNamespace(
        judge=SimpleNamespace(decide=decide),
        tools=SimpleNamespace(path=lambda _: path, execute=AsyncMock(return_value={'data': [row], 'path': str(path)})),
        store=SimpleNamespace(evidence=lambda *args: 'evidence-id'), sid='test', state={},
        log=lambda *args: None, emit=lambda *args: None)
    result = await try_fastpath(engine, 'Select the cheapest record from records.json and return its identifier and annual fee.')
    assert result == 'identifier_custom: Z-718 · fee_annual_eur: 37'
    assert engine.state['observations'][0]['evidence_id'] == 'evidence-id'
