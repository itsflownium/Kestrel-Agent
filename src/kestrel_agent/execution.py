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
        self.pending_cleanup: set[str] = set()

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
            code, _ = await self._cleanup_command('rm', '-f', name)
            if code:
                # --rm may already have removed it. Verify absence instead of
                # interpreting all nonzero exits as that benign race.
                code, output = await self._cleanup_command('ps', '-aq', '--filter', f'name=^/{name}$')
                if code or output.strip():
                    raise RuntimeError('Container still exists or Docker is unavailable.')
        except (OSError, asyncio.TimeoutError, RuntimeError) as error:
            raise RuntimeError(f'Could not confirm container cleanup: {name}. '
                               'Restore Docker access and retry cleanup before continuing.') from error
        self.pending_cleanup.discard(name)

    async def command(self, argv, cwd):
        if self.pending_cleanup:
            await self.close()
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
        failures = []
        for name in set(self.active) | self.pending_cleanup.copy():
            try:
                await self._remove(name)
            except RuntimeError as error:
                failures.append(str(error))
        if failures:
            raise RuntimeError('; '.join(failures))
