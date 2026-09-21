"""Responsive terminal command desk; renders without starting providers."""
from pathlib import Path

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.rule import Rule

from . import __version__
from .config import redact
from .provider_presets import label

INK = '#e6edf3'
MUTED = '#98a6b8'
ACCENT = '#e8b86d'
TEAL = '#80cec5'
BORDER = '#465366'


def command_desk(settings, workspace, sid, catalog, width):
    width = min(max(20, width), 116)
    title = Text.assemble((' K E S T R E L ', f'bold {ACCENT}'), (' / COMMAND DESK', MUTED))
    model = Text.assemble((settings.model or 'Provider default', f'bold {INK}'),
                          ('  ·  ' + label(settings), MUTED))
    mode = 'Jev-assisted' if settings.agent_mode == 'jev' else 'Standard'
    strip = Text(f'{mode}   /   {settings.execution_backend} execution   /   {settings.permission}', style=TEAL)
    task_rows = Table.grid(padding=(0, 2), expand=True)
    task_rows.add_column(style=f'bold {ACCENT}', width=12)
    task_rows.add_column(style=INK, overflow='fold')
    for key, purpose in [('/setup', 'Model setup'), ('/skills', 'Skill library'),
                         ('/workflow', 'Saved plans'), ('/connections', 'External tools')]:
        task_rows.add_row(key, purpose)
    left = Panel(task_rows, title=Text('START HERE', style=f'bold {MUTED}'), title_align='left',
                 border_style=BORDER, box=box.ROUNDED, padding=(1, 2))
    skills = catalog.get('skills', [])
    names = {skill['name'] for skill in skills}
    suggested = ['terminal-engineer', 'research-brief', 'data-audit', 'browser-workflow']
    shown = [name for name in suggested if name in names][:4]
    if not shown:
        shown = [skill['name'] for skill in skills[:4]]
    entries = Text(style=INK)
    for index, name in enumerate(shown):
        if index:
            entries.append('\n')
        entries.append('› ', style=TEAL)
        entries.append('/' + name)
    if not shown:
        entries.append('Install a skill to get started.', style=MUTED)
    right = Panel(entries, title=Text(f'SKILL SHELF · {len(skills)}', style=f'bold {MUTED}'),
                  title_align='left', border_style=BORDER, box=box.ROUNDED, padding=(1, 2))
    if width >= 86:
        cards = Table.grid(expand=True, padding=(0, 2))
        cards.add_column(ratio=1)
        cards.add_column(ratio=1)
        cards.add_row(left, right)
    else:
        cards = Group(left, right)
    root = str(workspace)
    user_home = str(Path.home())
    if root == user_home or root.startswith(user_home + '/'):
        root = '~' + root[len(user_home):]
    location = Text.assemble(('WORKSPACE  ', MUTED), (redact(root), INK))
    separator = '\n' if width < 60 else '  ·  '
    footer = Text(f'v{__version__}  ·  {sid[:12]}' + separator + f'network {"on" if settings.network else "off"}', style=MUTED)
    hints = Text.assemble(('Ask naturally', f'bold {INK}'), ('  or use a command above.\n', MUTED),
                          ('Tab', TEAL), (' commands  ·  ', MUTED), ('Alt+Enter', TEAL),
                          (' newline  ·  ', MUTED), ('Ctrl+C', TEAL), (' quit when idle', MUTED))
    return Panel(Group(title, Text(''), model, strip, Text(''), cards, Text(''),
                       location, footer, Text(''), Rule(style=BORDER), hints),
                 width=width, box=box.SIMPLE, padding=(0, 1), border_style=BORDER)
