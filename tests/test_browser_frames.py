import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip('playwright')
from kestrel_agent.browser import BrowserAdapter


@pytest.mark.asyncio
async def test_nested_cross_origin_frame_actions_and_invalidation():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/':
                body = f'<body>Main page<iframe src="http://localhost:{self.server.server_port}/nested"></iframe></body>'
            elif self.path == '/nested':
                body = '<body>Embedded page<iframe src="/form"></iframe></body>'
            else:
                body = '<body><label for="name">Record name</label><input id="name"><button onclick="document.querySelector(\'#result\').textContent=\'Saved: \'+document.querySelector(\'#name\').value">Save</button><p id="result">Not saved</p></body>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(body.encode())
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    browser = BrowserAdapter(headless=True)
    try:
        state = await browser.open(f'http://127.0.0.1:{server.server_port}/')
        tab = state['tab']
        page = browser.page(tab)
        assert len(state['frames']) == 3
        field = next(t for t in state['targets'] if t['label'] == 'Record name')
        assert field['frame'] != 'f0'
        filled = await browser.act(tab, state['observation'], field['target'], 'fill', 'Frame record')
        button = next(t for t in filled['targets'] if t['label'] == 'Save')
        saved = await browser.act(tab, filled['observation'], button['target'], 'click')
        assert 'Saved: Frame record' in saved['text']
        frame = next(f for f in page.frames if f.url.endswith('/form'))
        await frame.goto(f'http://localhost:{server.server_port}/replacement')
        with pytest.raises(ValueError, match='Stale'):
            await browser.act(tab, saved['observation'], button['target'], 'click')
        current = await browser.snapshot(tab)
        field = next(t for t in current['targets'] if t['label'] == 'Record name')
        # A hidden ancestor must suppress a still-visible descendant's controls.
        await page.locator('iframe').evaluate("el => el.style.display='none'")
        with pytest.raises(ValueError, match='Target changed'):
            await browser.act(tab, current['observation'], field['target'], 'fill', 'Wrong')
        hidden = await browser.snapshot(tab)
        assert hidden['targets'] == []
        assert 'Record name' not in hidden['text']
        await page.locator('iframe').evaluate("el => el.remove()")
        with pytest.raises(ValueError, match='Stale'):
            await browser.act(tab, hidden['observation'], 'e1', 'click')
    finally:
        await browser.close()
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.asyncio
async def test_frame_and_target_limits_are_reported():
    browser = BrowserAdapter(headless=True)
    try:
        await browser.start()
        page = await browser.context.new_page()
        await page.set_content('<body>' + '<button>Item</button>' * 151 + '<iframe srcdoc="<body>Frame</body>"></iframe>' * 21 + '</body>')
        tab = next(key for key, value in browser.pages.items() if value == page)
        state = await browser.snapshot(tab)
        assert len(state['targets']) == 150
        assert state['targets_may_be_truncated'] is True
        assert len(state['frames']) == 20
        assert state['frames_truncated'] is True
        assert len(state['text']) <= 16000
    finally:
        await browser.close()


@pytest.mark.asyncio
async def test_observation_retries_are_bounded_and_only_for_frame_changes():
    from unittest.mock import AsyncMock
    from kestrel_agent.browser import FrameObservationChanged
    browser = BrowserAdapter(headless=True)
    browser._snapshot = AsyncMock(side_effect=[FrameObservationChanged('changed'), {'observation': 'fresh'}])
    assert await browser._observe('tab') == {'observation': 'fresh'}
    assert browser._snapshot.await_count == 2
    browser._snapshot = AsyncMock(side_effect=FrameObservationChanged('changed'))
    with pytest.raises(FrameObservationChanged):
        await browser._observe('tab')
    assert browser._snapshot.await_count == 3
    browser._snapshot = AsyncMock(side_effect=ValueError('unrelated failure'))
    with pytest.raises(ValueError, match='unrelated'):
        await browser._observe('tab')
    assert browser._snapshot.await_count == 1
