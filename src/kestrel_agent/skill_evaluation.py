"""Recorded, version-bound evaluation and explicit export of skill workflows.

These reports certify neither skill prose nor independent fixture authorship.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import tempfile
import time
import uuid

from .completion import parse_json


def validate_exports(exports):
    if not isinstance(exports, dict) or len(exports) > 8:
        raise ValueError('Skill workflows must map at most eight export names to relative JSON paths.')
    for name, value in exports.items():
        if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', name):
            raise ValueError('Invalid skill workflow export name.')
        if not isinstance(value, str) or not 1 <= len(value) <= 512:
            raise ValueError('Skill workflow export requires a relative JSON path.')
        path = Path(value)
        if (path.is_absolute() or path.as_posix() != value or '\\' in value
                or any(part.startswith('.') for part in value.split('/')) or path.suffix != '.json'):
            raise ValueError('Skill workflow paths must be canonical relative JSON paths without hidden/traversal components.')


def initialize(store):
    store.db.execute('CREATE TABLE IF NOT EXISTS skill_workflow_evaluations(id TEXT PRIMARY KEY, body TEXT NOT NULL)')
    store.db.commit()


def report(store, evaluation_id):
    if not re.fullmatch(r'[a-f0-9]{32}', evaluation_id):
        raise ValueError('Use the complete recorded evaluation ID.')
    initialize(store)
    row = store.db.execute('SELECT body FROM skill_workflow_evaluations WHERE id=?', (evaluation_id,)).fetchone()
    if row is None:
        raise ValueError('No recorded skill workflow evaluation with this ID.')
    return parse_json(row[0])


def snapshot(registry, name):
    from .skill_registry import package_snapshot, snapshot_version
    skill = registry.discover().get(name)
    if skill is None:
        raise ValueError('Unknown skill; inspect the skill catalog and its discovery errors.')
    content = package_snapshot(skill.directory)
    return skill, content, snapshot_version(content)


def frozen_export(directory, name, content, workflow):
    from .skill_registry import write_snapshot, parse
    from .workflow_templates import read
    package = Path(directory)/name
    write_snapshot(package, content)
    # Read metadata and template from the same frozen bytes; never mix discovery
    # metadata with a later source-package revision.
    _, _, _, requirements, version = parse(package, with_version=True)
    exports = requirements.get('workflows', {})
    if workflow not in exports:
        raise ValueError('This skill does not declare that workflow export.')
    template_path = package/exports[workflow]
    template = read(template_path)
    return template_path, template, version, exports[workflow]


def evaluate(registry, name, workflow, suite_path, store):
    from .workflow_eval import evaluate_files, read_suite_bytes
    skill, content, package_hash = snapshot(registry, name)
    suite_data = read_suite_bytes(suite_path)
    # The suite is caller-supplied evidence, not proof of independent authorship.
    with tempfile.TemporaryDirectory(prefix='kestrel-skill-evaluation-') as directory:
        template_path, template, version, relative = frozen_export(directory, name, content, workflow)
        suite_copy = Path(directory)/'suite.json'
        suite_copy.write_bytes(suite_data)
        result = evaluate_files(template_path, suite_copy)
    evaluation_id = uuid.uuid4().hex
    result.update(evaluation_id=evaluation_id, created=time.time(), skill_name=name,
                  skill_origin=skill.origin, skill_entrypoint_sha256=version,
                  skill_package_sha256=package_hash, workflow_export=workflow,
                  workflow_path=relative, evaluated_template=template,
                  scope='The declared typed file workflow only; skill Markdown, scripts and other exports are not executed or certified.',
                  certification='not_certified',
                  fixture_authority='Caller-supplied expectations; independent authorship and unseen inputs are not established.',
                  export_eligible=bool(result['passed'] and result['positive_cases'] and result['negative_cases']))
    initialize(store)
    with store.db:
        store.db.execute('INSERT INTO skill_workflow_evaluations VALUES(?,?)', (evaluation_id, json.dumps(result, ensure_ascii=False)))
    return result


def export(registry, name, workflow, evaluation_id, store, *, replace=False):
    from .completion import canonical
    from .workflow_templates import install
    from .workflow_eval import runtime_fingerprint
    value = report(store, evaluation_id)
    if value.get('skill_name') != name or value.get('workflow_export') != workflow:
        raise ValueError('Evaluation belongs to a different skill or workflow export.')
    if not value.get('passed') or not value.get('positive_cases') or not value.get('negative_cases'):
        raise ValueError('Export requires a passing recorded suite with positive and negative cases.')
    if value.get('runtime_sha256') != runtime_fingerprint():
        raise ValueError('Evaluation runtime changed or was not recorded; rerun the suite before exporting.')
    _, content, package_hash = snapshot(registry, name)
    if package_hash != value.get('skill_package_sha256'):
        raise ValueError('Skill package changed since evaluation; test this version before exporting.')
    with tempfile.TemporaryDirectory(prefix='kestrel-skill-export-') as directory:
        path, template, version, relative = frozen_export(directory, name, content, workflow)
        template_hash = hashlib.sha256(json.dumps(template, sort_keys=True).encode()).hexdigest()
        if (template_hash != value.get('template_sha256')
                or canonical(template) != canonical(value.get('evaluated_template'))
                or version != value.get('skill_entrypoint_sha256') or relative != value.get('workflow_path')):
            raise ValueError('The export does not match its evaluated content.')
        installed = install(path, replace=replace)
    return {'workflow_name': installed, 'template_sha256': template_hash,
            'skill_name': name, 'skill_package_sha256': package_hash, 'evaluation_id': evaluation_id,
            'status': 'installed_from_tested_export', 'certification': 'not_certified',
            'scope': value['scope'], 'actions_executed': False,
            'next': 'Preview and explicitly run the installed template with current parameters and normal permissions.'}
