"""Workspace-only Docker command execution, independent of the model provider."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import uuid
from pathlib import Path


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

    async def _remove(self, name):
        process = await asyncio.create_subprocess_exec('docker', 'rm', '-f', name,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            await asyncio.wait_for(process.wait(), 10)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise RuntimeError(f'Could not confirm container cleanup: {name}')

    async def command(self, argv, cwd):
        if not shutil.which('docker'):
            raise RuntimeError('Docker CLI is missing. Install Docker or select the Codex execution backend in /setup.')
        name = 'kestrel-' + uuid.uuid4().hex
        command = docker_argv(self.settings, self.workspace, argv, cwd, name)
        process = await asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
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
            await asyncio.wait_for(asyncio.gather(process.wait(), output, errors), self.settings.command_timeout_seconds)
            stdout, out_cut = output.result()
            stderr, err_cut = errors.result()
            return {'exitCode': process.returncode, 'stdout': stdout, 'stderr': stderr,
                    'output_truncated': out_cut or err_cut, 'execution_backend': 'docker'}
        except (asyncio.CancelledError, asyncio.TimeoutError):
            await asyncio.shield(self._remove(name))
            raise
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
        for name in list(self.active):
            await self._remove(name)
