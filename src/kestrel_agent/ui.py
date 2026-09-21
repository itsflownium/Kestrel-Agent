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

COMMANDS = ["/help", "/new", "/continue", "/sessions", "/resume", "/model", "/model jev-key", "/model provider-key", "/provider", "/permissions", "/config", "/tools", "/status", "/clear", "/exit"]
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
        details = f"  {self.settings.permission}  ·  Ctrl+C {interrupt_hint}" if width < 90 else f"  {self.settings.model or self.settings.provider} + Jev  ·  {self.settings.permission}  ·  /help  ·  Ctrl+C {interrupt_hint}"
        return [("class:status", f"  {status}  "), ("", details)]

    def input_prompt(self):
        width = max(12, min(self.console.size.width - 4, 88))
        label = "Permission · yes / no" if self.pending_approval is not None else ("Working · Ctrl+C to stop" if self.busy else "Message Kestrel")
        return [("class:input-border", "\n  " + "─" * width + "\n"),
                ("class:hint", f"  {label}\n"), ("class:prompt", "  ❯ ")]

    def welcome(self):
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
        info.add_row("Models", f"{self.settings.model or 'default'}  +  Jev")
        info.add_row("Access", self.settings.permission)
        self.console.print(Panel(info, title="[bold #8bd5ca]Your workspace[/]", title_align="left",
                                 subtitle=f"[dim]session {self.sid}[/dim]", subtitle_align="right",
                                 width=width, box=box.ROUNDED, border_style="#414b60", padding=(1, 2)))
        suggestions = Text.assemble(
            ("  Start anywhere\n", "bold #d8dee9"),
            ("  Explain a project   ·   Compare documents   ·   Research an idea\n\n", "#8993a7"),
            ("  /model", "#8bd5ca"), (" choose model    ", "#8993a7"),
            ("/permissions", "#8bd5ca"), (" access    ", "#8993a7"),
            ("/help", "#8bd5ca"), (" all commands", "#8993a7"))
        self.console.print(suggestions)

    def emit(self, kind: str, text: str):
        if kind == "output":
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
        self.emit("connecting", "Jev · checking the quickest supported route")
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
                ("/new", "Start a fresh conversation"), ("/continue", "Continue interrupted work"),
                ("/sessions · /resume ID", "List or reopen conversations"), ("/model [ID]", "List/select model and configure Jev key"),
                ("/provider [NAME]", "Choose provider, endpoint, model, and keys"),
                ("/model jev-key · /model provider-key", "Enter or replace keys privately"),
                ("/permissions [read-only|workspace|full]", "View or change access profile"),
                ("/config", "Inspect settings; use kestrel config set KEY VALUE to edit"),
                ("/tools", "Discover connected MCP tools"), ("/status", "Show checkpoint and usage"),
                ("/clear · /exit", "Clear the screen or leave"), ("Ctrl+C · Alt+Enter", "Stop a task or quit when idle · insert newline")]:
                table.add_row(command, meaning)
            self.console.print(table)
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
        elif name == "/provider":
            await self.configure_provider(argument)
        elif name == "/model":
            if argument in {"jev-key", "provider-key"}:
                await self.configure_key(argument == "jev-key")
                return
            load_secrets()
            self.console.print(Text(f"  Provider: {provider_label(self.settings)} · Model: {self.settings.model or 'default'} · Jev key: {'configured' if os.environ.get('TYPESAFE_API_KEY') else 'missing'}"))
            self.console.print("  /model jev-key replaces the Jev key; /model provider-key sets the generation API key.", style="dim")
            if not os.environ.get('TYPESAFE_API_KEY'):
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
            self.engine.mcp_tools = await self.engine.runtime.mcp_catalog()
            self.console.print_json(json.dumps(self.engine.mcp_tools, default=str))
        else:
            self.emit("warning", "Unknown command. Use /help.")

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
        if not os.environ.get("TYPESAFE_API_KEY"):
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
