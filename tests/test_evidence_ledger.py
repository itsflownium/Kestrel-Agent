import json
from unittest.mock import AsyncMock

import pytest

from kestrel_agent.config import Settings
from kestrel_agent.engine import Engine
from kestrel_agent.store import Store


def setup(tmp_path, monkeypatch, **options):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path / 'state'))
    settings = Settings(**options)
    store = Store(settings)
    engine = Engine(settings, tmp_path, store, store.create(tmp_path), lambda *a: None, AsyncMock())
    engine.state.update(request='Find the original approval and final output.', steps=0, observations=[])
    return engine, store


def observe(engine, store, action, result):
    eid = store.evidence(engine.sid, result)
    engine.state['observations'].append({'action': action, 'evidence_id': eid,
        'tool': 'read_file', 'status': 'completed', 'arguments': {'path': action}, 'result': result})
    return eid


@pytest.mark.asyncio
async def test_old_evidence_remains_discoverable_and_retrievable(tmp_path, monkeypatch):
    engine, store = setup(tmp_path, monkeypatch)
    try:
        first = observe(engine, store, 'approval', {'content': 'approved by owner'})
        for i in range(20):
            observe(engine, store, f'noise_{i}', {'content': 'unrelated data'})
        context = engine.context()
        assert first in {row['evidence_id'] for row in context['evidence_index']}
        result = await engine.tools.execute('read_evidence', {'id': first})
        assert 'approved by owner' in result['content']
        assert result['truncated'] is False
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
async def test_excerpts_expose_omissions_and_can_retrieve_tail(tmp_path, monkeypatch):
    engine, store = setup(tmp_path, monkeypatch, max_context_chars=4000)
    try:
        eid = observe(engine, store, 'long', {'content': 'x' * 20000 + 'TAIL_MARKER'})
        view = engine.context()['observations'][0]
        assert view['result_truncated'] is True
        assert view['result_total_chars'] > len(view['result_excerpt'])
        result = await engine.tools.execute('read_evidence', {'id': eid, 'offset': 19950, 'max_chars': 1000})
        assert 'TAIL_MARKER' in result['content']
        assert result['next_offset'] is None
        assert result['truncated'] is True  # Earlier characters are omitted.
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
async def test_evidence_retrieval_cannot_cross_sessions(tmp_path, monkeypatch):
    engine, store = setup(tmp_path, monkeypatch)
    try:
        other = store.create(tmp_path)
        eid = store.evidence(other, {'private': 'other session'})
        with pytest.raises(ValueError, match='not available'):
            await engine.tools.execute('read_evidence', {'id': eid})
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
async def test_search_retains_tail_offsets_and_session_boundary(tmp_path, monkeypatch):
    engine, store = setup(tmp_path, monkeypatch)
    try:
        eid = observe(engine, store, 'old', {'content': 'x' * 19000 + 'RareTarget'})
        other = store.create(tmp_path)
        store.evidence(other, {'content': 'RareTarget private'})
        matches = await engine.tools.execute('search_evidence', {'query': 'RareTarget'})
        assert [r['evidence_id'] for r in matches['matches']] == [eid]
        row = matches['matches'][0]
        tail = await engine.tools.execute('read_evidence', {'id': eid, 'offset': row['offset']})
        assert 'RareTarget' in tail['content']
        listing = await engine.tools.execute('search_evidence', {'query': '', 'limit': 1})
        assert len(listing['matches']) == 1
    finally:
        await engine.close()
        store.close()


def test_requirements_survive_replans_without_resetting_verdicts():
    from kestrel_agent.evidence import register_requirements
    state = {}
    ledger = register_requirements(state, ['Write the report', 'Verify the total'])
    first = next(iter(ledger))
    ledger[first].update(status='met', reviewed_evidence=['receipt'])
    register_requirements(state, ['Verify the total', 'Recover the command'])
    assert len(ledger) == 3
    assert ledger[first]['status'] == 'met'
    assert ledger[first]['reviewed_evidence'] == ['receipt']


def test_identical_reads_and_new_action_ids_do_not_reset_progress_budget():
    from kestrel_agent.evidence import check_progress
    state = {'observations': []}
    check_progress(state, 2)
    state['observations'].append({'action': 'a', 'tool': 'read_file', 'status': 'completed', 'arguments': {'path': 'a'}, 'result': {'content': 'same'}})
    check_progress(state, 2)
    state['observations'].append({**state['observations'][0], 'action': 'new_id'})
    check_progress(state, 2)
    with pytest.raises(RuntimeError, match='No new successful evidence'):
        check_progress(state, 2)


