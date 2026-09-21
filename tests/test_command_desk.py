import io
from pathlib import Path

import pytest
from rich.console import Console
from rich.cells import cell_len

from kestrel_agent.config import Settings
from kestrel_agent.dashboard import command_desk


@pytest.mark.parametrize('width', [40, 60, 80, 100, 140])
def test_command_desk_fits_and_keeps_controls_readable(width):
    output = io.StringIO()
    console = Console(file=output, width=width, color_system=None)
    catalog = {'skills': [{'name': name} for name in ['terminal-engineer', 'research-brief', 'data-audit', 'browser-workflow']]}
    console.print(command_desk(Settings(agent_mode='standard'), Path('/workspace/a long project'), 'session1234567890', catalog, width))
    rendered = output.getvalue()
    assert all(cell_len(line) <= width for line in rendered.splitlines())
    for command in ['/setup', '/skills', '/workflow', '/connections']:
        assert command in rendered
    assert 'Provider default' in rendered
    assert 'network on' in rendered
    assert 'Your workspace' not in rendered


def test_live_prompt_reflows_after_resize(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from prompt_toolkit.output import DummyOutput
    from prompt_toolkit.data_structures import Size
    from prompt_toolkit.formatted_text import fragment_list_to_text
    from kestrel_agent import ui
    monkeypatch.setattr(ui, 'Engine', lambda *args: SimpleNamespace(close=AsyncMock()))
    terminal = ui.Terminal(Settings(agent_mode='standard'), tmp_path, None, 'resize-test')
    output = terminal.prompt.output
    sizes = [Size(rows=54, columns=80)]
    monkeypatch.setattr(output, 'get_size', lambda: sizes[0])
    terminal.welcome()
    narrow = fragment_list_to_text(terminal.input_prompt())
    sizes[0] = Size(rows=54, columns=207)
    wide = fragment_list_to_text(terminal.input_prompt())
    assert 'SKILL SHELF' in narrow and 'SKILL SHELF' in wide
    assert max(cell_len(line) for line in wide.splitlines()) >= 200
    assert max(cell_len(line) for line in narrow.splitlines()) <= 80
    sizes[0] = Size(rows=24, columns=60)
    short = fragment_list_to_text(terminal.input_prompt())
    assert 'COMMAND DESK' in short and len(short.splitlines()) < 10
