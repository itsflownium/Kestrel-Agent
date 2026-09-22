from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.history import DummyHistory
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style
from rich.console import Console
from rich import box
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__
from .config import Settings, redact, load_secrets, home, atomic_write
from .engine import Engine
from .store import Store
from .provider_presets import PRESETS, select, label as provider_label

COMMANDS = ["/connections", "/connections add", "/connections remove", "/setup", "/details", "/details on", "/details off", "/skills", "/skills show", "/skills check", "/skills use", "/help", "/mode", "/mode standard", "/mode jev", "/new", "/continue", "/sessions", "/resume", "/model", "/model jev-key", "/model provider-key", "/provider", "/permissions", "/config", "/tools", "/status", "/clear", "/exit"]
STYLE = Style.from_dict({
    "prompt": "#8bd5ca bold", "input-border": "#414b60", "hint": "#8993a7",
    "bottom-toolbar": "bg:#20232b #a8acb8", "status": "bg:#20232b #8bd5ca bold",
    "approval": "#f9e2af bold", "completion-menu.completion": "bg:#20232b #cdd6f4",
    "completion-menu.completion.current": "bg:#3a4554 #ffffff",
})


class Terminal:
    def __init__(self, settings: Settings, workspace: Path, store: Store, sid: str):
        self.settings, self.workspace, self.store, self.sid = settings, workspace, store, sid
        self.console = Console(highlight=False)
        self.phase = "ready"
        self.busy = False
        self.started_at = 0.0
        self.job: asyncio.Task | None = None
        self.pending_approval: asyncio.Future | None = None
        bindings = KeyBindings()

        @bindings.add("c-c")
        def interrupt(event):
            if self.job and not self.job.done():
                self.job.cancel()
                self.phase = "stopping"
            else:
                event.app.exit(exception=EOFError)

        @bindings.add("escape", "enter")
        def newline(event):
            event.current_buffer.insert_text("\n")

        self.prompt = PromptSession(
            completer=WordCompleter(COMMANDS, sentence=True), complete_while_typing=False,
            style=STYLE, key_bindings=bindings,
            bottom_toolbar=self.toolbar, refresh_interval=0.15,
            reserve_space_for_menu=4,
        )
        self.engine = Engine(settings, workspace, store, sid, self.emit, self.confirm)
        self.refresh_skills()

    def refresh_skills(self):
        from .skill_registry import SkillRegistry
        self.skill_registry = SkillRegistry(self.settings, self.workspace)
        self.prompt.completer = WordCompleter(COMMANDS + ['/' + name for name in self.skill_registry.discover()], sentence=True)

    def toolbar(self):
        if self.pending_approval is not None:
            status = "◆ Awaiting permission"
        elif self.busy:
            spinner = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[int(time.monotonic() * 8) % 10]
            elapsed = max(0, int(time.monotonic() - self.started_at))
            status = f"{spinner} {self.phase} · {elapsed}s"
        else:
            status = "● Ready"
        width = self.console.size.width
        interrupt_hint = "stop" if self.job and not self.job.done() else "quit"
        details = f"  {self.settings.permission}  ·  Ctrl+C {interrupt_hint}" if width < 90 else f"  {self.settings.model or self.settings.provider} · {self.settings.agent_mode}  ·  {self.settings.permission}  ·  /help  ·  Ctrl+C {interrupt_hint}"
        return [("class:status", f"  {status}  "), ("", details)]

    def input_prompt(self):
        width = max(12, min(self.console.size.width - 4, 88))
        label = "Permission · yes / no" if self.pending_approval is not None else ("Working · Ctrl+C to stop" if self.busy else "Message Kestrel")
        return [("class:input-border", "\n  " + "─" * width + "\n"),
                ("class:hint", f"  {label}\n"), ("class:prompt", "  ❯ ")]

    def welcome(self):
        self.refresh_skills()
        width = min(self.console.size.width, 92)
        self.console.print()
        brand = Table.grid(padding=(0, 2))
        brand.add_column(style="bold #8bd5ca", no_wrap=True)
        brand.add_column()
        brand.add_row("  ╲  ╱\n   ◇\n  ╱  ╲", Text.assemble(
            ("KESTREL", "bold #e6edf3"), (f"   v{__version__}\n", "#8993a7"),
            ("Think deeply. Move lightly.\n", "#a8acb8"),
            ("Your terminal, with a little more lift.", "#8993a7")))
        self.console.print(brand)
        self.console.print()
        workspace = str(self.workspace)
        user_home = str(Path.home())
        if workspace == user_home or workspace.startswith(user_home + "/"):
            workspace = "~" + workspace[len(user_home):]
        info = Table.grid(padding=(0, 2))
        info.add_column(style="#8993a7")
        info.add_column(style="#d8dee9", overflow="fold")
        info.add_row("Workspace", workspace)
        info.add_row("Provider", provider_label(self.settings))
        info.add_row("Models", f"{self.settings.model or 'default'}  ·  {self.settings.agent_mode}")
        info.add_row("Execution", self.settings.execution_backend + (" · " + self.settings.docker_image if self.settings.execution_backend == 'docker' else " sandbox"))
        info.add_row("Access", f"{self.settings.permission} · network {'on' if self.settings.network else 'off'}")
        catalog = self.skill_registry.catalog()
        info.add_row("Skills", f"{len(catalog['skills'])} available · /skills to explore")
        self.console.print(Panel(info, title="[bold #8bd5ca]Your workspace[/]", title_align="left",
                                 subtitle=f"[dim]session {self.sid}[/dim]", subtitle_align="right",
                                 width=width, box=box.ROUNDED, border_style="#414b60", padding=(1, 2)))
        suggestions = Text.assemble(
            ("  Start anywhere\n", "bold #d8dee9"),
            ("  Explain a project   ·   Compare documents   ·   Research an idea\n\n", "#8993a7"),
            ("  /setup", "#8bd5ca"), (" configure    ", "#8993a7"),
            ("/skills", "#8bd5ca"), (" extend    ", "#8993a7"),
            ("/permissions", "#8bd5ca"), (" access    ", "#8993a7"),
            ("/help", "#8bd5ca"), (" all commands", "#8993a7"))
        self.console.print(suggestions)

    def emit(self, kind: str, text: str):
        if kind in {"model", "judge", "tool", "connecting"}:
            self.phase = redact(text)[:65]
        if not self.settings.ui_details and kind in {"model", "judge", "planned", "decision", "connecting"}:
            return
        if kind == "output":
            if not self.settings.ui_details:
                lines = redact(text).splitlines()
                text = '\n'.join(lines[:5])[:600]
                if len(lines) > 5 or len(redact(text)) >= 600:
                    text += '\n… /details on shows subsequent full output; session logs retain evidence.' 
            self.console.print(Panel(Text(redact(text)), title="[dim]tool output[/dim]", title_align="left",
                                     width=min(self.console.size.width, 100), box=box.ROUNDED,
                                     border_style="#303642", padding=(0, 1)))
            return
        symbols = {"model": ("◌", "#a6adc8"), "judge": ("◇", "#8bd5ca"), "plan": ("→", "#c4b5fd"),
                   "planned": ("·", "dim"), "tool": ("↳", "#89b4fa"), "done": ("✓", "#a6e3a1"),
                   "warning": ("!", "#f9e2af"), "decision": ("·", "dim"), "usage": ("─", "dim")}
        if kind == "delta":
            self.console.print(text, end="", markup=False)
            return
        symbol, color = symbols.get(kind, ("·", "white"))
        if kind in {"model", "judge", "tool", "connecting"}:
            self.phase = text[:65]
        line = Text(f"  {symbol} ", style=color)
        line.append(redact(text))
        self.console.print(line)

    async def confirm(self, description: str) -> bool:
        # Keep a single prompt active while the background worker awaits user input.
        self.console.print(Panel(Text(redact(description)), title="Permission requested", border_style="#f9e2af"))
        self.console.print("  Enter [bold]yes[/bold] to allow once, or [bold]no[/bold] to decline.")
        self.pending_approval = asyncio.get_running_loop().create_future()
        try:
            return await self.pending_approval
        finally:
            self.pending_approval = None

    async def work(self, message: str | None):
        self.busy = True
        self.started_at = time.monotonic()
        self.phase = "Routing"
        self.emit("connecting", f"{self.settings.agent_mode.capitalize()} mode · preparing your task")
        try:
            answer = await self.engine.run(message)
            self.console.print()
            self.console.print(Text("  ◇ Kestrel", style="bold #8bd5ca"))
            self.console.print(Panel(Markdown(answer), width=min(self.console.size.width, 100),
                                     box=box.ROUNDED, border_style="#414b60", padding=(1, 2)))
        except asyncio.CancelledError:
            self.emit("warning", "Stopped. /continue resumes the task; /status shows its checkpoint.")
        except Exception as error:
            self.emit("warning", redact(str(error)))
        finally:
            self.busy = False
            self.phase = "ready"

    async def chat(self):
        self.welcome()
        with patch_stdout(raw=True):
            await self.ensure_keys()
            while True:
                try:
                    message = (await self.prompt.prompt_async(self.input_prompt)).strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if not message:
                    continue
                if self.pending_approval is not None:
                    if message.lower() not in {"yes", "y", "no", "n"}:
                        self.emit("warning", "Please answer yes or no for the pending action.")
                    elif not self.pending_approval.done():
                        self.pending_approval.set_result(message.lower() in {"yes", "y"})
                    continue
                if message == "/exit":
                    break
                if self.busy:
                    self.emit("warning", "A task is running. Ctrl+C stops it before you send another request.")
                    continue
                try:
                    if message.startswith("/"):
                        await self.command(message)
                    else:
                        self.job = asyncio.create_task(self.work(message))
                        # Set immediately so two fast submissions cannot start concurrent runs.
                        self.busy = True
                except Exception as error:
                    self.emit("warning", redact(str(error)))
        if self.job and not self.job.done():
            self.job.cancel()
            await asyncio.gather(self.job, return_exceptions=True)
        await self.engine.close()

    async def command(self, message: str):
        name, _, argument = message.partition(" ")
        argument = argument.strip()
        if name == "/help":
            table = Table(show_header=False, box=None, padding=(0, 2))
            for command, meaning in [
                ("/setup", "Configure models, auth, mode, and Docker execution"),
                ("/connections [add NAME URL|remove NAME]", "Connect browser, desktop, and service tools over MCP"),
                ("/details [on|off]", "Show or hide detailed agent activity"),
                ("/new", "Start a fresh conversation"), ("/continue", "Continue interrupted work"),
                ("/sessions · /resume ID", "List or reopen conversations"), ("/model [ID]", "List/select model and configure Jev key"),
                ("/skills [query] · /skills show NAME", "Discover skills or inspect guidance"),
                ("/skills use NAME TASK", "Apply a skill; /NAME TASK also works"),
                ("/mode [standard|jev]", "Choose one-provider or Jev-assisted decisions"),
                ("/provider [NAME]", "Choose provider, endpoint, model, and keys"),
                ("/model jev-key · /model provider-key", "Enter or replace keys privately"),
                ("/permissions [read-only|workspace|full]", "View or change access profile"),
                ("/config", "Inspect settings; use kestrel config set KEY VALUE to edit"),
                ("/tools", "List built-in capabilities and connected MCP tools"), ("/status", "Show checkpoint and usage"),
                ("/clear · /exit", "Clear the screen or leave"), ("Ctrl+C · Alt+Enter", "Stop a task or quit when idle · insert newline")]:
                if not argument or argument.lower() in (command + " " + meaning).lower():
                    table.add_row(command, meaning)
            self.console.print(table)
        elif name == "/connections":
            import shlex
            from .connections import Connection
            parts = shlex.split(argument)
            if parts and parts[0] == 'add':
                if len(parts) not in {3, 4} or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', parts[1]):
                    raise ValueError('Use /connections add NAME URL [BEARER_ENV]')
                connection = Connection(url=parts[2], bearer_env=parts[3] if len(parts) == 4 else None)
                await self.engine.runtime.connections.close()
                self.settings.mcp_connections[parts[1]] = connection
                self.settings.save()
                self.engine.mcp_tools = None
                self.emit('done', 'Connection saved. Tools require approval unless explicitly allowlisted.')
            elif parts and parts[0] == 'remove':
                if len(parts) != 2 or parts[1] not in self.settings.mcp_connections:
                    raise ValueError('Use /connections remove NAME with a configured name.')
                await self.engine.runtime.connections.close()
                del self.settings.mcp_connections[parts[1]]
                self.settings.mcp_auto_allow = [entry for entry in self.settings.mcp_auto_allow if not entry.startswith(f'direct:{parts[1]}/')]
                self.settings.save()
                self.engine.mcp_tools = None
            elif parts:
                raise ValueError('Use /connections, /connections add NAME URL [BEARER_ENV], or /connections remove NAME.')
            table = Table('Connection', 'Endpoint', 'Enabled', box=box.SIMPLE)
            for key, value in self.settings.mcp_connections.items():
                table.add_row('direct:' + key, value.url, str(value.enabled))
            self.console.print(table)
            self.console.print('  /connections add NAME URL [BEARER_ENV] · /tools discovers tools', style='dim')
        elif name == "/details":
            if argument and argument not in {'on', 'off'}:
                raise ValueError('Use /details on or /details off.')
            self.settings.ui_details = argument == 'on' if argument else not self.settings.ui_details
            self.settings.save()
            self.emit('done', 'Detailed activity ' + ('on' if self.settings.ui_details else 'off'))
        elif name == "/setup":
            from .setup import configure
            prompt = PromptSession(history=DummyHistory(), output=self.prompt.output)
            async def ask(label, default):
                answer = (await prompt.prompt_async(f'  {label} [{default}]: ')).strip()
                return answer or default
            try:
                candidate = await configure(self.settings, ask, lambda value: self.console.print(Text(value)))
            except (EOFError, KeyboardInterrupt):
                self.emit('warning', 'Setup cancelled; settings unchanged.')
                return
            await self.engine.close()
            candidate.save()
            self.settings = candidate
            self.engine = Engine(candidate, self.workspace, self.store, self.sid, self.emit, self.confirm)
            self.refresh_skills()
            await self.ensure_keys()
            if candidate.provider == 'codex':
                self.console.print('  Codex OAuth: kestrel auth login', style='dim')
            self.emit('done', 'Setup saved. Docker requires a running daemon and locally installed image.' if candidate.execution_backend == 'docker' else 'Setup saved.')
            self.welcome()
        elif name == "/skills":
            self.refresh_skills()
            subcommand, _, rest = argument.partition(' ')
            if subcommand == 'show':
                self.console.print(Markdown(self.skill_registry.load(rest.strip(), explicit=True)['guidance']))
            elif subcommand == 'use':
                skill, _, task = rest.partition(' ')
                self.skill_registry.load(skill, explicit=True)
                self.busy = True
                self.job = asyncio.create_task(self.work('/' + skill + ' ' + task))
            else:
                catalog = self.skill_registry.catalog('' if subcommand == 'check' else argument)
                table = Table('Skill', 'Purpose', 'Status', box=box.SIMPLE, expand=False)
                for skill in catalog['skills']:
                    status = ', '.join(skill['missing']) or ('manual' if skill['manual_only'] else skill['origin'])
                    table.add_row('/' + skill['name'], skill['description'], status)
                self.console.print(table)
                for issue in catalog['issues']:
                    self.emit('warning', f"{issue['path']}: {issue['error']}")
                self.console.print('  /skills show NAME · /NAME your task · kestrel skills install PATH', style='dim')
        elif name == "/clear":
            self.console.clear()
            self.welcome()
        elif name in {"/new", "/resume"}:
            sid = self.store.create(self.workspace) if name == "/new" else argument
            record = self.store.session(sid)
            await self.engine.close()
            self.sid, self.workspace = sid, Path(record["workspace"])
            self.engine = Engine(self.settings, self.workspace, self.store, sid, self.emit, self.confirm)
            self.welcome()
            if name == "/resume":
                for item in self.store.history(sid, 10):
                    if item["kind"] in {"user", "assistant"}:
                        self.console.print(Panel(Text(str(item["body"])), title=item["kind"], border_style="dim"))
        elif name == "/sessions":
            for record in self.store.sessions():
                self.console.print(Text(f"  {record['id']}  {record['title']}  {record['workspace']}"))
        elif name == "/continue":
            self.busy = True
            self.job = asyncio.create_task(self.work(None))
        elif name == "/status":
            state = self.engine.state
            self.console.print_json(json.dumps({k: state.get(k) for k in ("status", "steps", "statuses", "usage")}))
        elif name == "/config":
            self.console.print_json(self.settings.model_dump_json())
        elif name == "/permissions":
            if argument:
                self.settings.permission = argument
                self.settings.save()
            self.console.print(Text(f"  Profile: {self.settings.permission} · shell confirmation: {self.settings.confirm_shell} · network: {self.settings.network}"))
        elif name == "/mode":
            if argument:
                if argument not in {"standard", "jev"}:
                    raise ValueError("Choose /mode standard or /mode jev.")
                await self.engine.close()
                self.settings.agent_mode = argument
                self.settings.save()
                self.engine = Engine(self.settings, self.workspace, self.store, self.sid, self.emit, self.confirm)
                await self.ensure_keys()
            self.console.print(Text(f"  Mode: {self.settings.agent_mode} · " + ("decisions use your selected model" if self.settings.agent_mode == "standard" else "decisions use Jev")))
        elif name == "/provider":
            await self.configure_provider(argument)
        elif name == "/model":
            if argument in {"jev-key", "provider-key"}:
                await self.configure_key(argument == "jev-key")
                return
            load_secrets()
            self.console.print(Text(f"  Provider: {provider_label(self.settings)} · Model: {self.settings.model or 'default'} · Jev key: {'configured' if os.environ.get('TYPESAFE_API_KEY') else 'missing'}"))
            self.console.print("  /model jev-key replaces the Jev key; /model provider-key sets the generation API key.", style="dim")
            if self.settings.agent_mode == 'jev' and not os.environ.get('TYPESAFE_API_KEY'):
                await self.configure_key(True)
            if self.settings.provider != "codex":
                if argument:
                    self.settings.model = argument
                    self.settings.save()
                    self.emit("done", f"Model set to {argument}")
                else:
                    try:
                        for model in await self.engine.runtime.generator.models():
                            self.console.print(Text(f"  {model}"))
                    except Exception as error:
                        self.emit("warning", f"Model listing unavailable: {redact(str(error))}. Set an exact ID with /model MODEL_ID.")
                return
            await self.engine.runtime.start()
            models = (await self.engine.runtime.codex.models()).data
            if argument:
                available = {m.model for m in models}
                if argument not in available:
                    raise ValueError("Choose one of the model IDs listed by /model.")
                self.settings.model = argument
                self.settings.save()
                self.emit("done", f"Model set to {argument}")
            else:
                for model in models:
                    self.console.print(Text(f"  {model.model} · {model.display_name}"))
        elif name == "/tools":
            from .skill_registry import capabilities
            self.console.print(Panel(Text(', '.join(sorted(capabilities(self.settings)))), title='Built-in tools', border_style='#414b60'))
            self.console.print(Text(f'  Commands: {self.settings.execution_backend} · browser/desktop actions require a configured connector'))
            self.engine.mcp_tools = await self.engine.runtime.mcp_catalog()
            self.console.print_json(json.dumps(self.engine.mcp_tools, default=str))
        elif name[1:] in self.skill_registry.discover():
            self.skill_registry.load(name[1:], explicit=True)
            self.busy = True
            self.job = asyncio.create_task(self.work(message))
        else:
            self.emit("warning", "Unknown command. Use /help or /skills.")

    async def configure_key(self, jev: bool):
        from .generation import endpoint, save_key
        if not jev and self.settings.provider == 'codex':
            self.console.print('Codex uses OAuth. Run kestrel auth login from your shell.')
            return
        label = 'Jev' if jev else f'{self.settings.provider} ({endpoint(self.settings)})'
        self.console.print(Text(f'  {label} API key · hidden input · Enter skips'))
        # Explicit output avoids prompt_toolkit's TERM=dumb shortcut, which echoes
        # buffer changes without applying the password processor.
        prompt = PromptSession(history=DummyHistory(), output=self.prompt.output)
        try:
            key = (await prompt.prompt_async('  API key: ', is_password=True)).strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not key:
            return
        if any(char.isspace() for char in key) or (jev and not re.fullmatch(r'apikey_[A-Za-z0-9_]+', key)):
            raise ValueError('Invalid API key format.')
        if jev:
            home().mkdir(parents=True, exist_ok=True, mode=0o700)
            atomic_write(home() / 'secrets.env', f'TYPESAFE_API_KEY={key}\n')
            os.environ['TYPESAFE_API_KEY'] = key
            await self.engine.judge.close()
            self.engine.judge.client = None
        else:
            save_key(self.settings, key)
            # Explicit interactive replacement wins over an inherited environment value.
            os.environ.pop(self.settings.provider_api_key_env, None)
        self.emit('done', f'{"Jev" if jev else "Provider"} key saved privately. No API request was made.')

    async def ensure_keys(self):
        from .generation import api_key
        load_secrets()
        if self.settings.provider != "codex" and not api_key(self.settings):
            await self.configure_key(False)
        if self.settings.agent_mode == "jev" and not os.environ.get("TYPESAFE_API_KEY"):
            await self.configure_key(True)

    async def configure_provider(self, name: str = ""):
        from .generation import endpoint
        self.console.print(Text('  Providers: ' + ', '.join(PRESETS)))
        prompt = PromptSession(history=DummyHistory())
        try:
            provider = name or (await prompt.prompt_async('  Provider (Enter cancels): ')).strip()
            if not provider:
                return
            candidate = select(self.settings, provider)
            if candidate.provider != 'codex':
                base = (await prompt.prompt_async(f'  Base URL [{endpoint(candidate)}]: ')).strip()
                if base:
                    candidate.provider_base_url = base
                endpoint(candidate)
                candidate.model = (await prompt.prompt_async('  Model ID: ')).strip()
                if not candidate.model:
                    raise ValueError('A model ID is required for this provider.')
            await self.engine.close()
            candidate.save()
            self.settings = candidate
            self.engine = Engine(candidate, self.workspace, self.store, self.sid, self.emit, self.confirm)
            self.emit('done', f'Provider set to {provider_label(candidate)}.')
            await self.ensure_keys()
        except (EOFError, KeyboardInterrupt):
            return
