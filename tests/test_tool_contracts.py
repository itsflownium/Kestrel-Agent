import json
from typing import get_args
from unittest.mock import AsyncMock

import pytest

from kestrel_agent.config import Settings
from kestrel_agent.schema import Action, Plan, ToolName, bind
from kestrel_agent.tool_contracts import CONTRACTS, validate_arguments
from kestrel_agent.tools import ToolExecutor


def test_every_registered_tool_has_a_contract():
    assert set(CONTRACTS) == set(get_args(ToolName))


@pytest.mark.parametrize('tool,args', [
    ('write_file', {'path':'output.txt','content':None}),
    ('write_file', {'path':'output.txt','content':{'unserialized':'value'}}),
    ('shell', {'command':'echo unsafe'}),
    ('shell', {'command':['echo', 7]}),
    ('read_file', {'path':'a','max_lines':True}),
    ('read_file', {'path':'a','start_lien':10}),
    ('query_table', {'path':'a.csv','operation':'delete'}),
    ('query_table', {'path':'a.csv','operation':'sum','filters':[{'column':'a','op':'eq'}]}),
])
def test_invalid_literals_rejected_even_when_planning(tool,args):
    with pytest.raises(ValueError, match='Invalid'):
        validate_arguments(tool,args,allow_references=True)


def test_references_defer_only_their_own_fields():
    args = {'path':'output.txt','content':'${source.data}'}
    validate_arguments('write_file',args,allow_references=True)
    with pytest.raises(ValueError, match='content'):
        validate_arguments('write_file',bind(args,{'source':{'data':{'not':'text'}}}))
    with pytest.raises(ValueError, match='unexpected'):
        validate_arguments('write_file',{**args,'unexpected':'${source.data}'},allow_references=True)
    with pytest.raises(ValueError, match='path'):
        validate_arguments('write_file',{'content':'${source.data}'},allow_references=True)
    with pytest.raises(ValueError, match='limit'):
        validate_arguments('search_evidence',{'query':'${source.text}','limit':False},allow_references=True)


def test_nested_numeric_reference_validates_after_binding():
    args={'path':'data.json','operation':'count','filters':[{'column':'count','op':'${mode.value}','value':3}]}
    validate_arguments('query_table',args,allow_references=True)
    assert validate_arguments('query_table',bind(args,{'mode':{'value':'gt'}}))['filters'][0]['op']=='gt'
    with pytest.raises(ValueError):
        validate_arguments('query_table',bind(args,{'mode':{'value':'delete'}}))


def test_invalid_action_prevents_entire_plan_acceptance():
    with pytest.raises(ValueError, match='content'):
        Plan(mode='plan',message='',success_criteria=[],actions=[Action(id='write',tool='write_file',
            arguments_json=json.dumps({'path':'a','content':None}),depends_on=[],purpose='Write',condition='always')])


@pytest.mark.asyncio
async def test_invalid_arguments_have_no_write_or_command_effect(tmp_path):
    runtime=type('Runtime',(),{'command':AsyncMock()})()
    tools=ToolExecutor(Settings(),tmp_path,runtime,None,None,'test',AsyncMock())
    with pytest.raises(ValueError):
        await tools.execute('write_file',{'path':'output.txt','content':None})
    assert not (tmp_path/'output.txt').exists()
    with pytest.raises(ValueError):
        await tools.execute('shell',{'command':'echo invalid'})
    runtime.command.assert_not_called()


@pytest.mark.parametrize('tool,args', list({
    'list_files': {}, 'read_file': {'path':'a'}, 'search_files': {'query':'needle'},
    'write_file': {'path':'out','content':'text\n'}, 'shell': {'command':['echo','ok']},
    'repair_command': {'command':['python3','a.py'],'failure':{'exitCode':2}},
    'fetch_url': {'url':'https://example.com'}, 'mcp': {'server':'s','tool':'t','arguments':{'data':[1,2]}},
    'generate': {'prompt':'Write an explanation'}, 'research': {'prompt':'Find references'},
    'choose': {'question':'Pick one','options':[{'value':1}]},
    'read_evidence': {'id':'evidence-id'}, 'search_evidence': {'query':''},
    'query_table': {'path':'a.csv','operation':'sum','value_column':'amount','filters':[{'column':'status','op':'eq','value':'paid'}]},
}.items()))
def test_valid_arguments_for_every_tool(tool,args):
    validated=validate_arguments(tool,args)
    assert all(validated[key] == value for key,value in args.items())
