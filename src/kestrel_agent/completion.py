"""Bounded deterministic completion contracts; no generated code is executed."""
import asyncio
import json
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def parse_json(text):
    def reject(value):
        raise ValueError('Non-finite JSON is not supported.')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON keys are ambiguous.')
            result[key] = value
        return result
    return json.loads(text, parse_constant=reject, object_pairs_hook=pairs)


class CompletionCheck(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: str = Field(pattern=r'^[a-z][a-z0-9_]{0,39}$')
    requirement: str = Field(min_length=1, max_length=1000)
    kind: Literal['result_equals', 'result_json_equals', 'file_text_equals', 'file_json_equals']
    source: str = Field(min_length=1, max_length=2000)
    expected_json: str = Field(max_length=4000)

    @model_validator(mode='after')
    def valid(self):
        expected = parse_json(self.expected_json)
        if self.kind == 'file_text_equals' and not isinstance(expected, str):
            raise ValueError('Text checks require a JSON string expectation.')
        if self.kind.startswith('result_'):
            if not re.fullmatch(r'\$\{[a-z][a-z0-9_]*\.[A-Za-z0-9_.]+\}', self.source):
                raise ValueError('Result checks need a whole action-result reference.')
        elif '${' in self.source:
            raise ValueError('File checks need a literal path.')
        return self


def register(state, checks):
    ledger = state.setdefault('completion_checks', {})
    if len(set(ledger) | {check.id for check in checks}) > 16:
        raise ValueError('At most 16 completion checks may be retained per task.')
    # Validate all replacements before changing the checkpoint.
    for check in checks:
        previous = ledger.get(check.id)
        if previous:
            old = CompletionCheck.model_validate(previous['check'])
            if (old.kind, old.requirement, canonical(parse_json(old.expected_json))) != (
                check.kind, check.requirement, canonical(parse_json(check.expected_json))
            ) or (old.kind.startswith('file_') and old.source != check.source):
                raise ValueError(f'Cannot weaken or replace completion check {check.id}; start a new request to change its contract.')
    for check in checks:
        ledger[check.id] = {'check': check.model_dump(), 'passed': False, 'reason': 'Pending evaluation'}


async def evaluate(state, tools, active_ids):
    from .schema import bind
    ledger = state.setdefault('completion_checks', {})
    for key, entry in ledger.items():
        check = CompletionCheck.model_validate(entry['check'])
        # Old result checks keep their recorded verdict until explicitly rebound.
        # File checks always inspect the current artifact, including across replans.
        if check.kind.startswith('result_') and key not in active_ids:
            continue
        try:
            if check.kind.startswith('result_'):
                action = check.source[2:].split('.')[0]
                status = state.get('statuses', {}).get(action)
                if status not in {'completed', 'error'}:
                    raise ValueError('No definite executed action outcome.')
                actual = bind(check.source, state.get('results', {}))
                if check.kind == 'result_json_equals':
                    if not isinstance(actual, str):
                        raise ValueError('JSON result check requires complete JSON text.')
                    actual = parse_json(actual)
            else:
                result = await asyncio.to_thread(tools.read_file, {'path': check.source, 'start_line': 1, 'max_lines': 1000})
                if 'raw_text' not in result:
                    raise ValueError('Complete small plain-text artifact required; extracted or truncated text cannot pass.')
                actual = result['raw_text']
                if check.kind == 'file_json_equals':
                    actual = parse_json(actual)
                entry['source_sha256'] = result['sha256']
            entry['passed'] = canonical(actual) == canonical(parse_json(check.expected_json))
            entry['reason'] = 'Exact comparison passed' if entry['passed'] else 'Observed value differs from required value'
        except (ValueError, TypeError, KeyError, IndexError, OSError) as error:
            entry.update(passed=False, reason=str(error)[:300])
    return {key: entry for key, entry in ledger.items() if not entry['passed']}