@pytest.mark.asyncio
async def test_rejected_direct_answers_have_explicit_no_progress_limit(tmp_path, monkeypatch):
    from kestrel_agent.schema import Plan
    engine, store = setup(tmp_path, monkeypatch, max_no_progress_rounds=2)
    engine.make_plan = AsyncMock(return_value=Plan(mode='answer', message='Created it.', actions=[], success_criteria=[]))
    engine.judge.decide = AsyncMock(return_value={'direct_answer': {'choice': 'revise'}})
    try:
        with pytest.raises(RuntimeError, match='No new successful evidence'):
            await engine._loop()
        assert engine.make_plan.await_count == 2
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
async def test_replanning_keeps_previous_requirements_and_checkpoint(tmp_path, monkeypatch):
    from kestrel_agent.schema import Plan, Action
    engine, store = setup(tmp_path, monkeypatch)
    (tmp_path / 'first.txt').write_text('one')
    (tmp_path / 'second.txt').write_text('two')
    def plan(name, criterion):
        return Plan(mode='plan', message='', actions=[Action(id=name, tool='read_file',
            arguments_json=json.dumps({'path': name + '.txt'}), depends_on=[], purpose='Read', condition='always')], success_criteria=[criterion])
    engine.make_plan = AsyncMock(side_effect=[plan('first', 'Original unfinished requirement'),
        plan('second', 'Recovery requirement'), Plan(mode='clarify', message='Need input', actions=[], success_criteria=[])])
    reviews = []
    async def decide(state, questions):
        if 'original_task' in questions:
            reviews.append(questions)
            return {key: {'choice': 'not_met'} for key in questions}
        return {key: {'choice': 'execute'} for key in questions}
    engine.judge.decide = decide
    try:
        assert await engine._loop() == 'Need input'
        assert len(reviews) == 2
        assert 'Original unfinished requirement' in reviews[1]['criterion_0']['instructions']
        assert 'Recovery requirement' in reviews[1]['criterion_1']['instructions']
        saved = json.loads(store.session(engine.sid)['state'])
        assert len(saved['requirements']) == 2
        assert all(row['status'] == 'not_met' for row in saved['requirements'].values())
        assert all(row['reviewed_evidence'] for row in saved['requirements'].values())
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
async def test_omitted_index_entries_are_reported_and_searchable(tmp_path, monkeypatch):
    engine, store = setup(tmp_path, monkeypatch, max_context_chars=4000)
    try:
        first = observe(engine, store, 'old_approval', {'content': 'retained-first-fact'})
        for i in range(30):
            observe(engine, store, 'extra_' + str(i), {'content': str(i)})
        view = engine.context()
        assert view['evidence_index_omitted'] > 0
        matches = await engine.tools.execute('search_evidence', {'query': 'retained-first-fact'})
        assert matches['matches'][0]['evidence_id'] == first
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
async def test_invalid_plan_gets_one_bounded_correction_before_any_tool(tmp_path, monkeypatch):
    from kestrel_agent.schema import Plan
    engine, store = setup(tmp_path, monkeypatch)
    engine.runtime.mcp_catalog = AsyncMock(return_value=[])
    invalid = json.dumps({'mode': 'answer', 'message': 'Done', 'actions': [],
        'success_criteria': [], 'final_response_ref': '${missing.stdout}'})
    valid = Plan(mode='clarify', message='Need a source', actions=[], success_criteria=[]).model_dump_json()
    engine.runtime.complete = AsyncMock(side_effect=[invalid, valid])
    engine.tools.execute = AsyncMock(side_effect=AssertionError('Invalid plan must not execute'))
    try:
        result = await engine.make_plan()
        assert result.mode == 'clarify'
        assert engine.runtime.complete.await_count == 2
        engine.tools.execute.assert_not_called()
    finally:
        await engine.close()
        store.close()


@pytest.mark.asyncio
async def test_source_pagination_and_tail_remain_visible(tmp_path, monkeypatch):
    engine, store = setup(tmp_path, monkeypatch, max_context_chars=4000)
    (tmp_path / 'large.txt').write_text('first\n' + ('middle\n' * 400) + 'last\n')
    try:
        result = await engine.tools.execute('read_file', {'path': 'large.txt', 'max_lines': 200})
        assert result['truncated'] is True and result['next_line'] == 201
        observe(engine, store, 'large', result)
        view = engine.context()['observations'][0]
        assert view['result_metadata']['next_line'] == 201
        assert view['result_metadata']['total_lines'] == 402
        observe(engine, store, 'long_result', {'content': 'x' * 10000 + 'tail_fact'})
        view = engine.context()['observations'][-1]
        assert 'tail_fact' in view['result_tail_excerpt']
        assert view['result_tail_offset'] > len(view['result_excerpt'])
    finally:
        await engine.close()
        store.close()
