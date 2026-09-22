import copy
import json
from unittest.mock import AsyncMock

import pytest

from kestrel_agent.evidence import context


def observation(action, tool='read_file', result=None, arguments=None, status='completed'):
    return {'action':action,'tool':tool,'status':status,'evidence_id':'result-'+action,
            'invocation_evidence_id':'invocation-'+action,'arguments':arguments or {},
            'result':result if result is not None else {'content':'old result '*150}}


def page(action, source, content, offset=0, total=None):
    total = total if total is not None else offset+len(content)
    return observation(action,'read_evidence',
        {'content':content,'offset':offset,'total_chars':total,
         'next_offset':offset+len(content) if offset+len(content)<total else None,
         'truncated':offset>0 or offset+len(content)<total}, {'id':source,'offset':offset})


def test_requested_pages_are_visible_without_mutating_historical_receipts():
    originals=[observation('old-'+str(i)) for i in range(11)]
    lengths=[4600,1900,1300,1800,3500]
    requested=[page('requested-'+str(i),'source-'+str(i),chr(65+i)*size) for i,size in enumerate(lengths)]
    state={'observations':originals+requested}
    before=copy.deepcopy(state)
    view=context(state,24000)
    for item,wanted in zip(view['observations'][-5:],requested):
        assert item['retrieved_page']['content']==wanted['result']['content']
        assert item['retrieved_page']['source_evidence_id']==wanted['arguments']['id']
        assert not item['retrieved_page']['context_truncated']
        assert item['result_truncated'] is False
    assert state==before
    assert sum(len(item.get('retrieved_page',{}).get('content','')) for item in view['observations'])<=15600


def test_large_page_exposes_source_offset_not_double_serialized_excerpt_offset():
    text='東京 "line"\n'*2000
    state={'observations':[page('requested','source',text,offset=500,total=50000)]}
    view=context(state,4000)['observations'][0]
    focused=view['retrieved_page']
    assert focused['content'] and text.startswith(focused['content'])
    assert len(json.dumps(focused['content'])) - 2 <= 2600
    assert focused['offset']==500
    assert focused['end_offset']==focused['next_offset']==500+len(focused['content'])
    assert len(json.dumps(context(state,4000))) <= 8000
    assert focused['context_truncated'] and view['result_truncated']
    assert focused['source_metadata']['next_offset']==500+len(text)
    assert view['result_representation']=='retrieved_page_and_metadata'


def test_latest_pages_take_precedence_and_duplicate_reads_do_not_consume_budget():
    old=page('old','one','A'*2400)
    duplicate=page('duplicate','one','A'*2400)
    new=page('new','two','B'*2000)
    view=context({'observations':[old,duplicate,new]},4000)['observations']
    assert 'retrieved_page' not in view[0]
    assert view[1]['retrieved_page']['content']=='A'*600
    assert view[1]['retrieved_page']['next_offset']==600
    assert view[2]['retrieved_page']['content']=='B'*2000


def test_retrieval_does_not_relabel_failed_effect_as_successful():
    failed=observation('write','write_file',{'error':'permission denied'},status='error')
    read=page('read','invocation-write',json.dumps({'status':'error','executor_called':False}))
    view=context({'observations':[failed,read]},4000)
    assert view['observations'][0]['status']=='error'
    assert json.loads(view['observations'][1]['retrieved_page']['content'])['status']=='error'
    assert 'does not prove an effect occurred' in view['evidence_note']


@pytest.mark.asyncio
async def test_context_continuation_reconstructs_actual_store_evidence(tmp_path,monkeypatch):
    from kestrel_agent.config import Settings
    from kestrel_agent.engine import Engine
    from kestrel_agent.store import Store
    from kestrel_agent.schema import Action
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    settings=Settings(max_context_chars=4000)
    store=Store(settings)
    engine=Engine(settings,tmp_path,store,store.create(tmp_path),lambda *args:None,AsyncMock())
    engine.state.update(results={},statuses={})
    data={'content':'東京\\"\n'*1800,'important_final_fact':'preserved'}
    eid=store.evidence(engine.sid,data)
    collected=[];offset=0
    try:
        for index in range(20):
            await engine.perform(Action(id='page_'+str(index),tool='read_evidence',
                arguments_json=json.dumps({'id':eid,'offset':offset,'max_chars':20000}),
                depends_on=[],purpose='Read omitted evidence',condition='always'))
            focused=engine.context()['observations'][-1]['retrieved_page']
            assert focused['source_evidence_id']==eid and focused['offset']==offset
            collected.append(focused['content'])
            next_offset=focused['next_offset']
            if next_offset is None:break
            assert next_offset>offset
            offset=next_offset
        else:pytest.fail('Evidence pagination did not terminate')
        assert json.loads(''.join(collected))==data
        assert store.read_evidence(engine.sid,eid)==data
    finally:
        await engine.close();store.close()


def test_short_requested_page_returns_unused_capacity_to_other_observations():
    state={'observations':[observation('old-'+str(i)) for i in range(15)] + [page('short','source','small fact')]}
    view=context(state,24000)['observations']
    assert len(view[0]['result_excerpt'])+len(view[0]['result_tail_excerpt']) > 1000
    cost=sum(len(item['arguments_excerpt'])+len(item['result_excerpt'])+len(item['result_tail_excerpt']) for item in view)
    cost+=sum(len(json.dumps(item['retrieved_page']['content']))-2 for item in view if 'retrieved_page' in item)
    assert cost <= 18000
