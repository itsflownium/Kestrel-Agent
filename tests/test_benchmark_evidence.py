"""Benchmark assertions must use execution evidence, never a model's claimed output."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('workload_benchmark', Path(__file__).resolve().parents[1] / 'benchmarks/workloads.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


@pytest.mark.asyncio
@pytest.mark.parametrize('commands', [[], [{'exit_code':1, 'stdout':'TOTAL=42'}], [{'exit_code':None,'stdout':'TOTAL=42'}], [{'exit_code':False,'stdout':'TOTAL=42'}]])
async def test_claimed_recovery_without_successful_execution_fails(tmp_path, commands):
    passed, _ = await benchmark.grade('tool_recovery', 'TOTAL=42', tmp_path, None,
        [{'text':'The command succeeded with TOTAL=42'}], commands)
    assert not passed


@pytest.mark.asyncio
async def test_observed_successful_recovery_passes(tmp_path):
    passed, _ = await benchmark.grade('tool_recovery', 'TOTAL=42', tmp_path, None, [], [{'exit_code':0,'stdout':'TOTAL=42\n'}])
    assert passed


@pytest.mark.asyncio
async def test_json_answer_requires_execution_and_exact_format(tmp_path):
    answer='{"items":3,"ready":true}'
    assert not (await benchmark.grade('command_json', answer, tmp_path, None, [{'text':answer}], []))[0]
    commands=[{'exit_code':0,'stdout':answer}]
    assert (await benchmark.grade('command_json', answer, tmp_path, None, [], commands))[0]
    assert not (await benchmark.grade('command_json', '```json\n'+answer+'\n```', tmp_path, None, [], commands))[0]
