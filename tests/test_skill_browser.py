import asyncio
from types import SimpleNamespace

import pytest
from prompt_toolkit.document import Document
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from kestrel_agent.skill_browser import SkillCompleter, SkillSelection, browser_application
from kestrel_agent.skill_registry import SkillRegistry
from kestrel_agent.config import Settings


def test_contextual_completion_preserves_skill_task_text():
    c = SkillCompleter(['/skills', '/skills browse'], {'code-review': SimpleNamespace(description='Inspect changes')})
    results = list(c.get_completions(Document('/skills show co'), CompleteEvent()))
    assert [r.text for r in results] == ['/skills show code-review']
    assert results[0].start_position == -len('/skills show co')
    assert not list(c.get_completions(Document('/code-review check this'), CompleteEvent()))
    assert not list(c.get_completions(Document('ordinary prose'), CompleteEvent()))


def test_selection_search_and_boundaries():
    rows = [{'name': 'review', 'category': 'coding', 'description': 'Inspect changes'},
            {'name': 'research', 'category': 'research', 'description': 'Sources'}]
    s = SkillSelection(rows)
    s.move(99); assert s.selected()['name'] == 'research'
    s.query = 'coding inspect'; assert s.selected()['name'] == 'review'
    s.query = 'missing'; assert s.selected() is None
    s.move(-1); assert s.index == 0


@pytest.mark.asyncio
async def test_browser_filters_selects_and_cancels(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'state'))
    registry = SkillRegistry(Settings(), tmp_path)
    for keys, expected in [('debug-root\r', 'debug-root-cause'), ('\x03', None)]:
        with create_pipe_input() as input:
            app = browser_application(registry, input=input, output=DummyOutput())
            task = asyncio.create_task(app.run_async())
            await asyncio.sleep(.05)
            input.send_text(keys)
            assert await asyncio.wait_for(task, 3) == expected


def test_categories_and_new_skills_are_discoverable(tmp_path, monkeypatch):
    monkeypatch.setenv('KESTREL_HOME', str(tmp_path/'state'))
    registry = SkillRegistry(Settings(), tmp_path)
    catalog = registry.catalog(limit=500)
    assert not catalog['issues']
    assert len(catalog['skills']) >= 13
    assert 'code-review' in {s['name'] for s in registry.catalog('coding')['skills']}
    assert 'workflow-designer' in registry.discover()
