import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from kestrel_agent.config import Settings
from kestrel_agent.skill_registry import SkillRegistry, install, rollback, versions


def package(root, name='sample-skill', body='Use the observed inputs.', header=''):
    folder = root/name
    folder.mkdir(parents=True, exist_ok=True)
    (folder/'SKILL.md').write_text(f'---\nname: {name}\ndescription: Inspect a sample artifact.\n{header}---\n\n{body}\n')
    return folder


def registry(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'private'))
    return SkillRegistry(Settings(), tmp_path/'workspace')


def test_metadata_discovery_is_progressive_and_load_is_explicit(tmp_path, monkeypatch):
    reg = registry(tmp_path, monkeypatch)
    package(tmp_path/'private'/'skills', body='Unique full procedure not in descriptions.')
    rows = reg.catalog('sample')
    assert rows['skills'][0]['name'] == 'sample-skill'
    assert 'Unique full procedure' not in json.dumps(rows)
    assert 'Unique full procedure' in reg.load('sample-skill')['guidance']


def test_reference_boundary_and_missing_capabilities(tmp_path, monkeypatch):
    reg = registry(tmp_path, monkeypatch)
    folder = package(tmp_path/'private'/'skills')
    (folder/'references').mkdir()
    (folder/'references'/'safe.md').write_text('Supporting detail')
    assert reg.load('sample-skill', 'references/safe.md')['guidance'] == 'Supporting detail'
    for path in ['../outside.md', '/etc/passwd']:
        with pytest.raises(ValueError):
            reg.load('sample-skill', path)
    (folder/'bad.md').symlink_to('/etc/passwd')
    with pytest.raises(ValueError):
        reg.load('sample-skill', 'bad.md')
    (folder/'kestrel.json').write_text('{"required_tools":["research"]}')
    reg.settings.provider = 'anthropic'
    assert reg.catalog('sample')['skills'][0]['missing'] == ['tool:research']
    with pytest.raises(ValueError, match='prerequisites'):
        reg.load('sample-skill')


def test_manual_only_policy_is_enforced(tmp_path, monkeypatch):
    reg = registry(tmp_path, monkeypatch)
    package(tmp_path/'private'/'skills', header='disable-model-invocation: true\n')
    assert not reg.catalog('sample', for_model=True)['skills']
    with pytest.raises(ValueError, match='explicit'):
        reg.load('sample-skill')
    assert reg.load('sample-skill', explicit=True)['name'] == 'sample-skill'


def test_project_skills_require_trust(tmp_path, monkeypatch):
    reg = registry(tmp_path, monkeypatch)
    package(reg.workspace/'.agents'/'skills')
    assert not reg.catalog('sample')['skills']
    reg.settings.trusted_skill_workspaces.append(str(reg.workspace))
    assert reg.catalog('sample')['skills'][0]['origin'] == 'project'


def test_install_update_and_rollback_preserve_exact_versions(tmp_path, monkeypatch):
    reg = registry(tmp_path, monkeypatch)
    source = package(tmp_path/'source', body='First procedure')
    first = install(source)
    (source/'SKILL.md').write_text((source/'SKILL.md').read_text().replace('First procedure', 'Second procedure'))
    with pytest.raises(ValueError, match='already installed'):
        install(source)
    second = install(source, replace=True)
    assert first['version'] != second['version']
    assert len(versions('sample-skill')) == 2
    assert 'Second procedure' in reg.load('sample-skill')['guidance']
    rollback('sample-skill', first['version'][:12])
    assert 'First procedure' in reg.load('sample-skill')['guidance']
    assert not list((tmp_path/'private'/'skills').glob('.skill-*'))


def test_install_never_executes_scripts_and_rejects_symlinks(tmp_path, monkeypatch):
    registry(tmp_path, monkeypatch)
    source = package(tmp_path/'source')
    (source/'script.py').write_text('raise RuntimeError("must never execute")')
    assert install(source)['name'] == 'sample-skill'
    (source/'outside').symlink_to('/etc/passwd')
    with pytest.raises(ValueError, match='symlinks'):
        install(source, replace=True)


@pytest.mark.asyncio
async def test_engine_loads_user_selected_skill_without_expanding_request(tmp_path, monkeypatch):
    from kestrel_agent.engine import Engine
    from kestrel_agent.store import Store
    from kestrel_agent.schema import Plan
    reg = registry(tmp_path, monkeypatch)
    package(tmp_path/'private'/'skills')
    store = Store(reg.settings)
    engine = Engine(reg.settings, tmp_path, store, store.create(tmp_path), lambda *a: None, AsyncMock())
    engine.make_plan = AsyncMock(return_value=Plan(mode='answer', message='Grounded answer', actions=[], success_criteria=[]))
    engine.judge.decide = AsyncMock(return_value={'direct_answer': {'choice': 'supported'}})
    try:
        assert await engine.run('/sample-skill Explain the supplied input') == 'Grounded answer'
        assert engine.state['request'] == 'Explain the supplied input'
        assert engine.state['selected_skills'][0]['name'] == 'sample-skill'
        assert engine.state['selected_skills'][0]['content_sha256']
    finally:
        await engine.close()
        store.close()
