"""Live pixel-location/action/readback smoke in an isolated synthetic canvas."""
import asyncio
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import random
import tempfile
import threading
import uuid
from unittest.mock import AsyncMock

from kestrel_agent.browser import BrowserAdapter
from kestrel_agent.completion import parse_json
from kestrel_agent.config import Settings, load_secrets
from kestrel_agent.providers import Runtime
from kestrel_agent.tools import ToolExecutor


async def main():
    load_secrets()
    rng=random.Random(31287)
    nonce=uuid.uuid4().hex[:8].upper()
    positions=[(rng.randrange(70,160),rng.randrange(50,120)),(rng.randrange(380,470),rng.randrange(190,250))]
    rng.shuffle(positions)
    gx,gy=positions[0]
    rx,ry=positions[1]
    records=[]
    html=f'''<body style="margin:0"><canvas id="surface" width="760" height="440"></canvas><script>
    const c=document.getElementById('surface'),g=c.getContext('2d');
    g.fillStyle='white';g.fillRect(0,0,760,440);g.font='22px sans-serif';
    g.fillStyle='green';g.fillRect({gx},{gy},170,65);g.fillStyle='white';g.fillText('Confirm',{gx+35},{gy+40});
    g.fillStyle='red';g.fillRect({rx},{ry},170,65);g.fillStyle='white';g.fillText('Reject',{rx+40},{ry+40});
    c.onclick=e=>{{let kind=e.offsetX>={gx}&&e.offsetX<{gx+170}&&e.offsetY>={gy}&&e.offsetY<{gy+65}?'green':e.offsetX>={rx}&&e.offsetX<{rx+170}&&e.offsetY>={ry}&&e.offsetY<{ry+65}?'red':'outside';
    if(kind==='green'){{g.fillStyle='black';g.fillText('SAVED {nonce}',40,390);}}
    fetch('/record',{{method:'POST',body:JSON.stringify({{kind}})}});}};
    </script></body>'''
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(html.encode())
        def do_POST(self):
            records.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(200);self.end_headers();self.wfile.write(b'{}')
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    browser=BrowserAdapter(headless=True)
    runtime=None
    report={'model':'gpt-6-astra','effort':'medium','agent_mode':'standard','passed':False,'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        with tempfile.TemporaryDirectory(prefix='kestrel-canvas-vision-') as directory:
            root=Path(directory);os.environ['KESTREL_HOME']=str(root/'state')
            settings=Settings(agent_mode='standard',model='gpt-6-astra',effort='medium',network=False,shell=False)
            runtime=Runtime(settings,root,lambda *_:None)
            tool=ToolExecutor(settings,root,runtime,None,None,'canvas-smoke',AsyncMock(return_value=False))
            state=await browser.open(f'http://127.0.0.1:{server.server_port}/')
            state,image=await browser.screenshot(state['tab'])
            assert not state['targets']
            (root/'before.png').write_bytes(image.data)
            Path('benchmarks/canvas-vision-before.png').write_bytes(image.data)
            located=await tool.execute('inspect_image',{'source':'before.png','question':f'Locate the center of the GREEN Confirm rectangle. The image is {image.width} by {image.height} pixels. Return only JSON with numeric x and y coordinates, relative to the image top-left. Do not choose the red rectangle.'})
            point=parse_json(located['content'])
            assert isinstance(point,dict) and set(point)=={'x','y'}
            report.update(location=located,point=point)
            await browser.click_at(state['tab'],state['observation'],point['x'],point['y'])
            for _ in range(50):
                if records: break
                await asyncio.sleep(.02)
            state,image=await browser.screenshot(state['tab'])
            (root/'after.png').write_bytes(image.data)
            Path('benchmarks/canvas-vision-after.png').write_bytes(image.data)
            readback=await tool.execute('inspect_image',{'source':'after.png','question':'Return only the exact code following SAVED in this image. If there is no SAVED code, return MISSING.'})
            report.update(readback=readback,expected_code=nonce,records=records,
                          passed=records==[{'kind':'green'}] and readback['content'].strip()==nonce,
                          generation_calls=runtime.model_calls,jev_calls=0)
    except Exception as error:
        report['error']=type(error).__name__+': '+str(error)
    finally:
        if runtime: await runtime.close()
        await browser.close()
        server.shutdown();server.server_close();thread.join(timeout=2)
    Path('benchmarks/results-canvas-vision-smoke.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__': asyncio.run(asyncio.wait_for(main(),180))
