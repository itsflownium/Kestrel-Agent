import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('quality_workloads', Path(__file__).resolve().parents[1] / 'benchmarks/workloads.py')
workloads = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workloads)


@pytest.mark.asyncio
async def test_partial_effect_requires_observed_failure_and_exact_integer(tmp_path):
    (tmp_path / 'counter.txt').write_text('1')
    for answer, commands, expected in [
        ({'exit_code':2,'counter':1}, [], False),
        ({'exit_code':2,'counter':True}, [{'exit_code':2}], False),
        ({'exit_code':2,'counter':1}, [{'exit_code':2}], True),
    ]:
        passed, _ = await workloads.grade('partial_effect', json.dumps(answer), tmp_path, None, [], commands)
        assert passed is expected
    (tmp_path / 'counter.txt').write_text('2')
    passed, _ = await workloads.grade('partial_effect', '{"exit_code":2,"counter":1}', tmp_path, None, [], [{'exit_code':2}])
    assert passed is False


@pytest.mark.asyncio
async def test_stale_write_requires_refresh_evidence_and_exact_bytes(tmp_path):
    (tmp_path / 'memo.txt').write_text('upstream change\nreviewed\n')
    passed, _ = await workloads.grade('stale_write', 'DONE', tmp_path, None, [], [])
    assert passed is False
    commands = [{'exit_code':0,'stdout':'UPSTREAM_REFRESH_COMPLETE\n'}]
    passed, _ = await workloads.grade('stale_write', 'DONE', tmp_path, None, [], commands)
    assert passed is True
    (tmp_path / 'memo.txt').write_text('upstream change\nreviewed')
    passed, _ = await workloads.grade('stale_write', 'DONE', tmp_path, None, [], commands)
    assert passed is False
