import json
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from kestrel_agent.config import Settings
from kestrel_agent.engine import Engine
from kestrel_agent.schema import Plan
from kestrel_agent.store import Store


def setup_engine(tmp_path,monkeypatch,response):
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    (tmp_path/'cli.py').write_text('import argparse\np=argparse.ArgumentParser(); p.add_argument("--source", required=True)\n')
    (tmp_path/'input.csv').write_text('value\n3\n')
    settings=Settings();store=Store(settings)
    engine=Engine(settings,tmp_path,store,store.create(tmp_path),lambda *a:None,AsyncMock(return_value=True))
    engine.state['request']='Use the existing CSV input and report the actual result.'
    engine.save()
    engine.runtime.complete=AsyncMock(return_value=json.dumps(response))
    engine.runtime.command=AsyncMock(side_effect=AssertionError('Preparation must not execute'))
    return engine,store


def arguments(exit_code=2):
    return {'command':['python3','cli.py'],'failure':{'exitCode':exit_code,'stderr':'--source is required'},'cwd':'.'}


@pytest.mark.asyncio
async def test_repair_is_grounded_preparation_only(tmp_path,monkeypatch):
    engine,store=setup_engine(tmp_path,monkeypatch,{'ready':True,'command':['python3','cli.py','--source','input.csv'],'reason':'Observed required flag and existing input.'})
    try:
        result=await engine.tools.execute('repair_command',arguments())
        assert result['ready'] and result['command'][-1]=='input.csv'
        prompt=engine.runtime.complete.call_args.args[0]
        assert 'Use the existing CSV input' in prompt
        assert 'value' in prompt and '--source' in prompt
        assert {s['path'] for s in result['inspected_sources']}=={str(tmp_path/'cli.py'),str(tmp_path/'input.csv')}
        engine.runtime.command.assert_not_called()
    finally: await engine.close();store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('command',[
    ['sh','-c','echo changed'], ['python3','other.py'], ['python3','cli.py'], ['python3','cli.py','\x00']])
async def test_repair_rejects_program_changes_and_repetition(tmp_path,monkeypatch,command):
    engine,store=setup_engine(tmp_path,monkeypatch,{'ready':True,'command':command,'reason':'Correction'})
    try:
        with pytest.raises(ValueError): await engine.tools.execute('repair_command',arguments())
        engine.runtime.command.assert_not_called()
    finally: await engine.close();store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('exit_code',[0,None,False])
async def test_unknown_or_successful_outcome_cannot_trigger_repair(tmp_path,monkeypatch,exit_code):
    engine,store=setup_engine(tmp_path,monkeypatch,{'ready':False,'command':[],'reason':'Missing evidence'})
    try:
        with pytest.raises(ValueError): await engine.tools.execute('repair_command',arguments(exit_code))
        engine.runtime.complete.assert_not_called()
    finally: await engine.close();store.close()


@pytest.mark.asyncio
async def test_unresolved_repair_does_not_invent_input(tmp_path,monkeypatch):
    engine,store=setup_engine(tmp_path,monkeypatch,{'ready':False,'command':[],'reason':'Input is ambiguous.'})
    try:
        result=await engine.tools.execute('repair_command',arguments())
        assert result['ready'] is False and result['command']==[]
        engine.runtime.command.assert_not_called()
    finally: await engine.close();store.close()


def test_whole_result_reference_requires_dependency():
    with pytest.raises(ValidationError):
        Plan.model_validate({'mode':'plan','message':'Prepare','actions':[
            {'id':'repair','tool':'repair_command','arguments_json':'{"failure":"${unknown}"}',
             'depends_on':[],'purpose':'Prepare','condition':'always'}],'success_criteria':[]})


@pytest.mark.asyncio
async def test_unresolved_repair_cannot_include_command(tmp_path, monkeypatch):
    engine, store = setup_engine(tmp_path, monkeypatch, {
        'ready': False, 'command': ['python3', 'cli.py', '--source', 'invented.csv'],
        'reason': 'No suitable input found.'})
    try:
        with pytest.raises(ValueError, match='unresolved'):
            await engine.tools.execute('repair_command', arguments())
        engine.runtime.command.assert_not_called()
    finally:
        await engine.close()
        store.close()
