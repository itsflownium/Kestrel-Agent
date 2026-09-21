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


class FrameObservationChanged(ValueError):
    pass


class BrowserAdapter:
    def __init__(self, *, headless=False):
        self.headless = headless
        self.driver = self.browser = self.context = None
        self.pages, self.observations = {}, {}
        self.revisions = {}
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
        self.revisions[key] = 0
        def invalidate(frame):
            self.revisions[key] += 1
            if key in self.observations:
                self.observations[key]['token'] = None
        for event in ('frameattached', 'framenavigated', 'framedetached'):
            page.on(event, invalidate)
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
            return await self._observe(tab)

    async def snapshot(self, tab):
        async with self.lock:
            return await self._observe(tab)

    async def screenshot(self, tab):
        async with self.lock:
            state = await self._observe(tab)
            data = await self.page(tab).screenshot(type='png', full_page=False, timeout=10000)
            from .vision import validate_image
            image = validate_image(data, 'image/png')
            return state, image

    async def _observe(self, tab):
        # Read-only retries handle ordinary frame loading without repeating effects.
        for attempt in range(3):
            try:
                return await self._snapshot(tab)
            except FrameObservationChanged:
                if attempt == 2:
                    raise

    async def _snapshot(self, tab):
        page = self.page(tab)
        old = self.observations.pop(tab, None)
        if old:
            await self._dispose(old['targets'])
        revision = self.revisions[tab]
        targets, visible, frames, parts = {}, [], [], []
        truncated, text_truncated, text_size = False, False, 0
        candidates = list(page.frames)
        try:
            async with asyncio.timeout(20):
                for index, frame in enumerate(candidates[:20]):
                    if not await self._frame_visible(frame):
                        continue
                    fid = 'f' + str(index)
                    frames.append({'frame': fid, 'url': frame.url, 'name': frame.name})
                    text = await frame.locator('body').inner_text(timeout=2000)
                    part = ('' if frame == page.main_frame else f'\n[Frame {fid}: {frame.url}]\n') + text
                    remaining = max(0, 16000 - text_size)
                    parts.append(part[:remaining])
                    text_size += min(len(part), remaining)
                    text_truncated |= len(part) > remaining
                    handles = await frame.query_selector_all('a,button,input,textarea,select,[role="button"],[role="link"],[contenteditable="true"]')
                    try:
                        for handle in handles:
                            if len(visible) >= 150:
                                truncated = True
                                break
                            if not await handle.is_visible():
                                continue
                            signature = await handle.evaluate(SIGNATURE)
                            key = 'e' + str(len(visible) + 1)
                            targets[key] = (handle, signature, frame, frame.url)
                            visible.append({'target': key, 'frame': fid, **signature})
                    finally:
                        retained = {entry[0] for entry in targets.values()}
                        await asyncio.gather(*(h.dispose() for h in handles if h not in retained), return_exceptions=True)
                title = await page.title()
                if self.revisions[tab] != revision:
                    raise FrameObservationChanged('Page frames changed during observation. Inspect again.')
        except BaseException as error:
            await self._dispose(targets)
            if isinstance(error, Exception) and self.revisions.get(tab) != revision:
                raise FrameObservationChanged('Page frames changed during observation. Inspect again.') from error
            raise
        token = uuid.uuid4().hex
        self.observations[tab] = {'token': token, 'url': page.url, 'targets': targets}
        return {'tab': tab, 'observation': token, 'url': page.url, 'title': title,
                'text': ''.join(parts), 'text_truncated': text_truncated, 'targets': visible,
                'frames': frames, 'frames_truncated': len(candidates) > 20,
                'targets_may_be_truncated': truncated,
                'scope': 'Visible DOM in up to 20 frames, 150 targets total. No canvas or desktop actions.'}

    async def _dispose(self, targets):
        await asyncio.gather(*(entry[0].dispose() for entry in targets.values()), return_exceptions=True)

    async def _frame_visible(self, frame):
        while frame.parent_frame is not None:
            if frame.is_detached():
                return False
            element = await frame.frame_element()
            try:
                if not await element.is_visible():
                    return False
            finally:
                await element.dispose()
            frame = frame.parent_frame
        return not frame.is_detached()

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
            handle, signature, frame, frame_url = entry
            if frame.is_detached() or frame.url != frame_url or not await self._frame_visible(frame) or not await handle.evaluate('el => el.isConnected') or not await handle.is_visible() or await handle.evaluate(SIGNATURE) != signature:
                raise ValueError('Target changed. Inspect the current page again.')
            if snapshot['token'] != observation:
                raise ValueError('Stale observation. Inspect the current page again.')
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
                await self._dispose(snapshot['targets'])
            return await self._observe(tab)

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
            self.revisions.clear()


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
        """Read current text and targets across visible frames. Old observation IDs become invalid."""
        return await adapter.snapshot(tab)
    @server.tool()
    async def browser_screenshot(tab: str):
        """Capture this isolated tab's viewport and fresh DOM state. Inspect returned image_id with inspect_image; use DOM targets for actions."""
        import json
        from mcp.types import CallToolResult, ImageContent, TextContent
        state, image = await adapter.screenshot(tab)
        state['image_scope'] = 'Viewport pixels and DOM captured sequentially. Refresh after UI changes; screenshot coordinates are not desktop coordinates.'
        return CallToolResult(content=[TextContent(type='text', text=json.dumps(state)),
            ImageContent(type='image', mimeType=image.mime, data=image.encoded)])
    @server.tool()
    async def browser_act(tab: str, observation: str, target: str, operation: str, value: str = '') -> dict[str, Any]:
        """Click/fill/select/press an observed target, then inspect the resulting state. Stale targets fail."""
        return await adapter.act(tab, observation, target, operation, value)
    return server


def serve_browser(port=8931, headless=False):
    create_browser_server(port, headless).run(transport='streamable-http')
