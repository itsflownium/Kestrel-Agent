import json
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from kestrel_agent.config import Settings
from kestrel_agent.engine import Engine
from kestrel_agent.schema import Action,Plan
from kestrel_agent.store import Store
from kestrel_agent.tables import query


def action(after='success',tool='read_file'):
    return Action(id='recover',tool=tool,arguments_json='{}',depends_on=['run'],purpose='Recover',condition='always',after=after)


@pytest.mark.parametrize(('after','status','outcome'),[
 ('success','error','blocked'),('failure','error','ready'),('failure','completed','skip'),
 ('failure','uncertain','blocked'),('completion','error','ready'),('completion','uncertain','ready'),('success','skip','skip')])
def test_failure_dependency_semantics(after,status,outcome):
    assert Engine.dependency_outcome(action(after),{'run':status})==outcome


def test_uncertain_outcome_cannot_trigger_effect():
    assert Engine.dependency_outcome(action('completion','shell'),{'run':'uncertain'})=='blocked'


def test_skipped_branch_does_not_hide_failed_dependency():
    dependent=action()
    dependent.depends_on=['run','other']
    assert Engine.dependency_outcome(dependent,{'run':'skip','other':'error'})=='blocked'


def test_result_reference_must_be_declared():
    with pytest.raises(ValidationError):
        Plan(mode='answer',message='x',actions=[],success_criteria=[],final_response_ref='${invented.stdout}')


def test_decimal_json_output_is_numeric_and_exact(tmp_path):
    path=tmp_path/'data.csv';path.write_text('zone,fee\na,0.1\na,0.2\n')
    result=query(path,{'operation':'sum','group_by':'zone','value_column':'fee'})
    assert result['json_content']=='{"a":0.3}'
    assert json.loads(result['json_content'])=={'a':0.3}


@pytest.mark.asyncio
@pytest.mark.parametrize('approved',[True,False])
async def test_result_reuse_requires_jev_and_completed_task(tmp_path,monkeypatch,approved):
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    store=Store(Settings())
    engine=Engine(Settings(),tmp_path,store,store.create(tmp_path),lambda *a:None,AsyncMock(return_value=True))
    engine.state.update(request='Return only JSON totals.',steps=0,plan=None,observations=[])
    plan=Plan.model_validate({'mode':'plan','message':'Compute','actions':[{'id':'compute','tool':'query_table','arguments_json':'{}','depends_on':[],'purpose':'Compute','condition':'always'}],'success_criteria':[],'final_response_ref':'${compute.json_content}'})
    engine.make_plan=AsyncMock(return_value=plan)
    async def perform(a):
        engine.state['steps']+=1
        engine.state['statuses'][a.id]='completed'
        engine.state['results'][a.id]={'json_content':'{"A":3}'}
    engine.perform=perform
    engine.runtime.complete=AsyncMock(return_value='generated answer')
    engine.judge.decide=AsyncMock(side_effect=[{'compute':{'choice':'execute'}},
        {'original_task':{'choice':'met'},'reuse_response':{'choice':'supported' if approved else 'generate'}},
        {'support':{'choice':'supported'}}])
    try:
        assert await engine._loop()==('{"A":3}' if approved else 'generated answer')
        assert engine.runtime.complete.await_count==(0 if approved else 1)
    finally:
        await engine.close();store.close()


@pytest.mark.asyncio
async def test_recovered_error_does_not_force_new_plan(tmp_path,monkeypatch):
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    store=Store(Settings())
    engine=Engine(Settings(),tmp_path,store,store.create(tmp_path),lambda *a:None,AsyncMock(return_value=True))
    engine.state.update(request='Run and recover if needed.',steps=0,plan=None,observations=[])
    plan=Plan.model_validate({'mode':'plan','message':'Run then recover','actions':[
        {'id':'run','tool':'shell','arguments_json':'{}','depends_on':[],'purpose':'Run','condition':'always'},
        {'id':'retry','tool':'shell','arguments_json':'{}','depends_on':['run'],'after':'failure','purpose':'Recover','condition':'always'}
    ],'success_criteria':[],'final_response_ref':'${retry.stdout}'})
    engine.make_plan=AsyncMock(return_value=plan)
    async def perform(a):
        engine.state['steps']+=1
        engine.state['statuses'][a.id]='error' if a.id=='run' else 'completed'
        engine.state['results'][a.id]={'stdout':'done'}
    engine.perform=perform
    engine.runtime.complete=AsyncMock(side_effect=AssertionError('Unnecessary generation'))
    engine.judge.decide=AsyncMock(side_effect=[{'run':{'choice':'execute'}},{'retry':{'choice':'execute'}},
        {'original_task':{'choice':'met'},'recovery_run':{'choice':'met'},'reuse_response':{'choice':'supported'}}])
    try:
        assert await engine._loop()=='done'
        assert engine.make_plan.await_count==1
        assert engine.state['statuses']['run']=='error'
    finally:
        await engine.close();store.close()


@pytest.mark.asyncio
async def test_reuse_cannot_bypass_unfinished_original_task(tmp_path,monkeypatch):
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    store=Store(Settings())
    engine=Engine(Settings(),tmp_path,store,store.create(tmp_path),lambda *a:None,AsyncMock(return_value=True))
    engine.state.update(request='Read a source and do another required action.',steps=0,plan=None,observations=[])
    plan=Plan.model_validate({'mode':'plan','message':'Read','actions':[{'id':'read','tool':'read_file','arguments_json':'{}','depends_on':[],'purpose':'Read','condition':'always'}],'success_criteria':[],'final_response_ref':'${read.content}'})
    engine.make_plan=AsyncMock(side_effect=[plan,Plan(mode='clarify',message='Need the missing required input.',actions=[],success_criteria=[])])
    async def perform(a):
        engine.state['steps']+=1
        engine.state['statuses'][a.id]='completed'
        engine.state['results'][a.id]={'content':'partial output'}
    engine.perform=perform
    engine.judge.decide=AsyncMock(side_effect=[{'read':{'choice':'execute'}},
        {'original_task':{'choice':'not_met'},'reuse_response':{'choice':'supported'}}])
    try:
        assert await engine._loop()=='Need the missing required input.'
        assert engine.make_plan.await_count==2
    finally:
        await engine.close();store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',[False,True])
async def test_execution_evidence_keeps_provenance(tmp_path,monkeypatch,failure):
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    store=Store(Settings())
    engine=Engine(Settings(),tmp_path,store,store.create(tmp_path),lambda *a:None,AsyncMock(return_value=True))
    engine.state.update(steps=0,statuses={},results={},observations=[])
    engine.tools.execute=AsyncMock(side_effect=TimeoutError('transport lost') if failure else None,return_value={'stdout':'ok'})
    command=Action(id='run',tool='shell',arguments_json='{"command":["example"]}',depends_on=[],purpose='Run',condition='always')
    try:
        await engine.perform(command)
        evidence=engine.context()['observations'][0]
        assert evidence['tool']=='shell'
        assert json.loads(evidence['arguments_excerpt'])=={'command':['example']}
        assert evidence['status']==('uncertain' if failure else 'completed')
        assert bool(engine.state['uncertain_effects'])==failure
    finally:
        await engine.close();store.close()
