"""Explicit live image-input smoke test; one model call, no Jev or desktop access."""
import asyncio
import json
import hashlib
import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock
from PIL import Image, ImageDraw, ImageFont
from kestrel_agent.config import Settings, load_secrets
from kestrel_agent.providers import Runtime
from kestrel_agent.tools import ToolExecutor

async def main():
    load_secrets()
    target=uuid.uuid4().hex[:8].upper()
    other=uuid.uuid4().hex[:8].upper()
    image=Image.new('RGB',(800,300),'white')
    draw=ImageDraw.Draw(image)
    font=ImageFont.load_default(size=40)
    draw.rounded_rectangle((30,70,375,220),radius=12,fill='#087e3b')
    draw.rounded_rectangle((425,70,770,220),radius=12,fill='#b52828')
    draw.text((75,120),target,font=font,fill='white')
    draw.text((470,120),other,font=font,fill='white')
    image.save('benchmarks/vision-fixture.png')
    with tempfile.TemporaryDirectory(prefix='kestrel-vision-') as directory:
        root=Path(directory)
        os.environ['KESTREL_HOME']=str(root/'state')
        image.save(root/'fixture.png')
        settings=Settings(agent_mode='standard',model='gpt-6-astra',effort='medium',network=False)
        runtime=Runtime(settings,root,lambda *_:None)
        tool=ToolExecutor(settings,root,runtime,None,None,'vision-fixture',AsyncMock(return_value=False))
        try:
            async with asyncio.timeout(120):
                result=await tool.execute('inspect_image',{'source':'fixture.png','question':'Return only the exact text on the green button. Do not return the text on the red button.'})
            report={'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'fixture':'vision-fixture.png','model':settings.model,'effort':settings.effort,'expected':target,'result':result,
                    'passed':result['content'].strip()==target,'generation_calls':runtime.model_calls,'jev_calls':0}
            Path('benchmarks/results-vision-smoke.json').write_text(json.dumps(report,indent=2))
            print(json.dumps(report))
        finally:
            await runtime.close()

if __name__=='__main__': asyncio.run(main())
