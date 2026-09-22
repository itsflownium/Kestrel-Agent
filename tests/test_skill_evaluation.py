import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kestrel_agent.cli import app
from kestrel_agent.config import Settings
from kestrel_agent.skill_evaluation import evaluate, export, report
from kestrel_agent.skill_registry import SkillRegistry, capabilities
from kestrel_agent.store import Store
from kestrel_agent.workflow_templates import load

ROOT=Path(__file__).resolve().parents[1]
SUITE=ROOT/'examples/workflows/copy-text.tests.json'
TEMPLATE=ROOT/'examples/workflows/copy-text.json'


def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    root=tmp_path/'state'/'skills'/'sample-skill';root.mkdir(parents=True)
    (root/'SKILL.md').write_text('---\nname: sample-skill\ndescription: Copy input text through a declared workflow.\n---\nUse the declared copy workflow when applicable.\n')
    (root/'kestrel.json').write_text(json.dumps({'workflows':{'copy':'copy.json'}}))
    (root/'copy.json').write_bytes(TEMPLATE.read_bytes())
    settings=Settings();store=Store(settings)
    registry=SkillRegistry(settings,tmp_path/'workspace')
    return registry,store,root


def test_real_workflow_evaluation_is_recorded_and_exports_exact_template(tmp_path,monkeypatch):
    registry,store,root=setup(tmp_path,monkeypatch)
    try:
        result=evaluate(registry,'sample-skill','copy',SUITE,store)
        assert result['passed'] and result['export_eligible']
        assert result['positive_cases']==result['negative_cases']==2
        assert result['certification']=='not_certified'
        assert report(store,result['evaluation_id'])==result
        outcome=export(registry,'sample-skill','copy',result['evaluation_id'],store)
        assert outcome['workflow_name']=='copy-text'
        assert outcome['actions_executed'] is False
        assert load('copy-text')==json.loads(TEMPLATE.read_text())
        assert registry.catalog('sample-skill')['skills'][0]['workflows']==['copy']
        assert registry.load('sample-skill')['workflows']=={'copy':'copy.json'}
        assert not (tmp_path/'workspace').exists()
    finally: store.close()


def test_modified_package_and_wrong_report_cannot_replace_installed_workflow(tmp_path,monkeypatch):
    registry,store,root=setup(tmp_path,monkeypatch)
    try:
        result=evaluate(registry,'sample-skill','copy',SUITE,store)
        eid=result['evaluation_id']
        export(registry,'sample-skill','copy',eid,store)
        target=tmp_path/'state'/'workflow_templates'/'copy-text.json'
        original=target.read_bytes()
        for relative,content in [('SKILL.md',(root/'SKILL.md').read_text()+'Changed instructions.'),('copy.json','{}'),('reference.md','New package content.')]:
            path=root/relative
            before=path.read_bytes() if path.exists() else None
            path.write_text(content)
            with pytest.raises(ValueError,match='changed'):
                export(registry,'sample-skill','copy',eid,store,replace=True)
            assert target.read_bytes()==original
            if before is None: path.unlink()
            else: path.write_bytes(before)
        (root/'alias').symlink_to(root/'copy.json')
        with pytest.raises(ValueError,match='symlink'): export(registry,'sample-skill','copy',eid,store,replace=True)
        (root/'alias').unlink()
        for name,workflow,identifier in [('other','copy',eid),('sample-skill','other',eid),('sample-skill','copy','0'*32),('sample-skill','copy','../report')]:
            with pytest.raises(ValueError): export(registry,name,workflow,identifier,store,replace=True)
        with pytest.raises(ValueError,match='exists'): export(registry,'sample-skill','copy',eid,store)
        assert target.read_bytes()==original
        # Replacement is explicit and does not run the workflow's file actions.
        assert export(registry,'sample-skill','copy',eid,store,replace=True)['actions_executed'] is False
    finally: store.close()


