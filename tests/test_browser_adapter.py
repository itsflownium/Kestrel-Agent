import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip('playwright', reason='Install the browser extra for real browser tests')
from kestrel_agent.browser import BrowserAdapter

PAGE = b'''<!doctype html><title>Disposable browser fixture</title>
<label for="name">Name</label><input id="name">
<button id="save" onclick="document.querySelector('#result').textContent='Saved: '+document.querySelector('#name').value">Save</button>
<p id="result">Not saved</p>'''


@pytest.mark.asyncio
async def test_browser_observe_fill_click_verify_and_stale_rejection():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(PAGE)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    browser = BrowserAdapter(headless=True)
    try:
        initial = await browser.open(f'http://127.0.0.1:{server.server_port}/')
        assert initial['title'] == 'Disposable browser fixture'
        initial, image = await browser.screenshot(initial['tab'])
        assert image.width > 0 and image.height > 0 and image.mime == 'image/png'
        field = next(t['target'] for t in initial['targets'] if t['label'] == 'Name')
        filled = await browser.act(initial['tab'], initial['observation'], field, 'fill', 'Kestrel fixture')
        with pytest.raises(ValueError, match='Stale'):
            await browser.act(initial['tab'], initial['observation'], field, 'fill', 'Must not happen')
        save = next(t['target'] for t in filled['targets'] if t['label'] == 'Save')
        saved = await browser.act(filled['tab'], filled['observation'], save, 'click')
        assert 'Saved: Kestrel fixture' in saved['text']
        assert len(await browser.tabs()) == 1
        save = next(t['target'] for t in saved['targets'] if t['label'] == 'Save')
        # Mutation is test setup, never a model-exposed JS tool.
        await browser.page(saved['tab']).evaluate("document.querySelector('#save').textContent='Delete'")
        with pytest.raises(ValueError, match='Target changed'):
            await browser.act(saved['tab'], saved['observation'], save, 'click')
        with pytest.raises(ValueError, match='HTTP'):
            await browser.open('file:///etc/passwd')
        with pytest.raises(ValueError, match='Unsupported key'):
            await browser.act(saved['tab'], saved['observation'], save, 'press', 'Control+L')
    finally:
        await browser.close()
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=2)
    assert browser.context is None


@pytest.mark.asyncio
async def test_browser_tools_work_through_real_mcp_transport():
    import json
    import socket
    import uvicorn
    from kestrel_agent.browser import create_browser_server
    from kestrel_agent.config import Settings
    from kestrel_agent.connections import Connection, ConnectionPool
    from starlette.applications import Starlette
    from starlette.responses import HTMLResponse
    from starlette.routing import Route, Mount
    socket_ = socket.socket()
    socket_.bind(('127.0.0.1', 0))
    port = socket_.getsockname()[1]
    socket_.listen()
    browser_server = create_browser_server(port, headless=True)
    mcp_app = browser_server.streamable_http_app()
    # MCP's lifespan also owns browser cleanup; fixture page shares the listener.
    canvas = '''<body style="margin:0"><canvas id="c" width="400" height="240"></canvas><p id="result"></p><script>
    const c=document.getElementById('c'),g=c.getContext('2d');g.fillStyle='green';g.fillRect(80,60,140,60);
    c.onclick=e=>document.getElementById('result').textContent=(e.offsetX>80&&e.offsetX<220&&e.offsetY>60&&e.offsetY<120)?'Canvas clicked':'Wrong position';
    </script></body>'''
    app = Starlette(routes=[Route('/fixture', lambda request: HTMLResponse(PAGE.decode())), Route('/canvas', lambda request: HTMLResponse(canvas)), Mount('/', app=mcp_app)], lifespan=mcp_app.router.lifespan_context)
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    task = asyncio.create_task(server.serve(sockets=[socket_]))
    pool = ConnectionPool(Settings(provider='anthropic', mcp_connections={'browser': Connection(url=f'http://127.0.0.1:{port}/mcp')}))
    try:
        async with asyncio.timeout(5):
            while not server.started:
                await asyncio.sleep(.01)
        catalog = await pool.catalog()
        assert {t['name'] for t in catalog[0]['tools']} == {'browser_open','browser_tabs','browser_snapshot','browser_act','browser_screenshot','browser_click_at'}
        async def call(tool, arguments):
            result = await pool.call('browser', tool, arguments)
            assert not result.get('isError'), result
            assert isinstance(result.get('structuredContent'), dict)
            return result['structuredContent']
        state = await call('browser_open', {'url': f'http://127.0.0.1:{port}/fixture'})
        screenshot = await pool.call('browser', 'browser_screenshot', {'tab':state['tab']})
        assert not screenshot.get('isError'), screenshot
        state = screenshot['structuredContent']
        assert state == json.loads(screenshot['content'][0]['text'])
        pixels = next(block for block in screenshot['content'] if block['type'] == 'image')
        assert 'data' not in pixels
        assert pool.images.get(pixels['image_id']).width > 0
        assert screenshot['image_id'] == pixels['image_id']
        assert screenshot['image_refs'][0]['content_index'] == 1
        field = next(t['target'] for t in state['targets'] if t['label'] == 'Name')
        state = await call('browser_act', {'tab':state['tab'], 'observation':state['observation'], 'target':field, 'operation':'fill', 'value':'Through MCP'})
        save = next(t['target'] for t in state['targets'] if t['label'] == 'Save')
        state = await call('browser_act', {'tab':state['tab'], 'observation':state['observation'], 'target':save, 'operation':'click'})
        assert 'Saved: Through MCP' in state['text']
        state = await call('browser_open', {'url':f'http://127.0.0.1:{port}/canvas'})
        screenshot = await pool.call('browser','browser_screenshot',{'tab':state['tab']})
        state = screenshot['structuredContent']
        assert state == json.loads(screenshot['content'][0]['text'])
        assert not state['targets']
        state = await call('browser_click_at', {'tab':state['tab'],'observation':state['observation'],'x':150,'y':90})
        assert 'Canvas clicked' in state['text']
    finally:
        await pool.close()
        server.should_exit = True
        await asyncio.wait_for(task, 10)
        socket_.close()
