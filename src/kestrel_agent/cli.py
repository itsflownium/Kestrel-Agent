from __future__ import annotations

import asyncio
import json
import os
import time
import webbrowser
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from . import __version__
from .config import Settings, atomic_write, check_storage, home, load_secrets, redact
from .providers import Runtime
from .store import Store

app = typer.Typer(help="Kestrel · a general-purpose terminal agent", no_args_is_help=False, pretty_exceptions_enable=False)
auth_app = typer.Typer(help="Manage Codex OAuth, provider API keys, and your Jev key.")
config_app = typer.Typer(help="Configure access, models, budgets, and network settings.")
skills_app = typer.Typer(help="Discover, inspect, install, and version portable skills.")
workflows_app = typer.Typer(help="Review and manage reusable procedures.")
app.add_typer(auth_app, name="auth")
app.add_typer(config_app, name="config")
app.add_typer(workflows_app, name="workflows")
app.add_typer(skills_app, name="skills")
console = Console(highlight=False)


def emit(kind: str, message: str):
    console.print(Text(f"  {kind} · {redact(message)}", style="dim"))


def launch(workspace: Path, session: str | None = None):
    from .ui import Terminal
    load_secrets()
    settings = Settings.load()
    store = Store(settings)
    try:
        if session:
            workspace = Path(store.session(session)["workspace"])
        else:
            session = store.create(workspace.resolve())
        asyncio.run(Terminal(settings, workspace.resolve(), store, session).chat())
    except KeyboardInterrupt:
        console.print("\nStopped.", style="dim")
    except Exception as error:
        console.print(Text(redact(str(error)), style="red"))
        raise typer.Exit(1)
    finally:
        store.close()


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context, workspace: Path = typer.Option(Path.cwd(), "--workspace", "-C", exists=True, file_okay=False), version: bool = typer.Option(False, "--version")):
    if version:
        console.print(f"Kestrel {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        launch(workspace)


@app.command()
def chat(workspace: Path = typer.Option(Path.cwd(), "--workspace", "-C", exists=True, file_okay=False)):
    """Open the interactive terminal interface."""
    launch(workspace)


@app.command()
def resume(session: str):
    """Reopen a saved conversation; /continue resumes interrupted work."""
    launch(Path.cwd(), session)


@app.command()
def sessions():
    """List saved sessions without contacting a model."""
    store = Store(Settings.load())
    try:
        table = Table("Session", "Created", "Workspace", "Title", box=None)
        for record in store.sessions():
            table.add_row(record["id"], time.strftime("%b %d %H:%M", time.localtime(record["created"])), record["workspace"], record["title"])
        console.print(table)
    finally:
        store.close()


@app.command("setup")
def setup_agent():
    """Configure models, keys, Jev mode, access, and command execution."""
    from .setup import configure
    async def ask(label, default):
        return typer.prompt(label, default=default).strip()
    try:
        candidate = asyncio.run(configure(Settings.load(), ask, lambda value: console.print(Text(value))))
    except (ValueError, KeyboardInterrupt, EOFError) as error:
        console.print(Text(f"Setup cancelled; settings unchanged. {error}"))
        raise typer.Exit(1)
    candidate.save()
    prompt_provider_key(candidate)
    prompt_jev_if_missing()
    console.print(Text(f"Saved: {candidate.model or 'default'} · {candidate.agent_mode} · {candidate.execution_backend}"))
    if candidate.provider == "codex":
        console.print("Codex authentication: kestrel auth login")
    if candidate.execution_backend == "docker":
        console.print("Docker must be running with the selected image installed. Setup does not start Docker or pull images.")


@app.command()
def doctor(online: bool = typer.Option(False, "--online", help="Explicitly contact Codex account and Jev model-list endpoints; no generation.")):
    """Inspect setup. Network checks run only with --online."""
    load_secrets()
    settings = Settings.load()
    used = check_storage(settings)
    console.print(f"Kestrel {__version__}\nManaged storage: {used / 1_000_000:.1f} MB / {settings.max_storage_bytes / 1_000_000:.0f} MB")
    console.print(f"Data: {home()}\nAccess: {settings.permission}\nJev key: {'configured' if os.environ.get('TYPESAFE_API_KEY') else 'missing'}")
    console.print(Text(f"Mode: {settings.agent_mode}\nExecution: {settings.execution_backend}"))
    if settings.execution_backend == "docker":
        import shutil
        console.print(Text(f"Docker CLI: {shutil.which('docker') or 'missing'}\nImage: {settings.docker_image} (availability not checked)"))
    if online:
        async def check():
            runtime = Runtime(settings, Path.cwd(), emit)
            try:
                if settings.provider == "codex":
                    account = await runtime.account()
                    console.print("Codex: signed in" if account.get("account") else "Codex: run kestrel auth login")
                else:
                    models = await runtime.generator.models()
                    console.print(Text(f"{settings.provider}: model listing succeeded ({len(models)} models)"))
            finally:
                await runtime.close()
            if settings.agent_mode != "jev":
                return
            from typesafe_sdk import AsyncTypeSafeClient
            async with AsyncTypeSafeClient(timeout=20) as client:
                await client.models.list()
                console.print("Jev: authenticated")
        asyncio.run(check())


@auth_app.command("login")
def login():
    """Sign in using Codex-managed ChatGPT OAuth."""
    async def run():
        runtime = Runtime(Settings.load(), Path.cwd(), emit)
        try:
            await runtime.start()
            if (await runtime.account()).get("account"):
                console.print("Codex is already signed in.")
                return
            handle = await runtime.codex.login_chatgpt()
            console.print(Text("Open this URL to sign in:\n" + handle.auth_url))
            webbrowser.open(handle.auth_url)
            result = await handle.wait()
            if not result.success:
                raise RuntimeError(result.error or "Sign-in did not complete.")
            console.print("Codex sign-in complete.", style="green")
        finally:
            await runtime.close()
    asyncio.run(run())
    prompt_jev_if_missing()


@auth_app.command("jev")
def configure_jev():
    """Save your Jev key locally using hidden input."""
    key = typer.prompt("Jev API key", hide_input=True).strip()
    if not key.startswith("apikey_") or any(c.isspace() for c in key):
        raise typer.BadParameter("Expected a Jev apikey_ value without whitespace.")
    home().mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_write(home() / "secrets.env", f"TYPESAFE_API_KEY={key}\n")
    console.print("Jev key saved locally with owner-only file permissions. It was not tested.")


def prompt_jev_if_missing():
    if Settings.load().agent_mode != "jev":
        return
    load_secrets()
    if os.environ.get("TYPESAFE_API_KEY"):
        return
    key = typer.prompt("Jev API key (Enter skips)", hide_input=True, default="", show_default=False).strip()
    if not key:
        return
    import re
    if not re.fullmatch(r"apikey_[A-Za-z0-9_]+", key):
        raise typer.BadParameter("Expected a Jev apikey_ value without whitespace.")
    home().mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_write(home() / "secrets.env", f"TYPESAFE_API_KEY={key}\n")
    os.environ["TYPESAFE_API_KEY"] = key
    console.print("Jev key saved privately. No API request was made.")


def prompt_provider_key(settings: Settings, *, replace: bool = False):
    from .generation import api_key, endpoint, save_key
    from .provider_presets import label
    if settings.provider == "codex":
        console.print("Codex uses OAuth: run kestrel auth login.")
        return
    if not replace and api_key(settings):
        return
    console.print(Text(f"Provider: {label(settings)}\nEndpoint: {endpoint(settings)}"))
    key = typer.prompt("Provider API key (Enter skips)", hide_input=True, default="", show_default=False).strip()
    if not key:
        return
    if any(char.isspace() for char in key):
        raise typer.BadParameter("Expected an API key without whitespace.")
    save_key(settings, key)
    console.print("Saved privately for this provider and endpoint. No API request was made.")


@app.command("mode")
def select_mode(mode: str | None = typer.Argument(None)):
    """Choose standard (one provider) or jev-assisted decisions."""
    settings = Settings.load()
    if mode is not None:
        if mode not in {"standard", "jev"}:
            raise typer.BadParameter("Choose standard or jev.")
        settings.agent_mode = mode
        settings.save()
        prompt_jev_if_missing()
    console.print(Text(f"Mode: {settings.agent_mode}. " + ("Decisions use your selected model; no Jev key needed." if settings.agent_mode == "standard" else "Decisions use Jev.")))


@app.command("providers")
def list_providers():
    """List named provider setups; model IDs are chosen by you."""
    from .provider_presets import PRESETS
    table = Table("Name", "Provider", "Default endpoint", box=None)
    for name, preset in PRESETS.items():
        table.add_row(name, preset.label, preset.base_url or "Codex-managed OAuth")
    console.print(table)


@app.command("provider")
def select_provider(name: str, model: str | None = typer.Option(None), base_url: str | None = typer.Option(None)):
    """Select a provider/model and enter missing provider and Jev keys privately."""
    from .provider_presets import select, label
    try:
        candidate = select(Settings.load(), name, base_url=base_url, model=model)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    if candidate.provider != "codex" and not candidate.model:
        candidate.model = typer.prompt("Model ID").strip()
        if not candidate.model:
            raise typer.BadParameter("A model ID is required.")
    candidate.save()
    console.print(Text(f"Selected {label(candidate)} / {candidate.model or 'default'}."))
    prompt_provider_key(candidate)
    prompt_jev_if_missing()


@auth_app.command("provider")
def configure_provider(name: str | None = typer.Argument(None), base_url: str | None = typer.Option(None)):
    """Save a named (or current) provider key, then ask for a missing Jev key."""
    from .provider_presets import select
    try:
        settings = select(Settings.load(), name, base_url=base_url) if name else Settings.load()
        if base_url and not name:
            settings.provider_base_url = base_url
        prompt_provider_key(settings, replace=True)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    prompt_jev_if_missing()


@auth_app.command("poolside")
def configure_poolside(base_url: str | None = typer.Option(None)):
    """Save a Poolside API key without changing the active model."""
    configure_provider("poolside", base_url)


@config_app.command("show")
def config_show():
    console.print_json(Settings.load().model_dump_json())


@config_app.command("set")
def config_set(key: str, value: str):
    """Set a configuration value. Lists and booleans use JSON syntax."""
    settings = Settings.load()
    if key not in Settings.model_fields:
        raise typer.BadParameter("Unknown setting. Run kestrel config show.")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = value
    try:
        setattr(settings, key, parsed)
    except Exception as error:
        raise typer.BadParameter(str(error)) from error
    settings.save()
    console.print(Text(f"Saved {key} = {parsed}"))


@workflows_app.command("list")
def workflows_list():
    store = Store(Settings.load())
    try:
        for row in store.db.execute("SELECT id,name,active FROM workflows ORDER BY created DESC"):
            console.print(Text(f"{row['id']}  {'active' if row['active'] else 'candidate'}  {row['name']}"))
    finally:
        store.close()


@workflows_app.command("show")
def workflows_show(workflow: str):
    store = Store(Settings.load())
    try:
        row = store.db.execute("SELECT body FROM workflows WHERE id=?", (workflow,)).fetchone()
        if not row:
            raise typer.BadParameter("Unknown workflow ID.")
        console.print(Text(row[0]))
    finally:
        store.close()


@workflows_app.command("learn")
def workflows_learn(session: str):
    """Use one generation call to propose a reusable recipe from a completed session."""
    from .learning import learn_workflow
    settings = Settings.load()
    store = Store(settings)
    try:
        wid = asyncio.run(learn_workflow(store, settings, session, emit))
        console.print(f"Candidate saved: {wid}. Review with kestrel workflows show {wid}; activate after testing.")
    finally:
        store.close()


@workflows_app.command("activate")
def workflows_activate(workflow: str):
    """Activate a recipe you have reviewed and tested."""
    store = Store(Settings.load())
    try:
        store.activate(workflow)
        console.print(f"Activated {workflow}.")
    finally:
        store.close()


@workflows_app.command("disable")
def workflows_disable(workflow: str):
    store = Store(Settings.load())
    try:
        store.activate(workflow, False)
        console.print(f"Disabled {workflow}.")
    finally:
        store.close()


@app.command("eval")
def eval_command(dataset: Path = typer.Argument(..., exists=True, dir_okay=False), component: str = typer.Option("verify")):
    """Explicitly run labeled Jev evaluations. This makes billable Jev requests."""
    from .engine import GATE_PROMPT, VERIFY_PROMPT
    from .learning import evaluate, load_examples
    load_secrets()
    if component not in {"gate", "verify"}:
        raise typer.BadParameter("Choose gate or verify.")
    settings = Settings.load()
    store = Store(settings)
    try:
        template = store.template(component, GATE_PROMPT if component == "gate" else VERIFY_PROMPT)
        result = asyncio.run(evaluate(settings, load_examples(dataset), template, emit))
        console.print_json(json.dumps(result))
    finally:
        store.close()


@app.command("optimize")
def optimize_command(train: Path = typer.Option(..., exists=True, dir_okay=False), validation: Path = typer.Option(..., exists=True, dir_okay=False), test: Path = typer.Option(..., exists=True, dir_okay=False), component: str = typer.Option("verify"), budget: int = typer.Option(30, min=1, max=100)):
    """Explicitly run offline GEPA optimization. Uses Jev and the selected provider; no task tools."""
    from .learning import optimize
    load_secrets()
    path = optimize(Settings.load(), train, validation, component, budget, emit, test_path=test)
    console.print(Text(f"Candidate saved for review: {path}\nIndependent test results were saved; promotion checks the exact evaluated prompt."))


@app.command("promote-prompt")
def promote_prompt(candidate: Path = typer.Argument(..., exists=True, dir_okay=False)):
    """Activate a reviewed prompt candidate after your own held-out evaluation."""
    from .engine import GATE_PROMPT, VERIFY_PROMPT
    data = json.loads(candidate.read_text())
    if data.get("component") not in {"gate", "verify"} or not isinstance(data.get("instructions"), str):
        raise typer.BadParameter("Invalid prompt candidate.")
    store = Store(Settings.load())
    try:
        previous = store.template(data["component"], GATE_PROMPT if data["component"] == "gate" else VERIFY_PROMPT)
        from .learning_guards import promotion_report
        try:
            promotion_report(store.db, data, previous)
        except ValueError as error:
            raise typer.BadParameter(str(error)) from error
        backup = home() / "candidates" / f"{data['component']}-backup-{int(time.time())}.json"
        backup.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(backup, json.dumps({"component": data["component"], "instructions": previous, "kind": "backup", "requires_evaluation": True}))
        store.db.execute("INSERT OR REPLACE INTO templates VALUES(?,?,?)", (data["component"], data["instructions"], time.time()))
        store.db.commit()
        console.print(Text(f"Activated {data['component']}. Previous version: {backup}"))
    finally:
        store.close()


@skills_app.command("list")
def list_skills(query: str = typer.Argument("")):
    from .skill_registry import SkillRegistry
    console.print_json(json.dumps(SkillRegistry(Settings.load(), Path.cwd()).catalog(query)))


@skills_app.command("show")
def show_skill(name: str):
    from .skill_registry import SkillRegistry
    console.print_json(json.dumps(SkillRegistry(Settings.load(), Path.cwd()).load(name, explicit=True)))


@skills_app.command("check")
def check_skills():
    """Validate metadata and declared prerequisites; does not claim behavioral quality."""
    list_skills()


@skills_app.command("install")
def install_skill(source: Path = typer.Argument(..., exists=True, file_okay=False), replace: bool = typer.Option(False)):
    from .skill_registry import install
    try:
        console.print_json(json.dumps(install(source, replace=replace)))
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error


@skills_app.command("trust")
def trust_skills(workspace: Path = typer.Argument(Path.cwd(), exists=True, file_okay=False)):
    settings = Settings.load()
    path = str(workspace.resolve())
    if path not in settings.trusted_skill_workspaces:
        settings.trusted_skill_workspaces.append(path)
        settings.save()
    console.print(Text(f"Project skill discovery enabled for {path}. Skills do not grant tool permissions."))


@skills_app.command("versions")
def skill_versions(name: str):
    from .skill_registry import versions
    console.print_json(json.dumps(versions(name)))


@skills_app.command("rollback")
def rollback_skill(name: str, version: str):
    from .skill_registry import rollback
    console.print_json(json.dumps(rollback(name, version)))


if __name__ == "__main__":
    app()
