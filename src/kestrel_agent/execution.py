"""Workspace-only Docker command execution, independent of the model provider."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import uuid
from pathlib import Path

from .config import atomic_write, home


def docker_argv(settings, workspace: Path, argv: list[str], cwd: str, name: str) -> list[str]:
    root = workspace.resolve()
    directory = Path(cwd).resolve()
    if not directory.is_relative_to(root):
        raise PermissionError('Docker commands must run inside the workspace.')
    if not argv or any(not isinstance(arg, str) or '\x00' in arg for arg in argv):
        raise ValueError('Expected a nonempty command argv.')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/:@-]*', settings.docker_image):
        raise ValueError('Invalid Docker image reference.')
    if ',' in str(root):
        raise ValueError('Docker workspace paths containing commas are unsupported.')
    mount = f'type=bind,src={root},dst=/workspace'
    if settings.permission == 'read-only':
        mount += ',readonly'
    result = ['docker', 'run', '--rm', '--pull=never', '--name', name,
              '--label', f'io.kestrel.owner={name}',
              '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges',
              '--pids-limit=256', '--memory=2g', '--cpus=2',
              '--tmpfs', '/tmp:rw,nosuid,nodev,size=256m',
              '--network', 'bridge' if settings.network else 'none',
              '--mount', mount, '--workdir', '/workspace/' + directory.relative_to(root).as_posix(),
              '--env', 'HOME=/tmp', '--user', f'{os.getuid()}:{os.getgid()}',
              '--entrypoint', argv[0], settings.docker_image, *argv[1:]]
    return result


class DockerExecutor:
    def __init__(self, settings, workspace):
        self.settings, self.workspace = settings, workspace
        self.active: dict[str, asyncio.subprocess.Process] = {}
        self.pending_cleanup: set[str] = set()
        self.targets: dict[str, str] = {}

    async def _target_fingerprint(self):
        code, output = await self._cleanup_command('context', 'inspect')
        if code or not output or len(output) >= 4096:
            raise RuntimeError('Cannot identify the Docker context; no command was started.')
        context = json.loads(output)
        if not isinstance(context, list) or len(context) != 1 or not isinstance(context[0], dict):
            raise RuntimeError('Docker returned invalid context metadata.')
        configuration = {key: os.environ.get(key) for key in (
            'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH')}
        return hashlib.sha256(json.dumps([context, configuration], sort_keys=True).encode()).hexdigest()

    async def _cleanup_command(self, *argv):
        process = await asyncio.create_subprocess_exec('docker', *argv,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            # Cleanup output is bounded independently of command output.
            async def read():
                data = bytearray()
                while chunk := await process.stdout.read(8192):
                    if len(data) < 4096:
                        data.extend(chunk[:4096-len(data)])
                return bytes(data)
            reader = asyncio.create_task(read())
            await asyncio.wait_for(asyncio.gather(process.wait(), reader), 10)
            return process.returncode, reader.result()
        finally:
            if process.returncode is None:
                process.kill()
            await process.wait()
            if 'reader' in locals():
                if not reader.done():
                    reader.cancel()
                await asyncio.gather(reader, return_exceptions=True)

    async def _remove(self, name):
        self.pending_cleanup.add(name)
        try:
            if name in self.targets and await self._target_fingerprint() != self.targets[name]:
                raise RuntimeError('Docker context changed; restore the original target before cleanup.')
            code, owner = await self._cleanup_command('inspect', '--format',
                '{{ index .Config.Labels "io.kestrel.owner" }}', name)
            if code:
                code, output = await self._cleanup_command('ps', '-aq', '--filter', f'name=^/{name}$')
                if code or output.strip():
                    raise RuntimeError('Container ownership or absence could not be confirmed.')
                self.pending_cleanup.discard(name)
                self.targets.pop(name, None)
                return
            if owner.decode(errors='replace').strip() != name:
                raise RuntimeError('Container ownership label does not match the recorded run.')
            code, _ = await self._cleanup_command('rm', '-f', name)
            if code:
                # --rm may already have removed it. Verify absence instead of
                # interpreting all nonzero exits as that benign race.
                code, output = await self._cleanup_command('ps', '-aq', '--filter', f'name=^/{name}$')
                if code or output.strip():
                    raise RuntimeError('Container still exists or Docker is unavailable.')
        except (OSError, ValueError, asyncio.TimeoutError, RuntimeError) as error:
            raise RuntimeError(f'Could not confirm container cleanup: {name}. '
                               'Restore the original Docker context/access and verify container ownership '
                               'before retrying cleanup.') from error
        self.pending_cleanup.discard(name)
        self.targets.pop(name, None)

    def receipt_path(self):
        key = hashlib.sha256(str(self.workspace.resolve()).encode()).hexdigest()
        return home() / 'docker_runs' / key / 'pending.json'

    async def command(self, argv, cwd):
        # An OS lock is released on process death. A PID file cannot establish
        # ownership reliably because PIDs can be reused after a crash.
        from .jobs import ownership
        receipt = self.receipt_path()
        with ownership(receipt.with_suffix('.lock')) as acquired:
            if not acquired:
                raise RuntimeError('Another Kestrel Docker command owns this workspace. Wait for it to finish.')
            if receipt.is_symlink():
                raise RuntimeError('Docker cleanup receipt must not be a symbolic link.')
            if receipt.exists():
                if receipt.stat().st_size > 16000:
                    raise RuntimeError('Invalid Docker cleanup receipt; inspect it before continuing.')
                saved = json.loads(receipt.read_text())
                if (not isinstance(saved, dict) or saved.get('workspace') != str(self.workspace.resolve())
                        or not isinstance(saved.get('name'), str)
                        or not re.fullmatch(r'kestrel-[a-f0-9]{32}', saved['name'])
                        or not isinstance(saved.get('target'), str)
                        or not re.fullmatch(r'[a-f0-9]{64}', saved['target'])):
                    raise RuntimeError('Invalid Docker cleanup receipt; inspect it before continuing.')
                self.targets[saved['name']] = saved['target']
                await self._remove(saved['name'])
                receipt.unlink()
            if self.pending_cleanup:
                await self.close()
            if not shutil.which('docker'):
                raise RuntimeError('Docker CLI is missing. Install Docker or select the Codex execution backend in /setup.')
            name = 'kestrel-' + uuid.uuid4().hex
            command = docker_argv(self.settings, self.workspace, argv, cwd, name)
            target = await self._target_fingerprint()
            atomic_write(receipt, json.dumps({'name': name, 'workspace': str(self.workspace.resolve()), 'target': target}))
            self.targets[name] = target
            try:
                return await self._command(command, name)
            finally:
                # Confirm cleanup after every exit, including a disconnected or
                # killed Docker client. Failed confirmation leaves the journal.
                await asyncio.shield(self._remove(name))
                receipt.unlink()

    async def _command(self, command, name):
        launch = asyncio.create_task(asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE))
        cancelled = False
        # Cancellation during subprocess creation must not lose the handle to a
        # Docker client that has already started. Reap it before container cleanup.
        while True:
            try:
                process = await asyncio.shield(launch)
                break
            except asyncio.CancelledError:
                if launch.cancelled():
                    raise
                cancelled = True
        self.active[name] = process
        async def capture(stream):
            chunks, kept, total = [], 0, 0
            while chunk := await stream.read(8192):
                total += len(chunk)
                if kept < 32000:
                    piece = chunk[:32000-kept]
                    chunks.append(piece)
                    kept += len(piece)
            return b''.join(chunks).decode('utf-8', errors='replace'), total > kept
        output = asyncio.create_task(capture(process.stdout))
        errors = asyncio.create_task(capture(process.stderr))
        try:
            if cancelled:
                raise asyncio.CancelledError
            await asyncio.wait_for(asyncio.gather(process.wait(), output, errors), self.settings.command_timeout_seconds)
            stdout, out_cut = output.result()
            stderr, err_cut = errors.result()
            return {'exitCode': process.returncode, 'stdout': stdout, 'stderr': stderr,
                    'output_truncated': out_cut or err_cut, 'execution_backend': 'docker'}
        finally:
            if process.returncode is None:
                process.kill()
            await process.wait()
            for reader in (output, errors):
                if not reader.done():
                    reader.cancel()
            await asyncio.gather(output, errors, return_exceptions=True)
            self.active.pop(name, None)

    async def close(self):
        failures = []
        for name in set(self.active) | self.pending_cleanup.copy():
            try:
                await self._remove(name)
            except RuntimeError as error:
                failures.append(str(error))
        if failures:
            raise RuntimeError('; '.join(failures))
