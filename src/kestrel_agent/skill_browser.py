"""Local skill discovery: no model calls or skill execution while browsing."""
from prompt_toolkit.application import Application
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import TextArea
from prompt_toolkit.styles import Style


class SkillCompleter(Completer):
    def __init__(self, commands, skills):
        self.commands, self.skills = commands, skills

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith('/') or '\n' in text:
            return
        candidates = {command: 'Command' for command in self.commands}
        for name, skill in self.skills.items():
            candidates['/' + name] = skill.description
            for action in ('show', 'inspect', 'use'):
                candidates[f'/skills {action} {name}'] = skill.description
        for candidate, description in candidates.items():
            if candidate.startswith(text):
                yield Completion(candidate, start_position=-len(text), display_meta=description)


class SkillSelection:
    def __init__(self, rows, query=''):
        self.rows, self.query, self.index = rows, query, 0

    def matches(self):
        terms = self.query.lower().split()
        return [r for r in self.rows if all(t in (' '.join(str(r.get(k, '')) for k in
                ('name', 'description', 'category', 'origin'))).lower() for t in terms)]

    def move(self, amount):
        self.index = max(0, min(self.index + amount, len(self.matches()) - 1))

    def selected(self):
        rows = self.matches()
        return rows[min(self.index, len(rows)-1)] if rows else None


def browser_application(registry, query='', **application_kwargs):
    catalog = registry.catalog(limit=500)
    state = SkillSelection(catalog['skills'], query)
    search = TextArea(text=query, height=1, multiline=False, prompt=' Search › ')
    preview = TextArea(text='', read_only=True, scrollbar=True, wrap_lines=True)
    def update_preview():
        row = state.selected()
        if row:
            skill = registry.discover().get(row['name'])
            preview.text = (f"/{row['name']}  ·  {row.get('category', 'general')}  ·  {row['origin']}\n"
                            f"Status: {', '.join(row['missing']) or 'Available'}\n\n"
                            + (skill.body if skill else 'Skill is no longer available.'))
        else:
            preview.text = 'No matching skills. Change your search.'
    def changed(_):
        state.query, state.index = search.text, 0
        update_preview()
    search.buffer.on_text_changed += changed
    def listing():
        rows = state.matches()
        start = max(0, state.index - 3)
        fragments = []
        for i, row in enumerate(rows[start:start+7], start):
            fragments.append(('class:selected' if i == state.index else '',
                              f" {'›' if i == state.index else ' '} /{row['name']} · {row.get('category', 'general')}\n"))
        return fragments or [('', ' No matches\n')]
    bindings = KeyBindings()
    @bindings.add('up')
    def up(event):
        state.move(-1); update_preview()
    @bindings.add('down')
    def down(event):
        state.move(1); update_preview()
    @bindings.add('tab')
    def focus(event):
        event.app.layout.focus(search if event.app.layout.has_focus(preview) else preview)
    @bindings.add('enter')
    def choose(event):
        row = state.selected()
        if row:
            event.app.exit(result=row['name'])
    @bindings.add('escape')
    @bindings.add('c-c')
    def close(event):
        event.app.exit(result=None)
    update_preview()
    header = lambda: f" KESTREL / SKILLS  ·  {len(state.matches())} matches  ·  {len(catalog['issues'])} discovery issues"
    app = Application(layout=Layout(HSplit([
        Window(FormattedTextControl(header), height=1, style='class:title'), search,
        Window(FormattedTextControl(listing), height=7), preview,
        Window(FormattedTextControl(' ↑↓ select · type to search · Tab preview · PgUp/PgDn scroll · Enter inspect · Esc back'), height=2),
    ]), focused_element=search), key_bindings=bindings, full_screen=True,
        style=Style.from_dict({'title': 'bold #80cec5', 'selected': 'bg:#354557 #ffffff'}),
        **application_kwargs)
    return app
