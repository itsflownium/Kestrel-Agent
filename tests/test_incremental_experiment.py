import json
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from kestrel_agent.config import Settings
from kestrel_agent.engine import Engine
from kestrel_agent.schema import Action, Plan, SingleActionPlan, strict_schema
from kestrel_agent.store import Store


def action(name, tool, arguments):
    return Action(id=name,tool=tool,arguments_json=json.dumps(arguments),depends_on=[],purpose='Complete the requested file task',condition='always')


def step(item, checks=None):
    return Plan(mode='plan',message='Next action',actions=[item],success_criteria=[],completion_checks=checks or [])


def answer(text='DONE'):
    return Plan(mode='answer',message=text,actions=[],success_criteria=[])


def make_engine(tmp_path,monkeypatch,**options):
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    workspace=tmp_path/'workspace';workspace.mkdir()
    settings=Settings(agent_mode='standard',network=False,shell=False,**options)
    store=Store(settings)
    engine=Engine(settings,workspace,store,store.create(workspace),lambda *_:None,AsyncMock(return_value=False))
    engine._incremental_experiment=True
    engine.state.update(request='Write DONE to result.txt, verify it and reply DONE.',steps=0,plan=None)
    return engine,store


def test_single_action_schema_and_default_policy():
    value=step(action('first','read_file',{'path':'a'})).model_dump()
    value['actions'].append(action('second','read_file',{'path':'b'}).model_dump())
    assert len(Plan.model_validate(value).actions)==2
    with pytest.raises(ValidationError): SingleActionPlan.model_validate(value)
    assert strict_schema(SingleActionPlan)['properties']['actions']['maxItems']==1
    assert Engine._incremental_experiment is False


@pytest.mark.asyncio
async def test_incremental_actions_use_real_tools_and_final_review(tmp_path,monkeypatch):
    engine,store=make_engine(tmp_path,monkeypatch)
    engine.make_plan=AsyncMock(side_effect=[step(action('write','write_file',{'path':'result.txt','content':'DONE'})),
        step(action('read','read_file',{'path':'result.txt'})),answer()])
    engine.judge.decide=AsyncMock(return_value={'original_task':{'choice':'met'},'answer_support':{'choice':'supported'}})
    try:
        assert await engine._loop()=='DONE'
        assert (engine.workspace/'result.txt').read_text()=='DONE'
        assert engine.make_plan.await_count==3
        engine.judge.decide.assert_awaited_once()
        assert len(engine.state['completed_effects'])==1
        assert len(engine.state['observations'])==2
        assert 'original_task' in engine.judge.decide.call_args.args[1]
    finally:
        await engine.close();store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('reject',['original_task','answer_support'])
async def test_incomplete_or_unsupported_final_answer_cannot_exit(tmp_path,monkeypatch,reject):
    engine,store=make_engine(tmp_path,monkeypatch)
    (engine.workspace/'source.txt').write_text('Unfinished task')
    engine.make_plan=AsyncMock(side_effect=[step(action('read','read_file',{'path':'source.txt'})),answer(),
        step(action('write','write_file',{'path':'result.txt','content':'DONE'})),answer()])
    bad={'original_task':{'choice':'met'},'answer_support':{'choice':'supported'}}
    bad[reject]={'choice':'not_met' if reject=='original_task' else 'unsupported'}
    engine.judge.decide=AsyncMock(side_effect=[bad,{'original_task':{'choice':'met'},'answer_support':{'choice':'supported'}}])
    try:
        assert await engine._loop()=='DONE'
        assert engine.make_plan.await_count==4
        assert (engine.workspace/'result.txt').read_text()=='DONE'
    finally:
        await engine.close();store.close()


@pytest.mark.asyncio
async def test_exact_contract_failure_blocks_answer_before_semantic_review(tmp_path,monkeypatch):
    engine,store=make_engine(tmp_path,monkeypatch)
    engine.make_plan=AsyncMock(side_effect=[step(action('write','write_file',{'path':'result.txt','content':'WRONG'}),[
        {'id':'output','requirement':'Write DONE','kind':'file_text_equals','source':'result.txt','expected_json':'"DONE"'}]),
        answer(),Plan(mode='clarify',message='Repair is still needed.',actions=[],success_criteria=[])])
    engine.judge.decide=AsyncMock(side_effect=AssertionError('Exact check must block the answer'))
    try:
        assert await engine._loop()=='Repair is still needed.'
        assert engine.state['awaiting_input']
        assert engine.state['completion_checks']['output']['passed'] is False
        engine.judge.decide.assert_not_awaited()
    finally:
        await engine.close();store.close()


@pytest.mark.asyncio
async def test_saved_multi_action_plan_is_rejected_before_effects(tmp_path,monkeypatch):
    engine,store=make_engine(tmp_path,monkeypatch)
    plan=step(action('one','write_file',{'path':'a','content':'one'}))
    value=plan.model_dump();value['actions'].append(action('two','write_file',{'path':'b','content':'two'}).model_dump())
    engine.state['plan']=value
    try:
        with pytest.raises(ValueError,match='one action'): await engine._loop()
        assert not list(engine.workspace.iterdir())
    finally:
        await engine.close();store.close()


@pytest.mark.asyncio
async def test_no_progress_and_permissions_remain_enforced(tmp_path,monkeypatch):
    engine,store=make_engine(tmp_path,monkeypatch,permission='read-only',max_no_progress_rounds=2)
    engine.make_plan=AsyncMock(return_value=step(action('write','write_file',{'path':'result.txt','content':'DONE'})))
    engine.judge.decide=AsyncMock(side_effect=AssertionError('No automatic final acceptance'))
    try:
        with pytest.raises(RuntimeError,match='No new successful evidence'): await engine._loop()
        assert not (engine.workspace/'result.txt').exists()
        assert engine.state['statuses']['write']=='error'
    finally:
        await engine.close();store.close()


@pytest.mark.asyncio
async def test_model_receives_single_action_schema_and_correction(tmp_path,monkeypatch):
    engine,store=make_engine(tmp_path,monkeypatch)
    engine.mcp_tools=[]
    invalid=step(action('a','read_file',{'path':'a'})).model_dump()
    invalid['actions'].append(action('b','read_file',{'path':'b'}).model_dump())
    engine.runtime.complete=AsyncMock(side_effect=[json.dumps(invalid),answer().model_dump_json()])
    try:
        assert (await engine.make_plan()).mode=='answer'
        assert engine.runtime.complete.await_count==2
        for call in engine.runtime.complete.call_args_list:
            assert call.kwargs['schema']['properties']['actions']['maxItems']==1
            assert 'CONTROLLER EXPERIMENT' in call.args[0]
        assert 'validation' in engine.runtime.complete.call_args.args[0]
    finally:
        await engine.close();store.close()
