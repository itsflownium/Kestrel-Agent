import asyncio
import json
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest

from kestrel_agent.config import Settings
from kestrel_agent.engine import Engine
from kestrel_agent.fastpath import try_fastpath
from kestrel_agent.prefetch import prefetch
from kestrel_agent.providers import Runtime
from kestrel_agent.schema import Plan
from kestrel_agent.store import Store
from kestrel_agent.telemetry import UsageLedger


def test_usage_snapshots_do_not_double_count_or_regress():
    ledger = UsageLedger()
    def snapshot(total):
        return NS(input_tokens=total,output_tokens=total//10,cached_input_tokens=total//2,
                  cache_write_input_tokens=None,reasoning_output_tokens=0)
    for value in [100,100,80,180]:ledger.observe('thread-a',snapshot(value))
    ledger.observe('thread-b',snapshot(20))
    assert ledger.totals['input_tokens'] == 200
    assert ledger.totals['cached_input_tokens'] == 100
    assert ledger.totals['output_tokens'] == 20


class FakeThread:
    def __init__(self, name):
        self.id=name; self.calls=0
    async def turn(self, prompt, **kwargs):
        self.calls+=1
        total=NS(input_tokens=100*self.calls,output_tokens=10*self.calls,cached_input_tokens=20*self.calls,cache_write_input_tokens=0,reasoning_output_tokens=2*self.calls)
        usage=NS(thread_id=self.id,turn_id=str(self.calls),token_usage=NS(total=total))
        async def events():
            yield NS(method='thread/tokenUsage/updated',payload=usage)
            yield NS(method='thread/tokenUsage/updated',payload=usage)
            yield NS(method='item/completed',payload=NS(item=NS(type='agentMessage',text='answer',phase='final_answer')))
            yield NS(method='turn/completed',payload=NS(turn=NS(status='completed')))
        return NS(stream=events,interrupt=AsyncMock())


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,threads',[('fresh',2),('task',1)])
async def test_generation_sessions_and_deduplicated_usage(tmp_path, mode, threads):
    runtime=Runtime(Settings(generation_session=mode),tmp_path,lambda *args:None)
    runtime.start=AsyncMock()
    runtime.account=AsyncMock(return_value={'account':{'id':'dummy'}})
    runtime.rpc=AsyncMock(return_value={'config':{}})
    runtime.codex.thread_start=AsyncMock(side_effect=[FakeThread('one'),FakeThread('two')])
    try:
        assert await runtime.complete('first',schema={'type':'object'})=='answer'
        assert await runtime.complete('second',schema={'type':'object'})=='answer'
        assert runtime.codex.thread_start.await_count==threads
        assert runtime.account.await_count==1 and runtime.rpc.await_count==1
        assert runtime.input_tokens==200 and runtime.output_tokens==20
        records=[r for r in runtime.telemetry.records if r['stage']=='generation']
        assert [r['usage']['input_tokens'] for r in records]==[100,100]
        assert all('prompt' not in r for r in records)
    finally:await runtime.close()


@pytest.mark.asyncio
async def test_model_and_task_change_invalidate_session(tmp_path):
    runtime=Runtime(Settings(generation_session='task'),tmp_path,lambda *args:None)
    runtime.start=AsyncMock();runtime.account=AsyncMock(return_value={'account':{'id':'dummy'}})
    runtime.rpc=AsyncMock(return_value={'config':{}})
    runtime.codex.thread_start=AsyncMock(side_effect=[FakeThread('one'),FakeThread('two'),FakeThread('three')])
    try:
        await runtime.complete('a')
        runtime.settings.model='different-model'
        await runtime.complete('b')
        runtime.begin_task()
        await runtime.complete('c')
        assert runtime.codex.thread_start.await_count==3
        assert runtime.account.await_count==3
    finally:await runtime.close()


@pytest.mark.asyncio
async def test_no_classifier_when_no_executable_route():
    engine=NS(judge=NS(decide=AsyncMock(side_effect=AssertionError('Redundant question'))))
    assert await try_fastpath(engine,'Explain how iterators work.') is None
    engine.judge.decide.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('changed',[False,True])
async def test_initial_evidence_reuse_requires_matching_hash(tmp_path,monkeypatch,changed):
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    path=tmp_path/'data.json';path.write_text('[{"value":1}]')
    settings=Settings();store=Store(settings)
    engine=Engine(settings,tmp_path,store,store.create(tmp_path),lambda *a:None,AsyncMock())
    engine.state.update(steps=0,observations=[])
    engine.judge.decide=AsyncMock(return_value={'route':{'choice':'model'}})
    original=engine.tools.execute;engine.tools.execute=AsyncMock(side_effect=original)
    try:
        await try_fastpath(engine,'Read data.json and explain its contents.')
        if changed:path.write_text('[{"value":2}]')
        await prefetch(engine,'Read data.json and explain its contents.')
        assert engine.tools.execute.await_count==(2 if changed else 1)
        assert engine.state['observations'][0]['result']['data'][0]['value']==(2 if changed else 1)
    finally:await engine.close();store.close()


