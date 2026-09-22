import asyncio
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from prompt_toolkit import PromptSession
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console

from kestrel_agent.config import Settings
from kestrel_agent import ui


def terminal_with_pipe(tmp_path, monkeypatch, pipe, run):
    engine = SimpleNamespace(run=run, close=AsyncMock())
    monkeypatch.setattr(ui, 'Engine', lambda *a: engine)
    monkeypatch.setattr(ui, 'PromptSession', lambda **kw: PromptSession(input=pipe, output=DummyOutput(), **kw))
    terminal = ui.Terminal(Settings(), tmp_path, None, 'test')
    terminal.console = Console(file=io.StringIO())
    terminal.ensure_keys = AsyncMock()
    return terminal, engine


async def prompt_ready(terminal):
    async def wait():
        while not terminal.prompt.app.is_running:
            await asyncio.sleep(0)
    await asyncio.wait_for(wait(), 3)


@pytest.mark.asyncio
async def test_control_c_at_idle_prompt_exits_and_closes_engine(tmp_path, monkeypatch):
    with create_pipe_input() as pipe:
        terminal, engine = terminal_with_pipe(tmp_path, monkeypatch, pipe, AsyncMock())
        chat = asyncio.create_task(terminal.chat())
        try:
            await prompt_ready(terminal)
            assert 'Ctrl+C quit' in str(terminal.toolbar())
            pipe.send_text('\x03')
            await asyncio.wait_for(chat, 3)
            engine.close.assert_awaited_once()
            engine.run.assert_not_called()
        finally:
            chat.cancel()
            await asyncio.gather(chat, return_exceptions=True)


@pytest.mark.asyncio
async def test_control_c_stops_active_task_then_next_press_quits(tmp_path, monkeypatch):
    started = asyncio.Event()
    async def run(message):
        started.set()
        await asyncio.Event().wait()
    with create_pipe_input() as pipe:
        terminal, engine = terminal_with_pipe(tmp_path, monkeypatch, pipe, AsyncMock(side_effect=run))
        chat = asyncio.create_task(terminal.chat())
        try:
            await prompt_ready(terminal)
            pipe.send_text('hello\r')
            await asyncio.wait_for(started.wait(), 3)
            assert 'Ctrl+C stop' in str(terminal.toolbar())
            pipe.send_text('\x03')
            await asyncio.wait_for(asyncio.shield(terminal.job), 3)
            assert not chat.done() and not terminal.busy
            engine.close.assert_not_called()
            await prompt_ready(terminal)
            pipe.send_text('\x03')
            await asyncio.wait_for(chat, 3)
            engine.close.assert_awaited_once()
        finally:
            chat.cancel()
            if terminal.job:
                terminal.job.cancel()
                await asyncio.gather(terminal.job, return_exceptions=True)
            await asyncio.gather(chat, return_exceptions=True)
