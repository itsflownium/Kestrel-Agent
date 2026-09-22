import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from kestrel_agent.config import Settings
from kestrel_agent.schema import bind
from kestrel_agent.tools import ToolExecutor


@pytest.mark.asyncio
async def test_exact_text_preserves_whitespace_when_appended(tmp_path):
    path = tmp_path / 'memo.txt'
    original = b'upstream\r\n\r\n  spaces\t\r\n'
    path.write_bytes(original)
    tools = ToolExecutor(Settings(), tmp_path, None, None, None, 'test', AsyncMock())
    result = tools.read_file({'path': 'memo.txt'})
    assert result['raw_text'].encode() == original
    args = bind({'path': 'memo.txt', 'content': '${read.raw_text}reviewed\n',
                 'expected_sha256': '${read.sha256}'}, {'read': result})
    await tools.execute('write_file', args)
    assert path.read_bytes() == original + b'reviewed\n'


def test_partial_read_does_not_offer_full_source_text(tmp_path):
    (tmp_path / 'memo.txt').write_text('first\nsecond\n')
    tools = ToolExecutor(Settings(), tmp_path, None, None, None, 'test', None)
    assert 'raw_text' not in tools.read_file({'path': 'memo.txt', 'max_lines': 1})
    assert 'raw_text' not in tools.read_file({'path': 'memo.txt', 'start_line': 2})


@pytest.mark.asyncio
async def test_extraction_and_hash_share_snapshot_even_when_source_changes(tmp_path, monkeypatch):
    import pypdf
    path = tmp_path / 'report.pdf'
    old, new = b'old simulated PDF bytes', b'updated PDF bytes'
    path.write_bytes(old)
    def parse(stream):
        assert stream.read() == old
        path.write_bytes(new)
        return SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: 'old content')])
    monkeypatch.setattr(pypdf, 'PdfReader', parse)
    tools = ToolExecutor(Settings(), tmp_path, None, None, None, 'test', AsyncMock())
    result = tools.read_file({'path': 'report.pdf'})
    assert result['sha256'] == hashlib.sha256(old).hexdigest()
    assert 'old content' in result['content'] and 'raw_text' not in result
    with pytest.raises(ValueError, match='current expected_sha256'):
        await tools.execute('write_file', {'path': 'report.pdf', 'content': 'replacement', 'expected_sha256': result['sha256']})
    assert path.read_bytes() == new
