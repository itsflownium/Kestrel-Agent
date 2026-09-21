"""Explicit, typed workflow templates compiled into normal permissioned plans."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .config import atomic_write, home
from .completion import parse_json
from .schema import Plan


def directory():
    return home() / 'workflow_templates'


def read(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 100000:
        raise ValueError('A workflow must be a regular JSON file no larger than 100 KB.')
    value = parse_json(path.read_text())
    allowed = {'version', 'name', 'description', 'parameters', 'actions', 'success_criteria', 'completion_checks', 'final_response_ref'}
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError('Unknown workflow fields.')
    if type(value.get('version')) is not int or value['version'] != 1:
        raise ValueError('Expected workflow format version 1.')
    if not isinstance(value.get('name'), str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', value['name']):
        raise ValueError('Invalid workflow name.')
    if not isinstance(value.get('description'), str) or not 1 <= len(value['description']) <= 2000:
        raise ValueError('A workflow description is required (up to 2000 characters).')
    schema = value.get('parameters')
    if not isinstance(schema, dict) or schema.get('type') != 'object' or schema.get('additionalProperties') is not False:
        raise ValueError('Parameters need an object JSON schema with additionalProperties=false.')
    # No external schema resolution, dynamic remote schemas, or implicit code.
    def refs(item):
        if isinstance(item, dict):
            if '$ref' in item or '$dynamicRef' in item:
                raise ValueError('Workflow parameter schemas cannot contain references.')
            for child in item.values():
                refs(child)
        elif isinstance(item, list):
            for child in item:
                refs(child)
    refs(schema)
    from jsonschema import Draft202012Validator
    Draft202012Validator.check_schema(schema)
    if not isinstance(value.get('actions'), list) or not 1 <= len(value['actions']) <= 12:
        raise ValueError('A workflow needs 1–12 actions.')
    return value


def load(name):
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', name):
        raise ValueError('Invalid workflow name.')
    value = read(directory() / (name + '.json'))
    if value['name'] != name:
        raise ValueError('Workflow filename and name differ.')
    return value


def install(path, replace=False):
    value = read(path)
    target = directory() / (value['name'] + '.json')
    if target.exists() and not replace:
        raise ValueError('Workflow exists; use --replace after reviewing the new version.')
    directory().mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_write(target, json.dumps(value, indent=2, ensure_ascii=False))
    return value['name']


def compile_workflow(value, parameters):
    from jsonschema import Draft202012Validator
    Draft202012Validator(value['parameters']).validate(parameters)
    def substitute(item):
        if isinstance(item, dict):
            if set(item) == {'$param'}:
                name = item['$param']
                if not isinstance(name, str) or name not in parameters:
                    raise ValueError('A referenced workflow parameter was not supplied.')
                return parameters[name]
            return {key: substitute(child) for key, child in item.items()}
        if isinstance(item, list):
            return [substitute(child) for child in item]
        return item
    actions = []
    for original in value['actions']:
        action = dict(original)
        if 'arguments_json' in action or 'arguments' not in action:
            raise ValueError('Workflow actions use typed arguments, not arguments_json.')
        action['arguments_json'] = json.dumps(substitute(action.pop('arguments')), ensure_ascii=False, allow_nan=False)
        actions.append(action)
    checks = []
    for original in value.get('completion_checks', []):
        check = dict(original)
        if 'expected' in check:
            check['expected_json'] = json.dumps(substitute(check.pop('expected')), ensure_ascii=False, allow_nan=False)
        check['source'] = substitute(check['source'])
        checks.append(check)
    plan = Plan(mode='plan', message=value['description'], actions=actions,
        success_criteria=value.get('success_criteria', []), completion_checks=checks,
        final_response_ref=value.get('final_response_ref'))
    version = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    return plan, version
