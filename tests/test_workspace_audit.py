from kestrel_agent.workspace_audit import snapshot, compare


def test_net_changes_include_binary_modes_and_symlinks(tmp_path):
    (tmp_path / 'nested').mkdir()
    file = tmp_path / 'nested' / 'binary'
    file.write_bytes(b'\x00\x01')
    before = snapshot(tmp_path, max_seconds=5)
    assert compare(before, snapshot(tmp_path, max_seconds=5))['unchanged_at_boundaries'] is True
    file.write_bytes(b'\x00\x02')
    (tmp_path / 'link').symlink_to('/outside/does-not-exist')
    result = compare(before, snapshot(tmp_path, max_seconds=5))
    assert result['complete'] is True
    assert set(result['changed_paths']) == {'nested/binary', 'link'}
    assert result['unchanged_at_boundaries'] is False


def test_incomplete_snapshot_never_claims_unchanged(tmp_path):
    (tmp_path / 'large').write_bytes(b'x' * 100)
    result = snapshot(tmp_path, max_bytes=10)
    assert result['complete'] is False
    assert compare(result, result)['unchanged_at_boundaries'] is None
