import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from kestrel_agent.config import Settings
from kestrel_agent.engine import Engine
from kestrel_agent.fastpath import try_fastpath
from kestrel_agent.schema import Plan
from kestrel_agent.store import Store
from kestrel_agent.tables import query


def test_table_query_decimal_and_invalid_values(tmp_path):
    path=tmp_path/'data.csv'
    path.write_text('area,cost,state\nA,0.10,ok\nA,0.20,ok\nB,3.50,ok\nA,900,skip\nB,NaN,ok\nB,1e999999,ok\n')
    result=query(path,{'operation':'sum','group_by':'area','value_column':'cost','filters':[{'column':'state','op':'eq','value':'ok'}]})
    assert result['results']=={'A':'0.30','B':'3.50'}
    assert result['invalid_numeric_rows_skipped']==2
    assert not result['rounded']


def test_table_operations_and_invalid_filters(tmp_path):
    path=tmp_path/'data.json'
    path.write_text(json.dumps([{'amount':2},{'amount':4},{'amount':6}]))
    for op,expected in [('count','3'),('mean','4'),('min','2'),('max','6')]:
        assert query(path,{'operation':op,'value_column':'amount'})['results']=={'all':expected}
    with pytest.raises(ValueError):
        query(path,{'operation':'sum','value_column':'amount','filters':[{'column':'missing','op':'eq','value':1}]})


@pytest.mark.asyncio
async def test_multiple_sources_never_offer_single_file_fastpath():
    async def decide(state,questions):
        assert 'selection' not in questions['route']['options']
        assert 'records' in state and state['records'] is None
        return {'route':{'choice':'model'}}
    engine=SimpleNamespace(judge=SimpleNamespace(decide=decide),log=lambda *a:None,emit=lambda *a:None)
    assert await try_fastpath(engine,'Use policy.md and releases.json to choose one release.') is None


@pytest.mark.asyncio
async def test_partial_diagnosis_cannot_finish_original_request(tmp_path,monkeypatch):
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    settings=Settings()
    store=Store(settings)
    engine=Engine(settings,tmp_path,store,store.create(tmp_path),lambda *a:None,AsyncMock(return_value=True))
    engine.state.update(request='Run the corrected command successfully.',steps=1,plan=None,observations=[])
    engine.make_plan=AsyncMock(side_effect=[Plan(mode='answer',message='I diagnosed it.',actions=[],success_criteria=[]),Plan(mode='clarify',message='Need the missing input file.',actions=[],success_criteria=[])])
    engine.judge.decide=AsyncMock(return_value={'original_task':{'choice':'not_met'}})
    try:
        assert await engine._loop()=='Need the missing input file.'
        assert engine.make_plan.await_count==2
    finally:
        await engine.close(); store.close()


@pytest.mark.asyncio
async def test_answer_format_is_checked_after_generation(tmp_path,monkeypatch):
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    store=Store(Settings())
    engine=Engine(Settings(),tmp_path,store,store.create(tmp_path),lambda *a:None,AsyncMock(return_value=True))
    engine.state.update(request='Read a file and reply only JSON.',steps=0,plan=None,observations=[])
    plan=Plan.model_validate({'mode':'plan','message':'Read source','actions':[{'id':'read','tool':'read_file','arguments_json':'{"path":"input.json"}','depends_on':[],'purpose':'Read source','condition':'always'}],'success_criteria':['Final response is only JSON.']})
    engine.make_plan=AsyncMock(return_value=plan)
    async def perform(action):
        engine.state['steps']+=1
        engine.state['statuses'][action.id]='completed'
    engine.perform=perform
    engine.runtime.complete=AsyncMock(return_value='{"ok":true}')
    engine.judge.decide=AsyncMock(side_effect=[
        {'read':{'choice':'execute'}},
        {'criterion_0':{'choice':'response_pending'},'original_task':{'choice':'met'}},
        {'support':{'choice':'supported'}},
    ])
    try:
        assert await engine._loop()=='{"ok":true}'
        assert engine.make_plan.await_count==1
        assert engine.runtime.complete.await_count==1
    finally:
        await engine.close();store.close()
