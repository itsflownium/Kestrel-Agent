"""An isolated browser with observed targets; no model-supplied JS or selectors."""
from __future__ import annotations

import asyncio
import uuid
from urllib.parse import urlsplit
from typing import Any

SIGNATURE = '''el => ({tag: el.tagName.toLowerCase(), role: el.getAttribute('role'),
    type: el.getAttribute('type'), label: (el.getAttribute('aria-label') ||
    Array.from(el.labels || []).map(x => x.innerText).join(' ') || el.innerText ||
    el.getAttribute('placeholder') || el.getAttribute('name') || '').slice(0,500),
    href: el.getAttribute('href'), disabled: !!el.disabled, readonly: !!el.readOnly})'''


class BrowserAdapter:
    def __init__(self, *, headless=False):
        self.headless = headless
        self.driver = self.browser = self.context = None
        self.pages, self.observations = {}, {}
        self.lock = asyncio.Lock()

    async def start(self):
        if self.context is not None:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError as error:
            raise RuntimeError('Install Kestrel with the browser extra and run playwright install chromium.') from error
        self.driver = await async_playwright().start()
        try:
            self.browser = await self.driver.chromium.launch(headless=self.headless)
            self.context = await self.browser.new_context(accept_downloads=False, service_workers='block')
            self.context.set_default_timeout(10000)
            async def route(request):
                if urlsplit(request.request.url).scheme in {'http', 'https'}:
                    await request.continue_()
                else:
                    await request.abort()
            await self.context.route('**/*', route)
            self.context.on('page', self.register)
        except BaseException:
            await self.close()
            raise

    def register(self, page):
        if page in self.pages.values():
            return
        key = uuid.uuid4().hex[:10]
        self.pages[key] = page
        page.on('framenavigated', lambda frame: self.observations.pop(key, None) if frame == page.main_frame else None)
        page.on('close', lambda: self.observations.pop(key, None))
        # Dialogs cannot silently block later operations; report via subsequent state.
        page.on('dialog', lambda dialog: dialog.dismiss())

    def page(self, tab):
        page = self.pages.get(tab)
        if page is None or page.is_closed():
            raise ValueError('Unknown or closed tab. List tabs and choose an observed ID.')
        return page

    async def tabs(self):
        async with self.lock:
            return [{'tab': key, 'url': page.url, 'title': await page.title()} for key, page in self.pages.items() if not page.is_closed()]

    async def open(self, url):
        parsed = urlsplit(url)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Open an HTTP(S) URL without embedded credentials.')
        async with self.lock:
            await self.start()
            page = await self.context.new_page()
            self.register(page)
            tab = next(key for key, value in self.pages.items() if value == page)
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            return await self._snapshot(tab)

    async def snapshot(self, tab):
        async with self.lock:
            return await self._snapshot(tab)

    async def _snapshot(self, tab):
        page = self.page(tab)
        old = self.observations.pop(tab, None)
        if old:
            for handle, _ in old['targets'].values():
                await handle.dispose()
        targets, visible = {}, []
        handles = await page.query_selector_all('a,button,input,textarea,select,[role="button"],[role="link"],[contenteditable="true"]')
        for index, handle in enumerate(handles):
            if len(visible) >= 150:
                await handle.dispose()
                continue
            if not await handle.is_visible():
                await handle.dispose()
                continue
            signature = await handle.evaluate(SIGNATURE)
            key = 'e' + str(index + 1)
            targets[key] = (handle, signature)
            visible.append({'target': key, **signature})
        token = uuid.uuid4().hex
        self.observations[tab] = {'token': token, 'url': page.url, 'targets': targets}
        text = await page.locator('body').inner_text(timeout=10000)
        return {'tab': tab, 'observation': token, 'url': page.url, 'title': await page.title(),
                'text': text[:16000], 'text_truncated': len(text) > 16000, 'targets': visible,
                'targets_may_be_truncated': len(handles) > 150,
                'scope': 'Main-frame visible DOM only. No iframe, canvas, or desktop visual interpretation.'}

    async def act(self, tab, observation, target, operation, value=''):
        if operation not in {'click', 'fill', 'select', 'press'}:
            raise ValueError('Unsupported browser operation.')
        if len(value) > 16000:
            raise ValueError('Browser input exceeds 16000 characters.')
        if operation == 'press' and value not in {'Enter', 'Tab', 'Escape', 'ArrowDown', 'ArrowUp', 'Space'}:
            raise ValueError('Unsupported key.')
        async with self.lock:
            page = self.page(tab)
            snapshot = self.observations.get(tab)
            if not snapshot or snapshot['token'] != observation or snapshot['url'] != page.url:
                raise ValueError('Stale observation. Inspect the current page again.')
            entry = snapshot['targets'].get(target)
            if entry is None:
                raise ValueError('Target was not in this observation.')
            handle, signature = entry
            if not await handle.evaluate('el => el.isConnected') or not await handle.is_visible() or await handle.evaluate(SIGNATURE) != signature:
                raise ValueError('Target changed. Inspect the current page again.')
            # Consume the observation before dispatch; ambiguous failures must not replay it.
            self.observations.pop(tab, None)
            try:
                if operation == 'click':
                    await handle.click(timeout=10000)
                elif operation == 'fill':
                    await handle.fill(value, timeout=10000)
                elif operation == 'select':
                    await handle.select_option(value, timeout=10000)
                else:
                    await handle.press(value, timeout=10000)
            finally:
                for old_handle, _ in snapshot['targets'].values():
                    await old_handle.dispose()
            return await self._snapshot(tab)

    async def close(self):
        try:
            if self.browser:
                await self.browser.close()
        finally:
            if self.driver:
                await self.driver.stop()
            self.driver = self.browser = self.context = None
            self.pages.clear()
            self.observations.clear()


def create_browser_server(port=8931, headless=False):
    from contextlib import asynccontextmanager
    from mcp.server.fastmcp import FastMCP
    adapter = BrowserAdapter(headless=headless)
    @asynccontextmanager
    async def lifespan(server):
        try:
            yield {}
        finally:
            await adapter.close()
    server = FastMCP('Kestrel Browser', host='127.0.0.1', port=port, lifespan=lifespan, json_response=True)
    @server.tool()
    async def browser_open(url: str) -> dict[str, Any]:
        """Open an HTTP(S) page in Kestrel's isolated browser; return observed targets."""
        return await adapter.open(url)
    @server.tool()
    async def browser_tabs() -> list[dict]:
        """List this browser's open tabs; does not access the user's other browsers."""
        return await adapter.tabs()
    @server.tool()
    async def browser_snapshot(tab: str) -> dict[str, Any]:
        """Read current main-frame text and targets. Old observation IDs become invalid."""
        return await adapter.snapshot(tab)
    @server.tool()
    async def browser_act(tab: str, observation: str, target: str, operation: str, value: str = '') -> dict[str, Any]:
        """Click/fill/select/press an observed target, then inspect the resulting state. Stale targets fail."""
        return await adapter.act(tab, observation, target, operation, value)
    return server


def serve_browser(port=8931, headless=False):
    create_browser_server(port, headless).run(transport='streamable-http')
