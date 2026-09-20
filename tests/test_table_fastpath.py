import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from kestrel_agent.table_fastpath import query_options, try_table
from kestrel_agent.tables import query


def test_schema_choices_and_bounds():
    questions, choices=query_options('Average fee by zone for ok records with duration >= 2.',
        [{'zone':'East','fee':4,'state':'ok','duration':3}])
    assert set(choices['fields'].values())=={'zone','fee','state','duration'}
    assert {'column':'duration','op':'gte','value':'2'} in choices['predicates'].values()
    assert all(p['value']!='not-in-request' for p in choices['predicates'].values())
    assert query_options('sum', [{f'field_{i}':i for i in range(17)}]) is None
    assert query_options('sum', [{}]) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome',['accepted','unsupported','rejected','changed'])
async def test_table_fastpath_checks_request_evidence_and_source(tmp_path,outcome):
    rows=[{'zone':'West','fee':'0.1','state':'ok'}, {'zone':'West','fee':'0.2','state':'ok'},
          {'zone':'West','fee':'90','state':'skip'}, {'zone':'West','fee':'invalid','state':'ok'}]
    path=tmp_path/'custom.json';path.write_text(json.dumps(rows))
    async def decide(state, questions):
        if 'supported' in questions:
            _, choices=query_options(state['request'],rows)
            column=lambda name: next(k for k,v in choices['fields'].items() if v==name)
            predicate=next(k for k,v in choices['predicates'].items() if v=={'column':'state','op':'eq','value':'ok'})
            return {k:{'choice':v} for k,v in {'supported':'no' if outcome=='unsupported' else 'yes',
                'operation':'sum','group':column('zone'),'value':column('fee'),
                'filter_0':predicate,'filter_1':'NONE','filter_2':'NONE'}.items()}
        assert state['query']['filters']==[{'column':'state','op':'eq','value':'ok'}]
        assert state['result']['invalid_numeric_rows_skipped']==1
        return {'sufficient':{'choice':'no' if outcome=='rejected' else 'yes'}}
    async def execute(tool,args):
        if tool=='query_table': return query(path,args)
        return {'sha256':'changed' if outcome=='changed' else 'original'}
    engine=SimpleNamespace(judge=SimpleNamespace(decide=AsyncMock(side_effect=decide)),
        tools=SimpleNamespace(execute=AsyncMock(side_effect=execute)),log=lambda *a:None,emit=lambda *a:None,
        store=SimpleNamespace(evidence=lambda *a:'evidence-id'),sid='test',state={})
    answer=await try_table(engine,'Sum fee by zone for state ok only. Return only numeric JSON.',
        {'path':str(path),'sha256':'original'},rows)
    assert answer==('{"West":0.3}' if outcome=='accepted' else None)
    if outcome=='unsupported': engine.tools.execute.assert_not_awaited()
    if outcome=='accepted':
        assert engine.state['observations'][-1]['tool']=='query_table'
        assert engine.judge.decide.await_count==2
    else: assert not engine.state.get('observations')