@pytest.mark.asyncio
async def test_direct_answer_review_rejects_unobserved_work(tmp_path,monkeypatch):
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    settings=Settings();store=Store(settings)
    engine=Engine(settings,tmp_path,store,store.create(tmp_path),lambda *a:None,AsyncMock())
    engine.state.update(request='Create a file.',steps=0,plan=None)
    engine.make_plan=AsyncMock(side_effect=[Plan(mode='answer',message='File created.',actions=[],success_criteria=[]),Plan(mode='clarify',message='Which path?',actions=[],success_criteria=[])])
    engine.judge.decide=AsyncMock(return_value={'direct_answer':{'choice':'revise'}})
    try:
        assert await engine._loop()=='Which path?'
        engine.judge.decide.assert_awaited_once()
    finally:await engine.close();store.close()


@pytest.mark.asyncio
async def test_cancellation_clears_reusable_session(tmp_path):
    runtime=Runtime(Settings(generation_session='task'),tmp_path,lambda *args:None)
    runtime.start=AsyncMock();runtime.account=AsyncMock(return_value={'account':{'id':'dummy'}})
    runtime.rpc=AsyncMock(return_value={'config':{}})
    interrupt=AsyncMock()
    async def events():
        raise asyncio.CancelledError()
        yield
    thread=NS(turn=AsyncMock(return_value=NS(stream=events,interrupt=interrupt)))
    runtime.codex.thread_start=AsyncMock(return_value=thread)
    try:
        with pytest.raises(asyncio.CancelledError):await runtime.complete('request')
        assert runtime._generation_thread is None
        assert runtime.active_turn is None
        interrupt.assert_awaited_once()
    finally:await runtime.close()


def test_telemetry_records_failure_without_exception_content():
    from kestrel_agent.telemetry import Telemetry
    telemetry=Telemetry()
    with pytest.raises(RuntimeError):
        with telemetry.measure('test'):
            raise RuntimeError('private prompt or secret')
    assert telemetry.records[0]['error_type']=='RuntimeError'
    assert 'private' not in json.dumps(telemetry.records)


@pytest.mark.asyncio
async def test_schema_change_and_failed_turn_start_invalidate_thread(tmp_path):
    runtime=Runtime(Settings(generation_session='task'),tmp_path,lambda *args:None)
    runtime.start=AsyncMock();runtime.account=AsyncMock(return_value={'account':{'id':'dummy'}})
    runtime.rpc=AsyncMock(return_value={'config':{}})
    first, second, third = FakeThread('one'), FakeThread('two'), FakeThread('three')
    runtime.codex.thread_start=AsyncMock(side_effect=[first, second, third])
    try:
        await runtime.complete('structured',schema={'type':'object'})
        await runtime.complete('plain text')
        assert runtime.codex.thread_start.await_count == 2
        second.turn=AsyncMock(side_effect=RuntimeError('turn startup failed'))
        with pytest.raises(RuntimeError,match='startup failed'):
            await runtime.complete('same schema')
        assert runtime._generation_thread is None and runtime._setup is None
        await runtime.complete('retry')
        assert runtime.codex.thread_start.await_count == 3
    finally:await runtime.close()


@pytest.mark.asyncio
async def test_compact_profile_keeps_sandbox_and_tool_controls(tmp_path):
    from openai_codex import ApprovalMode, Sandbox
    from kestrel_agent.providers import COMPACT_GENERATION_INSTRUCTIONS
    runtime=Runtime(Settings(generation_prompt_profile='compact'),tmp_path,lambda *args:None)
    runtime.start=AsyncMock();runtime.account=AsyncMock(return_value={'account':{'id':'dummy'}})
    runtime.rpc=AsyncMock(return_value={'config':{'mcp_servers':{'connected':{}}}})
    runtime.codex.thread_start=AsyncMock(return_value=FakeThread('one'))
    try:
        await runtime.complete('answer the task')
        options=runtime.codex.thread_start.call_args.kwargs
        assert options['base_instructions'] == COMPACT_GENERATION_INSTRUCTIONS
        assert options['sandbox'] == Sandbox.read_only
        assert options['approval_mode'] == ApprovalMode.deny_all
        for key in ['features.shell_tool','features.unified_exec','features.code_mode','apps._default.enabled','mcp_servers.connected.enabled']:
            assert options['config'][key] is False
        assert options['config']['web_search'] == 'disabled'
        assert 'host controller owns all actions' in options['developer_instructions']
    finally:await runtime.close()