@pytest.mark.parametrize('case',['failed','positive-only'])
def test_failed_or_one_sided_evidence_is_not_export_eligible(tmp_path,monkeypatch,case):
    registry,store,root=setup(tmp_path,monkeypatch)
    suite=json.loads(SUITE.read_text())
    if case=='failed': suite['cases'][0]['expected_files']['saved/copy.txt']='WRONG'
    else: suite['cases']=suite['cases'][:2]
    path=tmp_path/'suite.json';path.write_text(json.dumps(suite))
    try:
        result=evaluate(registry,'sample-skill','copy',path,store)
        assert not result['export_eligible']
        assert result['passed']==(case=='positive-only')
        with pytest.raises(ValueError,match='positive and negative'):
            export(registry,'sample-skill','copy',result['evaluation_id'],store)
        assert not (tmp_path/'state'/'workflow_templates').exists()
    finally: store.close()


@pytest.mark.parametrize('path',['../escape.json','/tmp/escape.json','a//b.json','a/./b.json','.hidden.json','a\\b.json','script.py'])
def test_invalid_export_paths_are_rejected_during_discovery(tmp_path,monkeypatch,path):
    registry,store,root=setup(tmp_path,monkeypatch)
    try:
        (root/'kestrel.json').write_text(json.dumps({'workflows':{'copy':path}}))
        assert not registry.catalog('sample-skill')['skills']
        assert registry.issues
    finally: store.close()


def test_missing_export_and_executable_tools_fail_before_recording_or_install(tmp_path,monkeypatch):
    registry,store,root=setup(tmp_path,monkeypatch)
    try:
        with pytest.raises(ValueError,match='does not declare'):
            evaluate(registry,'sample-skill','absent',SUITE,store)
        template=json.loads(TEMPLATE.read_text())
        template['actions'][0]['tool']='shell'
        template['actions'][0]['arguments']={'command':['touch','must-not-exist']}
        (root/'copy.json').write_text(json.dumps(template))
        with pytest.raises(ValueError,match='file tools only'):
            evaluate(registry,'sample-skill','copy',SUITE,store)
        assert not list(tmp_path.rglob('must-not-exist'))
        assert not (tmp_path/'state'/'workflow_templates').exists()
    finally: store.close()


def test_cli_workflow_testing_report_and_explicit_export(tmp_path,monkeypatch):
    registry,store,root=setup(tmp_path,monkeypatch);store.close()
    runner=CliRunner()
    listing=runner.invoke(app,['skills','workflows','sample-skill'])
    assert listing.exit_code==0
    assert json.loads(listing.stdout)['workflows']=={'copy':'copy.json'}
    tested=runner.invoke(app,['skills','test','sample-skill','copy',str(SUITE)])
    assert tested.exit_code==0,tested.stdout
    result=json.loads(tested.stdout)
    fetched=runner.invoke(app,['skills','report',result['evaluation_id']])
    assert fetched.exit_code==0 and json.loads(fetched.stdout)==result
    exported=runner.invoke(app,['skills','export','sample-skill','copy',result['evaluation_id']])
    assert exported.exit_code==0,exported.stdout
    assert json.loads(exported.stdout)['status']=='installed_from_tested_export'


def test_network_disabled_skills_cannot_advertise_tool_discovery():
    assert not {'discover_tools','inspect_tool'} & capabilities(Settings(network=False))
    assert {'discover_tools','inspect_tool'} <= capabilities(Settings(network=True,permission='read-only'))


@pytest.mark.parametrize('recorded', [None, 'obsolete-runtime'])
def test_export_rejects_missing_or_obsolete_runtime(tmp_path, monkeypatch, recorded):
    registry, store, root = setup(tmp_path, monkeypatch)
    try:
        result = evaluate(registry, 'sample-skill', 'copy', SUITE, store)
        assert len(result['runtime_sha256']) == 64
        if recorded is None:
            result.pop('runtime_sha256')
        else:
            result['runtime_sha256'] = recorded
        with store.db:
            store.db.execute('UPDATE skill_workflow_evaluations SET body=? WHERE id=?',
                             (json.dumps(result), result['evaluation_id']))
        with pytest.raises(ValueError, match='rerun the suite'):
            export(registry, 'sample-skill', 'copy', result['evaluation_id'], store)
        assert not (tmp_path/'state'/'workflow_templates').exists()
    finally:
        store.close()
