from unittest.mock import AsyncMock

import pytest

from kestrel_agent.config import Settings
from kestrel_agent.engine import Engine
from kestrel_agent.prefetch import prefetch
from kestrel_agent.schema import Plan
from kestrel_agent.store import Store


def make_engine(tmp_path,monkeypatch,**kwargs):
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    settings=Settings(**kwargs);store=Store(settings)
    engine=Engine(settings,tmp_path,store,store.create(tmp_path),lambda *a:None,AsyncMock(return_value=True))
    engine.state.update(steps=0,observations=[])
    return engine,store


@pytest.mark.asyncio
async def test_initial_evidence_includes_source_hash_and_absent_destination(tmp_path,monkeypatch):
    (tmp_path/'source.md').write_text('The required value is in this source.')
    engine,store=make_engine(tmp_path,monkeypatch)
    try:
        await prefetch(engine,'Read source.md and write answer.json.')
        observations=engine.state['observations']
        assert len(observations)==2
        assert observations[0]['tool']=='read_file'
        assert observations[0]['result']['sha256']
        assert observations[1]['result']['exists'] is False
        assert not (tmp_path/'answer.json').exists()
    finally: await engine.close();store.close()


@pytest.mark.asyncio
async def test_prefetch_respects_size_permissions_and_order(tmp_path,monkeypatch):
    (tmp_path/'big.txt').write_text('x'*12001)
    (tmp_path/'script.py').write_text('raise Exception()')
    engine,store=make_engine(tmp_path,monkeypatch)
    try:
        await prefetch(engine,'Run script.py, then inspect big.txt and ../outside.txt.')
        assert engine.state['observations']==[]
    finally: await engine.close();store.close()


@pytest.mark.asyncio
async def test_prefetch_respects_step_budget(tmp_path,monkeypatch):
    engine,store=make_engine(tmp_path,monkeypatch,max_steps=1)
    try:
        await prefetch(engine,'Read first.txt and second.txt.')
        assert len(engine.state['observations'])==0
        assert engine.state['steps']==0
    finally: await engine.close();store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('supported',[True,False])
async def test_answer_after_prefetch_requires_support_and_format(tmp_path,monkeypatch,supported):
    engine,store=make_engine(tmp_path,monkeypatch)
    engine.state.update(request='Return only the supported value.',steps=1,plan=None)
    engine.make_plan=AsyncMock(side_effect=[
        Plan(mode='answer',message='candidate',actions=[],success_criteria=[]),
        Plan(mode='clarify',message='Need more evidence.',actions=[],success_criteria=[])])
    engine.judge.decide=AsyncMock(return_value={'original_task':{'choice':'met'},
        'answer_support':{'choice':'supported' if supported else 'unsupported'}})
    try:
        assert await engine._loop()==('candidate' if supported else 'Need more evidence.')
        assert engine.make_plan.await_count==(1 if supported else 2)
    finally: await engine.close();store.close()
