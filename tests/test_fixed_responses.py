import json
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from kestrel_agent.config import Settings
from kestrel_agent.engine import Engine
from kestrel_agent.schema import Action, Plan
from kestrel_agent.store import Store


def plan(text='CONFIRMED', checks=None):
    return Plan(mode='plan', message='Read source', actions=[Action(id='read',tool='read_file',arguments_json='{"path":"note.txt"}',depends_on=[],purpose='Inspect source',condition='always')],success_criteria=[],final_response_text=text,completion_checks=checks or [])


@pytest.mark.parametrize('change', [
    {'mode':'answer','actions':[]}, {'final_response_ref':'${read.raw_text}'},
    {'final_response_text':' '}, {'final_response_text':'x'*1001},
])
def test_fixed_response_contract_is_bounded_and_unambiguous(change):
    value=plan().model_dump()
    value.update(change)
    with pytest.raises(ValidationError):
        Plan.model_validate(value)


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['success','unicode','unsupported','incomplete','failed-check','missing-source'])
@pytest.mark.parametrize('mode', ['standard','jev'])
async def test_fixed_response_requires_real_outcome_and_semantic_review(tmp_path, monkeypatch, case, mode):
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'private'))
    workspace=tmp_path/'workspace'
    workspace.mkdir()
    if case != 'missing-source':
        (workspace/'note.txt').write_text('observed evidence')
    settings=Settings(agent_mode=mode,shell=False,network=False)
    store=Store(settings)
    engine=Engine(settings,workspace,store,store.create(workspace),lambda *args:None,AsyncMock())
    text='All set ✓\n' if case=='unicode' else 'CONFIRMED'
    checks=[{'id':'exact','requirement':'Required evidence','kind':'result_equals','source':'${read.raw_text}','expected_json':'"different"'}] if case=='failed-check' else []
    initial=plan(text,checks)
    engine.state.update(request=f'Read note.txt and then reply exactly {text}',steps=0,plan=None)
    engine.make_plan=AsyncMock(side_effect=[initial,Plan(mode='clarify',message='Unfinished work requires attention.',actions=[],success_criteria=[])])
    verdict={'original_task':{'choice':'not_met' if case=='incomplete' else 'met'},
             'reuse_response':{'choice':'generate' if case=='unsupported' else 'supported'}}
    if case=='missing-source':
        verdict['recovery_read']={'choice':'not_met'}
    gate = [{'read':{'choice':'execute'}}] if mode == 'jev' else []
    engine.judge.decide=AsyncMock(side_effect=gate + [verdict,{'support':{'choice':'supported'}}])
    engine.runtime.complete=AsyncMock(return_value='Reviewed fallback')
    try:
        answer=await engine._loop()
        if case in {'success','unicode'}:
            assert answer==text
            engine.runtime.complete.assert_not_called()
            assert engine.state['statuses']['read']=='completed'
        elif case=='unsupported':
            assert answer=='Reviewed fallback'
            engine.runtime.complete.assert_awaited_once()
            assert engine.judge.decide.await_count==2 + len(gate)
        else:
            assert answer=='Unfinished work requires attention.'
            assert engine.make_plan.await_count==2
            engine.runtime.complete.assert_not_called()
        context, questions=engine.judge.decide.call_args_list[len(gate)].args
        assert context['candidate_response']==text
        assert 'USER explicitly requested' in questions['reuse_response']['instructions']
        assert 'original_task' in questions
    finally:
        await engine.close()
        store.close()
