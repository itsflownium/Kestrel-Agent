import math
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip('playwright')
from kestrel_agent.browser import BrowserAdapter

HTML = '''<html><body style="margin:0"><canvas id="surface" width="400" height="240"></canvas>
<script>
window.clicks=0;
const canvas=document.getElementById('surface'), c=canvas.getContext('2d');
window.draw=(color='green')=>{c.fillStyle='white';c.fillRect(0,0,400,240);c.fillStyle=color;c.fillRect(80,60,140,60);c.fillStyle='white';c.font='20px sans-serif';c.fillText('Confirm',100,98);};draw();
canvas.onclick=e=>{if(e.offsetX>=80&&e.offsetX<220&&e.offsetY>=60&&e.offsetY<120){window.clicks++;draw('blue');}};
</script></body></html>'''


@pytest.fixture
def page_url():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type','text/html')
            self.end_headers()
            self.wfile.write(HTML.encode())
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.asyncio
async def test_canvas_click_uses_css_pixels_and_consumes_image_token(page_url):
    browser=BrowserAdapter(headless=True)
    try:
        initial=await browser.open(page_url)
        assert not initial['targets']
        with pytest.raises(ValueError,match='screenshot'):
            await browser.click_at(initial['tab'],initial['observation'],150,90)
        state,image=await browser.screenshot(initial['tab'])
        assert state['viewport']['width']==image.width
        assert state['viewport']['units']=='CSS pixels'
        after=await browser.click_at(state['tab'],state['observation'],150,90)
        assert await browser.page(state['tab']).evaluate('window.clicks')==1
        with pytest.raises(ValueError,match='Stale'):
            await browser.click_at(state['tab'],state['observation'],150,90)
        with pytest.raises(ValueError,match='screenshot'):
            await browser.click_at(after['tab'],after['observation'],150,90)
        assert await browser.page(state['tab']).evaluate('window.clicks')==1
    finally:
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['pixels','resize','scroll','navigate','hover'])
async def test_changed_viewport_never_dispatches_click(page_url,change):
    browser=BrowserAdapter(headless=True)
    try:
        state=await browser.open(page_url)
        page=browser.page(state['tab'])
        if change=='scroll':
            await page.evaluate("document.body.style.height='2000px'")
        state,_=await browser.screenshot(state['tab'])
        if change=='pixels': await page.evaluate("draw('red')")
        elif change=='resize': await page.set_viewport_size({'width':800,'height':600})
        elif change=='scroll': await page.evaluate('scrollTo(0,20)')
        elif change=='navigate': await page.goto(page_url+'?next')
        else: await page.evaluate("canvas.onmousemove=()=>draw('red')")
        with pytest.raises(ValueError,match='changed|Stale'):
            await browser.click_at(state['tab'],state['observation'],150,90)
        assert await page.evaluate('window.clicks')==0
        with pytest.raises(ValueError,match='Stale'):
            await browser.click_at(state['tab'],state['observation'],150,90)
    finally:
        await browser.close()


@pytest.mark.asyncio
async def test_invalid_coordinates_do_not_dispatch(page_url):
    browser=BrowserAdapter(headless=True)
    try:
        state=await browser.open(page_url)
        state,_=await browser.screenshot(state['tab'])
        for x,y in [(True,90),(-1,90),(math.nan,90),(math.inf,90),(150,-1),(state['viewport']['width'],90)]:
            with pytest.raises(ValueError):
                await browser.click_at(state['tab'],state['observation'],x,y)
        assert await browser.page(state['tab']).evaluate('window.clicks')==0
        await browser.click_at(state['tab'],state['observation'],150,90)
        assert await browser.page(state['tab']).evaluate('window.clicks')==1
    finally:
        await browser.close()


@pytest.mark.asyncio
async def test_high_dpi_image_coordinates_stay_in_css_pixels(page_url):
    browser=BrowserAdapter(headless=True)
    try:
        await browser.start()
        await browser.context.close()
        browser.context=await browser.browser.new_context(device_scale_factor=2,viewport={'width':800,'height':500})
        state=await browser.open(page_url)
        state,image=await browser.screenshot(state['tab'])
        assert (image.width,image.height)==(800,500)
        assert await browser.page(state['tab']).evaluate('devicePixelRatio')==2
        await browser.click_at(state['tab'],state['observation'],150,90)
        assert await browser.page(state['tab']).evaluate('window.clicks')==1
    finally:
        await browser.close()


@pytest.mark.asyncio
async def test_mouse_failure_consumes_token_and_releases_button(page_url,monkeypatch):
    from unittest.mock import AsyncMock
    browser=BrowserAdapter(headless=True)
    try:
        state=await browser.open(page_url)
        state,_=await browser.screenshot(state['tab'])
        page=browser.page(state['tab'])
        down=AsyncMock(side_effect=RuntimeError('dispatch uncertain'))
        up=AsyncMock()
        monkeypatch.setattr(page.mouse,'down',down)
        monkeypatch.setattr(page.mouse,'up',up)
        with pytest.raises(RuntimeError,match='dispatch uncertain'):
            await browser.click_at(state['tab'],state['observation'],150,90)
        up.assert_awaited_once_with(button='left')
        with pytest.raises(ValueError,match='Stale'):
            await browser.click_at(state['tab'],state['observation'],150,90)
    finally:
        await browser.close()
