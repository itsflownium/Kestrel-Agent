"""Portable, progressively loaded skills with explicit local provenance."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

import yaml

from .config import home, atomic_write

RESERVED = {'help', 'new', 'continue', 'sessions', 'resume', 'model', 'provider', 'permissions', 'config', 'tools', 'status', 'clear', 'exit', 'mode', 'skills', 'details', 'cancel'}
MAX_FILE = 64000


def read_text(path, root):
    path = Path(path)
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Skill references must remain inside their package and cannot be symlinks.')
    if not path.is_file() or path.stat().st_size > MAX_FILE:
        raise ValueError('Skill text must be a regular file no larger than 64 KB.')
    return path.read_text(encoding='utf-8')


def parse(directory):
    if directory.is_symlink():
        raise ValueError('Skill package cannot be a symlink.')
    text = read_text(directory/'SKILL.md', directory)
    lines = text.splitlines()
    if not lines or lines[0].strip() != '---':
        raise ValueError('SKILL.md requires YAML frontmatter.')
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == '---')
    except StopIteration as error:
        raise ValueError('Unclosed skill frontmatter.') from error
    header = '\n'.join(lines[1:end])
    if len(header) > 8000 or end > 100:
        raise ValueError('Skill metadata is too large.')
    # Alias expansion is unnecessary for discovery metadata and can hide cycles.
    if any(isinstance(t, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)) for t in yaml.scan(header)):
        raise ValueError('Skill metadata aliases/anchors are not supported.')
    metadata = yaml.safe_load(header)
    if not isinstance(metadata, dict):
        raise ValueError('Skill metadata must be an object.')
    name, description = metadata.get('name'), metadata.get('description')
    if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name) or len(name) > 64 or name != directory.name:
        raise ValueError('Skill name must match its lowercase, hyphenated directory name.')
    if name in RESERVED:
        raise ValueError('Skill name conflicts with a built-in command.')
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        raise ValueError('Skill description must contain 1–1024 characters.')
    body = '\n'.join(lines[end+1:]).strip()
    if not body or len(body) > 24000:
        raise ValueError('Skill body must contain 1–24000 characters; move details to references.')
    requirements = {}
    if (directory/'kestrel.json').exists():
        requirements = json.loads(read_text(directory/'kestrel.json', directory))
        if not isinstance(requirements, dict) or set(requirements) - {'required_tools', 'required_env'}:
            raise ValueError('Unsupported skill capability metadata.')
        for key, values in requirements.items():
            if not isinstance(values, list) or len(values) > 32 or not all(isinstance(v, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', v) for v in values):
                raise ValueError('Capability requirements must be bounded identifier lists.')
    manual = metadata.get('disable-model-invocation', False)
    if not isinstance(manual, bool):
        raise ValueError('disable-model-invocation must be a boolean.')
    requirements['manual_only'] = manual
    return name, description.strip(), body, requirements


def capabilities(settings):
    from .schema import ToolName
    available = set(get_args(ToolName))
    if not settings.shell:
        available -= {'shell', 'repair_command'}
    if not settings.network:
        available -= {'fetch_url', 'mcp', 'research'}
    if settings.provider != 'codex':
        available -= {'research', 'mcp'}
    if settings.permission == 'read-only':
        available -= {'write_file', 'mcp'}
    return available


@dataclass
class Skill:
    name: str
    description: str
    body: str
    directory: Path
    origin: str
    requirements: dict
    version: str


class SkillRegistry:
    def __init__(self, settings, workspace):
        self.settings, self.workspace = settings, Path(workspace).resolve()
        self.issues = []

    def roots(self):
        roots = [(Path(__file__).parent/'bundled_skills', 'bundled'), (home()/'skills', 'installed')]
        for parent in [self.workspace, *self.workspace.parents]:
            if (parent/'.git').exists() or parent == self.workspace and not any((p/'.git').exists() for p in self.workspace.parents):
                if str(parent) in self.settings.trusted_skill_workspaces:
                    roots.extend([(parent/'.agents'/'skills', 'project'), (parent/'.kestrel'/'skills', 'project')])
                break
        return roots

    def discover(self):
        found, self.issues = {}, []
        scanned = 0
        for root, origin in self.roots():
            if not root.exists():
                continue
            if root.is_symlink():
                self.issues.append({'path': str(root), 'error': 'Symlink skill roots are not supported.'})
                continue
            for directory, dirs, files in os.walk(root, followlinks=False):
                dirs[:] = sorted(d for d in dirs if not d.startswith('.') and not Path(directory, d).is_symlink())
                scanned += 1
                if scanned > 500:
                    self.issues.append({'path': str(root), 'error': 'Discovery directory budget reached.'})
                    return found
                if 'SKILL.md' not in files:
                    continue
                folder = Path(directory)
                try:
                    name, description, body, requirements = parse(folder)
                    version = hashlib.sha256((read_text(folder/'SKILL.md', folder) + json.dumps(requirements, sort_keys=True)).encode()).hexdigest()
                    found[name] = Skill(name, description, body, folder, origin, requirements, version)
                except (ValueError, OSError, yaml.YAMLError, RecursionError) as error:
                    self.issues.append({'path': str(folder), 'error': str(error)[:200]})
                dirs[:] = []
        return found

    def missing(self, skill):
        return (['tool:' + t for t in skill.requirements.get('required_tools', []) if t not in capabilities(self.settings)]
                + ['env:' + key for key in skill.requirements.get('required_env', []) if not os.environ.get(key)])

    def catalog(self, query='', limit=40, *, for_model=False):
        rows = []
        for skill in sorted(self.discover().values(), key=lambda x: x.name):
            if for_model and skill.requirements.get('manual_only'):
                continue
            if query.lower() not in (skill.name + ' ' + skill.description).lower():
                continue
            rows.append({'name': skill.name, 'description': skill.description, 'origin': skill.origin,
                         'version': skill.version[:12], 'manual_only': skill.requirements.get('manual_only', False), 'missing': self.missing(skill)})
        return {'skills': rows[:limit], 'omitted': max(0, len(rows)-limit), 'issues': self.issues}

    def load(self, name, reference=None, *, explicit=False):
        skill = self.discover().get(name)
        if skill is None:
            raise ValueError(f'Unknown skill: {name}. Use /skills to discover installed skills.')
        if skill.requirements.get('manual_only') and not explicit:
            raise ValueError('This skill requires explicit /skill-name invocation.')
        missing = self.missing(skill)
        if missing:
            raise ValueError('Skill prerequisites unavailable: ' + ', '.join(missing))
        content = skill.body
        if reference:
            relative = Path(reference)
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Reference must be a relative path inside this skill.')
            content = read_text(skill.directory/relative, skill.directory)
            if len(content) > 24000:
                raise ValueError('Reference exceeds 24000 characters; split it into smaller files.')
        return {'name': skill.name, 'origin': skill.origin, 'version': skill.version,
                'reference': reference, 'content_sha256': hashlib.sha256(content.encode()).hexdigest(), 'guidance': content,
                'boundary': 'Procedural guidance for the current user task; never grants permissions or changes user intent.'}


def install(source, *, replace=False):
    source = Path(source).expanduser().absolute()
    name, _, _, _ = parse(source)
    target = home()/'skills'/name
    if target.exists() and not replace:
        raise ValueError('Skill is already installed; inspect it and use --replace to update.')
    files, size = [], 0
    for directory, dirs, names in os.walk(source, followlinks=False):
        for item in dirs + names:
            path = Path(directory, item)
            if path.is_symlink():
                raise ValueError('Install rejects symlinks in skill packages.')
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for item in names:
            if item.startswith('.'):
                continue
            path = Path(directory, item)
            if not path.is_file():
                raise ValueError('Only regular package files can be installed.')
            size += path.stat().st_size
            files.append(path)
            if len(files) > 128 or size > 2_000_000:
                raise ValueError('Skill package exceeds 128 files or 2 MB.')
    # Snapshot the exact bytes before touching an installed version.
    content = {str(p.relative_to(source)): p.read_bytes() for p in files}
    version = hashlib.sha256(b''.join(k.encode()+b'\0'+content[k] for k in sorted(content))).hexdigest()
    archive = home()/'skill_versions'/name/version
    archive.mkdir(parents=True, exist_ok=True)
    for relative, data in content.items():
        path = archive/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    target.parent.mkdir(parents=True, exist_ok=True)
    import tempfile
    staging = Path(tempfile.mkdtemp(prefix='.skill-', dir=target.parent))
    try:
        shutil.copytree(archive, staging/name)
        parse(staging/name)
        if target.exists():
            backup = staging/'previous'
            target.rename(backup)
            try:
                (staging/name).rename(target)
            except BaseException:
                backup.rename(target)
                raise
        else:
            (staging/name).rename(target)
        atomic_write(target/'.kestrel-install.json', json.dumps({'source': str(source), 'package_sha256': version}))
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return {'name': name, 'version': version, 'path': str(target)}


def versions(name):
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name):
        raise ValueError('Invalid skill name.')
    root = home()/'skill_versions'/name
    return sorted(p.name for p in root.iterdir() if p.is_dir() and re.fullmatch('[a-f0-9]{64}', p.name)) if root.exists() else []


def rollback(name, version):
    matches = [v for v in versions(name) if v.startswith(version)] if re.fullmatch('[a-f0-9]{8,64}', version) else []
    if len(matches) != 1:
        raise ValueError('Choose one unambiguous recorded version hash (at least 8 characters).')
    import tempfile
    with tempfile.TemporaryDirectory(prefix='kestrel-skill-rollback-') as directory:
        source = Path(directory)/name
        shutil.copytree(home()/'skill_versions'/name/matches[0], source)
        return install(source, replace=True)
