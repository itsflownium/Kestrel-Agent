import json
from unittest.mock import AsyncMock

import pytest

from kestrel_agent.schema import Action, bind


def test_missing_field_identifies_reference_and_available_keys_without_values():
    result={'skill':{'guidance':'PRIVATE BODY','version':'PRIVATE VERSION'}}
    with pytest.raises(ValueError) as failure:
        bind({'prompt':'Guidance: ${skill.content}'},result)
    text=str(failure.value)
    assert '${skill.content}' in text and 'guidance' in text and 'version' in text
    assert 'PRIVATE' not in text
    assert bind({'prompt':'Guidance: ${skill.guidance}'},result)=={'prompt':'Guidance: PRIVATE BODY'}


@pytest.mark.parametrize('reference,fragment', [
    ('${missing.field}','Available fields'),
    ('${rows.nope}','integer index'),
    ('${rows.5}','outside the list'),
    ('${rows.-3}','outside the list'),
    ('${rows.0.missing}','Available fields'),
    ('${scalar.field}','not an object or list'),
    ('${nothing.field}','not an object or list'),
])
def test_invalid_references_fail_closed_with_shape_diagnostics(reference,fragment):
    with pytest.raises(ValueError,match=fragment):
        bind(reference,{'rows':[{'value':'SECRET'}],'scalar':'SECRET','nothing':None})


def test_reference_types_and_existing_negative_indices_are_preserved():
    value={'rows':[{'value':[1,2]}, {'value':False}]}
    assert bind('${rows.0.value}',value)==[1,2]
    assert bind('${rows.-1.value}',value) is False
    assert bind('value=${rows.1.value}',value)=='value=False'
    assert bind('$(echo literal)',value)=='$(echo literal)'


def test_error_metadata_is_bounded_and_terminal_control_characters_are_escaped():
    values={f'field-{i}-'+'x'*100:'PRIVATE' for i in range(100)}
    values['\x1b[31m']='PRIVATE'
    with pytest.raises(ValueError) as failure: bind('${source.absent}',{'source':values})
    text=str(failure.value)
    assert len(text)<1800 and '89 more omitted' in text and 'PRIVATE' not in text
    with pytest.raises(ValueError) as failure: bind('${source.absent}',{'source':{'\x1b[31m':'PRIVATE'}})
    assert '\x1b' not in str(failure.value)
    assert '\\u001b' in str(failure.value)


@pytest.mark.asyncio
async def test_bad_reference_is_recorded_without_dispatch_or_uncertain_effect(tmp_path,monkeypatch):
    from kestrel_agent.config import Settings
    from kestrel_agent.engine import Engine
    from kestrel_agent.store import Store
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    settings=Settings(agent_mode='standard')
    store=Store(settings)
    engine=Engine(settings,tmp_path,store,store.create(tmp_path),lambda *_:None,AsyncMock())
    engine.state.update(results={'skill':{'guidance':'private guidance'}},statuses={'skill':'completed'})
    engine.tools.execute=AsyncMock(side_effect=AssertionError('Invalid binding must not dispatch'))
    try:
        await engine.perform(Action(id='write',tool='write_file',arguments_json=json.dumps({'path':'out.txt','content':'${skill.content}'}),
            depends_on=['skill'],purpose='Write requested output',condition='always'))
        assert engine.state['statuses']['write']=='error'
        assert 'guidance' in engine.state['results']['write']['error']
        assert 'private guidance' not in engine.state['results']['write']['error']
        engine.tools.execute.assert_not_called()
        assert not (tmp_path/'out.txt').exists()
        assert not engine.state['uncertain_effects']
        observed=engine.state['observations'][-1]
        invocation=store.read_evidence(engine.sid,observed['invocation_evidence_id'])
        assert invocation['executor_called'] is False
        assert invocation['executor_returned'] is False
    finally:
        await engine.close();store.close()


@pytest.mark.asyncio
async def test_documented_skill_binding_matches_real_tool_result(tmp_path,monkeypatch):
    from kestrel_agent.config import Settings
    from kestrel_agent.engine import Engine
    from kestrel_agent.store import Store
    from kestrel_agent.tools import CATALOG
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    settings=Settings(agent_mode='standard')
    store=Store(settings)
    engine=Engine(settings,tmp_path,store,store.create(tmp_path),lambda *_:None,AsyncMock())
    try:
        result=await engine.tools.execute('load_skill',{'name':'terminal-engineer'})
        assert '${action.guidance}' in CATALOG
        assert bind('${action.guidance}',{'action':result})==result['guidance']
        assert result['guidance'].strip()
    finally:
        await engine.close();store.close()


def test_long_unicode_field_names_cannot_flood_the_error_context():
    values={('東京'*100)+str(i):'PRIVATE VALUE' for i in range(30)}
    with pytest.raises(ValueError) as failure:
        bind('${source.absent}',{'source':values})
    assert len(str(failure.value))<=2000
    assert 'diagnostic truncated' in str(failure.value)
    assert 'PRIVATE VALUE' not in str(failure.value)


def test_very_large_numeric_index_has_a_bounded_diagnostic():
    with pytest.raises(ValueError) as failure:
        bind('${rows.'+'9'*4000+'}',{'rows':[1]})
    assert len(str(failure.value))<=2000
    assert 'outside the list' in str(failure.value)


def test_json_unicode_escaping_cannot_hide_a_dependency_reference():
    from kestrel_agent.schema import Plan
    first=Action(id='source',tool='read_file',arguments_json='{"path":"input.txt"}',depends_on=[],purpose='Read',condition='always')
    encoded='{"path":"out.txt","content":"${' + chr(92) + 'u0073ource.raw_text}"}'
    second=Action(id='save',tool='write_file',arguments_json=encoded,depends_on=[],purpose='Save',condition='always')
    with pytest.raises(ValueError,match='declared dependency'):
        Plan(mode='plan',message='Copy',actions=[first,second],success_criteria=[])
    second.depends_on=['source']
    plan=Plan(mode='plan',message='Copy',actions=[first,second],success_criteria=[])
    assert bind(plan.actions[1].arguments(),{'source':{'raw_text':'observed text'}})['content']=='observed text'


def test_dictionary_keys_remain_literal_in_graph_validation_and_binding():
    from kestrel_agent.schema import Plan
    arguments={'server':'fixture','tool':'accept','arguments':{'${literal.key}':'value'}}
    action=Action(id='call',tool='mcp',arguments_json=json.dumps(arguments),depends_on=[],purpose='Pass literal key',condition='always')
    Plan(mode='plan',message='Use literal key',actions=[action],success_criteria=[])
    assert bind(arguments,{})==arguments
