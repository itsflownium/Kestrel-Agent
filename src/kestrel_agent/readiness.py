"""Bounded readiness checks; no generation, image pulls or permission changes."""
import asyncio
import importlib.util
import os
import shutil
import sys
import signal
from urllib.parse import urlsplit


async def command_ready(*argv):
    """Probe only an exit code. Never copy subprocess output into diagnostics."""
    process = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.DEVNULL,
                                                   stderr=asyncio.subprocess.DEVNULL,
                                                   start_new_session=os.name == 'posix')
    try:
        return await asyncio.wait_for(process.wait(), 5) == 0
    finally:
        if process.returncode is None:
            try:
                if os.name == 'posix':
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
        await process.wait()


async def chromium_ready():
    from playwright.async_api import async_playwright
    async with asyncio.timeout(20):
        async with async_playwright() as driver:
            browser = await driver.chromium.launch(headless=True, timeout=10000)
            try:
                return True
            finally:
                await browser.close()


async def inspect_readiness(settings, *, runtime_checks=False):
    checks = []
    def add(name, state, detail):
        checks.append({'name': name, 'state': state, 'detail': detail})
    add('Model selection', 'configured' if settings.model or settings.provider == 'codex' else 'missing',
        'Model ID configured; availability is unverified.' if settings.model else
        'Codex provider default selected.' if settings.provider == 'codex' else 'Select an exact model ID through /model or /setup.')
    if settings.provider == 'codex':
        add('Model authentication', 'unverified', 'Use doctor --online to check Codex sign-in without generation.')
    else:
        from .generation import api_key, endpoint
        try:
            local = urlsplit(endpoint(settings)).hostname in {'localhost', '127.0.0.1', '::1'}
            present = bool(api_key(settings))
            add('Model authentication', 'configured' if present or local else 'missing',
                'Credentials are configured; validity is not checked.' if present else
                'Loopback provider permits no key; availability is not checked.' if local else 'Run kestrel auth provider.')
        except Exception:
            add('Model authentication', 'unavailable', 'Provider configuration could not be read; review /setup.')
    if settings.agent_mode == 'jev':
        present = bool(os.environ.get('TYPESAFE_API_KEY'))
        add('Jev', 'configured' if present else 'missing', 'Key presence only; validity is not checked.' if present else 'Run kestrel auth jev.')
    else:
        add('Jev', 'disabled', 'Standard mode does not require Jev.')
    if not settings.shell:
        add('Command execution', 'disabled', 'Shell execution is disabled in settings.')
    elif settings.execution_backend == 'docker':
        docker = shutil.which('docker')
        if not docker:
            add('Docker', 'missing', 'Install Docker and configure a daemon.')
        elif not runtime_checks:
            add('Docker', 'unverified', 'CLI found. Use --runtime-checks to check the configured daemon and local image.')
        else:
            try:
                ready = await command_ready(docker, 'info', '--format', '{{.ServerVersion}}')
                add('Docker daemon', 'ready' if ready else 'unavailable',
                    'Configured daemon responded.' if ready else 'Start or reconnect the configured Docker daemon/context.')
                if ready:
                    present = await command_ready(docker, 'image', 'inspect', '--format', '{{.Id}}', '--', settings.docker_image)
                    add('Docker image', 'ready' if present else 'missing',
                        'Configured image is present; no container was run.' if present else 'Install the configured image explicitly; no image was pulled.')
            except Exception:
                add('Docker runtime', 'unavailable', 'Daemon/image probe failed or exceeded five seconds; inspect Docker separately.')
    else:
        add('Command execution', 'unverified', 'Codex sandbox selected; no task command was executed by this check.')
    if importlib.util.find_spec('playwright') is None:
        add('Browser', 'missing', 'Install the browser extra and its matching Chromium runtime.')
    elif not runtime_checks:
        add('Browser', 'unverified', 'Playwright found. Use --runtime-checks to verify Chromium can launch.')
    else:
        try:
            await chromium_ready()
            add('Browser', 'ready', 'Isolated headless Chromium launched and closed; no page was opened.')
        except Exception:
            add('Browser', 'unavailable', 'Chromium could not launch. Check its matching runtime and OS execution permissions.')
    if sys.platform != 'darwin':
        add('Native desktop', 'unavailable', 'The current native adapter requires macOS; browser tools are separate.')
    elif importlib.util.find_spec('ApplicationServices') is None:
        add('Native desktop', 'missing', 'Install the desktop extra in Kestrel’s Python environment.')
    else:
        try:
            from ApplicationServices import AXIsProcessTrusted
            trusted = bool(AXIsProcessTrusted())
            add('Desktop Accessibility', 'ready' if trusted else 'missing',
                'Current process has OS permission; the server host may differ. App control was not exercised.' if trusted else
                'Enable Accessibility for the process hosting desktop-server in System Settings. No permission was changed.')
        except Exception:
            add('Desktop Accessibility', 'unavailable', 'The macOS permission query failed; no app was inspected.')
    return checks
