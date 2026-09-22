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
