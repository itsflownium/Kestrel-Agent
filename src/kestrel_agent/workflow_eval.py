"""Isolated, model-free behavioral fixtures for typed file workflows.

A passed user-supplied suite is scoped evidence, never automatic certification.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .completion import canonical, parse_json
from .workflow_templates import compile_workflow, read


class Fixture(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    name: str = Field(min_length=1, max_length=100)
    kind: str = Field(pattern='^(positive|negative)$')
    parameters: dict
    files: dict[str, str]
    expected_files: dict[str, str]
    expected_statuses: dict[str, str]
    expected_errors: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode='after')
    def bounded_files(self):
        if any(not text or len(text) > 400 for text in self.expected_errors.values()):
            raise ValueError('Expected error fragments must contain 1–400 characters.')
        for files in (self.files, self.expected_files):
            if len(files) > 64 or sum(len(value.encode()) for value in files.values()) > 200_000:
                raise ValueError('Each fixture file tree is limited to 64 files and 200 KB.')
            for name in files:
                path = Path(name)
                if not name or path.as_posix() != name or path.is_absolute() or any(part in {'..', '.'} for part in name.split('/')) or '\\' in name:
                    raise ValueError('Fixture paths must be relative file paths without traversal.')
                if any(parent.as_posix() in files for parent in path.parents if parent != Path('.')):
                    raise ValueError('A fixture path cannot be both a file and a directory.')
        return self


class Suite(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    version: int = Field(ge=1, le=1)
    cases: list[Fixture] = Field(min_length=1, max_length=24)

    @model_validator(mode='after')
    def unique_names(self):
        if len({case.name for case in self.cases}) != len(self.cases):
            raise ValueError('Fixture names must be unique.')
        return self


def validate_plans(template, suite):
    plans = []
    for case in suite.cases:
        plan, version = compile_workflow(template, case.parameters)
        if any(action.tool not in {'read_file', 'write_file', 'list_files', 'search_files'}
               or action.condition.strip().lower() != 'always' for action in plan.actions):
            raise ValueError('Offline fixtures support unconditional file tools only; no models, shell, network or connectors.')
        ids = {action.id for action in plan.actions}
        if set(case.expected_statuses) != ids:
            raise ValueError('Each fixture must specify expected status for every action.')
        if any(status not in {'completed', 'error', 'blocked', 'skip'} for status in case.expected_statuses.values()):
            raise ValueError('Unsupported expected action status.')
        if set(case.expected_errors) != {key for key, value in case.expected_statuses.items() if value == 'error'}:
            raise ValueError('Every expected error action needs an expected_errors message fragment.')
        successful = (all(status in {'completed', 'skip'} for status in case.expected_statuses.values())
                      and any(status == 'completed' for status in case.expected_statuses.values()))
        if (case.kind == 'positive') != successful:
            raise ValueError('Positive fixtures must complete required actions (unused branches may skip); negative fixtures must expect an error or blocked action.')
        plans.append((plan, version))
    return plans


async def run_worker(template, suite):
    from .config import Settings, home
    from .engine import Engine, GATE_PROMPT
    from .store import Store
    from .scheduler import execute_plan
    from .completion import register, evaluate

    plans = validate_plans(template, suite)
    settings = Settings(agent_mode='standard', shell=False, network=False,
                        permission='workspace', confirm_writes=False)
    store = Store(settings)
    results = []
    async def reject(*args, **kwargs):
        raise RuntimeError('Model and approval requests are unavailable in offline fixtures.')
    try:
        for index, (case, (plan, version)) in enumerate(zip(suite.cases, plans)):
            workspace = home().parent / 'fixtures' / str(index)
            workspace.mkdir(parents=True)
            for name, content in case.files.items():
                path = workspace/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding='utf-8')
            engine = Engine(settings, workspace, store, store.create(workspace), lambda *args: None, reject)
            engine.runtime.complete = reject
            engine.judge.decide = reject
            engine.state.update(request=template['description'], statuses={}, results={}, steps=0, observations=[])
            error = None
            try:
                register(engine.state, plan.completion_checks)
                await asyncio.wait_for(execute_plan(engine, plan, GATE_PROMPT), timeout=20)
                await evaluate(engine.state, engine.tools, {check.id for check in plan.completion_checks})
            except Exception as exc:
                # An unexpected exception is never accepted as a negative pass.
                error = type(exc).__name__
            finally:
                await engine.close()
            actual = {}
            for path in workspace.rglob('*'):
                if path.is_file():
                    actual[path.relative_to(workspace).as_posix()] = path.read_bytes()
            file_match = actual == {name: text.encode('utf-8') for name, text in case.expected_files.items()}
            status_match = engine.state['statuses'] == case.expected_statuses
            error_match = all(fragment in str(engine.state['results'].get(action, {}).get('error', ''))
                              for action, fragment in case.expected_errors.items())
            checks = engine.state.get('completion_checks', {})
            checks_pass = all(item.get('passed') is True for item in checks.values())
            passed = not error and file_match and status_match and error_match and (case.kind == 'negative' or checks_pass)
            results.append({'name': case.name, 'kind': case.kind, 'passed': bool(passed),
                            'files_match': file_match, 'statuses_match': status_match,
                            'expected_errors_match': error_match,
                            'statuses': engine.state['statuses'], 'completion_checks_passed': checks_pass,
                            'error': error})
    finally:
        store.close()
    return {'version': 1, 'template_sha256': plans[0][1],
            'suite_sha256': hashlib.sha256(canonical(suite.model_dump()).encode()).hexdigest(),
            'passed': all(result['passed'] for result in results), 'cases': results,
            'positive_cases': sum(case.kind == 'positive' for case in suite.cases),
            'negative_cases': sum(case.kind == 'negative' for case in suite.cases),
            'scope': 'Offline unconditional file workflows; user-supplied exact file and action-status expectations.',
            'certification': 'not_certified',
            'limitations': 'No independent suite authorship or held-out split is verified. No model repair, final answer, shell, browser, desktop or external provider is evaluated. No automatic activation or promotion.'}


def read_suite_bytes(path):
    from .skill_registry import read_bytes
    path = Path(path).expanduser().absolute()
    root = path.parent.resolve()
    try:
        return read_bytes(root/path.name, root, 1_000_000)
    except ValueError as error:
        raise ValueError('Workflow suite must be a regular non-symlink file no larger than 1 MB.') from error


def evaluate_files(template_path, suite_path):
    template = read(template_path)
    suite = Suite.model_validate(parse_json(read_suite_bytes(suite_path)))
    validate_plans(template, suite)
    with tempfile.TemporaryDirectory(prefix='kestrel-workflow-eval-') as directory:
        # A separate process owns its private home; never mutate the caller's
        # global environment or write fixture sessions into the user's database.
        env = {key: value for key, value in os.environ.items()
               if key in {'PATH', 'HOME', 'LANG', 'LC_ALL', 'SYSTEMROOT'}}
        env['KESTREL_HOME'] = str(Path(directory)/'state')
        try:
            process = subprocess.run([sys.executable, '-m', 'kestrel_agent.workflow_eval'],
                                     input=json.dumps({'template': template, 'suite': suite.model_dump()}, ensure_ascii=False),
                                     text=True, capture_output=True, env=env, cwd=directory,
                                     timeout=30 * len(suite.cases) + 10)
        except subprocess.TimeoutExpired as error:
            raise ValueError('Offline fixture worker timed out; no validation report was accepted.') from error
        if process.returncode:
            raise ValueError('Offline fixture worker failed; no validation report was accepted.')
        return parse_json(process.stdout)


if __name__ == '__main__':
    request = parse_json(sys.stdin.buffer.read(2_000_001))
    print(json.dumps(asyncio.run(run_worker(request['template'], Suite.model_validate(request['suite'])))))
