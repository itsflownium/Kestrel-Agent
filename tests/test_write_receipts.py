import hashlib
from unittest.mock import AsyncMock

import pytest

from kestrel_agent.config import Settings
from kestrel_agent.engine import Engine
from kestrel_agent.store import Store


@pytest.mark.asyncio
@pytest.mark.parametrize('existing',[True,False])
async def test_write_rechecks_after_approval(tmp_path,monkeypatch,existing):
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    path=tmp_path/'target.txt'
    if existing: path.write_text('original')
    expected=hashlib.sha256(b'original').hexdigest() if existing else None
    async def confirm(_):
        path.write_text('changed while approval was open')
        return True
    settings=Settings(confirm_writes=True);store=Store(settings)
    engine=Engine(settings,tmp_path,store,store.create(tmp_path),lambda *a:None,confirm)
    try:
        with pytest.raises(ValueError):
            await engine.tools.execute('write_file',{'path':'target.txt','content':'replacement','expected_sha256':expected})
        assert path.read_text()=='changed while approval was open'
    finally: await engine.close();store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('existing',[True,False])
async def test_write_receipt_explains_verified_precondition(tmp_path,monkeypatch,existing):
    monkeypatch.setenv('KESTREL_HOME',str(tmp_path/'state'))
    path=tmp_path/'target.txt'
    if existing: path.write_text('original')
    expected=hashlib.sha256(b'original').hexdigest() if existing else None
    settings=Settings();store=Store(settings)
    engine=Engine(settings,tmp_path,store,store.create(tmp_path),lambda *a:None,AsyncMock(return_value=True))
    try:
        result=await engine.tools.execute('write_file',{'path':'target.txt','content':'replacement','expected_sha256':expected})
        assert result['previous_sha256']==expected
        assert result['precondition']==('existing content matched expected_sha256' if existing else 'target did not exist')
        assert result['sha256']==hashlib.sha256(b'replacement').hexdigest()
    finally: await engine.close();store.close()
