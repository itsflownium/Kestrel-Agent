"""App-scoped macOS Accessibility tools; no global mouse or keyboard control."""
from __future__ import annotations
import asyncio
import os
import re
import secrets
import sys
import time
import uuid
from typing import Any


class MacAccessibility:
    def __init__(self, bundle_id):
        if sys.platform != 'darwin':
            raise RuntimeError('This adapter requires macOS; configure another desktop MCP adapter on other systems.')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{2,199}', bundle_id):
            raise ValueError('Provide an exact application bundle identifier.')
        try:
            import ApplicationServices as AX
            from AppKit import NSRunningApplication
        except ImportError as error:
            raise RuntimeError('Install the desktop extra to use macOS Accessibility.') from error
        self.ax, self.apps, self.bundle_id = AX, NSRunningApplication, bundle_id

    def application(self):
        if not self.ax.AXIsProcessTrusted():
            raise PermissionError('macOS Accessibility access is not authorized for this process. Enable it in System Settings before native desktop use.')
        apps = self.apps.runningApplicationsWithBundleIdentifier_(self.bundle_id)
        if len(apps) != 1:
            raise ValueError('The configured app must have exactly one running instance. Open it yourself and observe again.')
        pid = int(apps[0].processIdentifier())
        root = self.ax.AXUIElementCreateApplication(pid)
        self.ax.AXUIElementSetMessagingTimeout(root, 2.0)
        return pid, root

    def attribute(self, element, name):
        error, value = self.ax.AXUIElementCopyAttributeValue(element, name, None)
        return value if error == 0 else None

    def describe(self, element):
        error, pid = self.ax.AXUIElementGetPid(element, None)
        if error:
            return None
        role = self.attribute(element, 'AXRole')
        subrole = self.attribute(element, 'AXSubrole')
        secure = role == 'AXSecureTextField' or subrole == 'AXSecureTextField'
        error, actions = self.ax.AXUIElementCopyActionNames(element, None)
        error_set, settable = self.ax.AXUIElementIsAttributeSettable(element, 'AXValue', None)
        value = None if secure else self.attribute(element, 'AXValue')
        return {'pid': int(pid), 'role': str(role or ''), 'subrole': str(subrole or ''),
                'label': str(self.attribute(element, 'AXTitle') or self.attribute(element, 'AXDescription') or '')[:500],
                'value': value[:1000] if isinstance(value, str) else value if isinstance(value, (int, float, bool)) else None,
                'enabled': bool(self.attribute(element, 'AXEnabled')),
                'secure': secure, 'pressable': error == 0 and 'AXPress' in (actions or []),
                'settable': error_set == 0 and bool(settable) and not secure}

    def scan(self):
        pid, root = self.application()
        queue, nodes, seen = [(root, 0)], [], set()
        truncated = False
        deadline = time.monotonic() + 8
        while queue and len(nodes) < 200 and time.monotonic() < deadline:
            element, depth = queue.pop(0)
            identity = hash(element)
            if identity in seen:
                continue
            seen.add(identity)
            info = self.describe(element)
            if info is None or info['pid'] != pid:
                continue
            nodes.append((element, info))
            if depth < 10:
                # Bounded retrieval avoids materializing an unbounded AXChildren array.
                error, count = self.ax.AXUIElementGetAttributeValueCount(element, 'AXChildren', None)
                if error == 0 and count:
                    truncated = truncated or count > 200
                    error, children = self.ax.AXUIElementCopyAttributeValues(element, 'AXChildren', 0, min(count, 200), None)
                    if error == 0:
                        queue.extend((child, depth + 1) for child in (children or [])[:200])
            else:
                truncated = True
        return pid, nodes, bool(queue) or truncated

    def press(self, element):
        error = self.ax.AXUIElementPerformAction(element, 'AXPress')
        if error:
            raise RuntimeError(f'Accessibility press returned error {error}; inspect the outcome before retrying.')

    def fill(self, element, value):
        error = self.ax.AXUIElementSetAttributeValue(element, 'AXValue', value)
        if error:
            raise RuntimeError(f'Accessibility value update returned error {error}; inspect the outcome before retrying.')


class DesktopAdapter:
    def __init__(self, backend):
        self.backend, self.lock = backend, asyncio.Lock()
        self.observation, self.pid, self.targets = None, None, {}

    def _observe(self):
        pid, nodes, truncated = self.backend.scan()
        self.pid, self.observation = pid, uuid.uuid4().hex
        self.targets = {f'e{i+1}': (element, info) for i, (element, info) in enumerate(nodes)}
        return {'app': self.backend.bundle_id, 'pid': pid, 'observation': self.observation,
                'targets': [{'target':key, **info} for key, (_, info) in self.targets.items()],
                'truncated': truncated, 'scope':'Configured application accessibility tree only; no global desktop access.'}

    async def _dispatch(self, function, *args):
        await self.lock.acquire()
        task = asyncio.create_task(asyncio.to_thread(function, *args))
        def finished(future):
            self.lock.release()
            if not future.cancelled():
                future.exception()  # Consume errors even if the requester disconnected.
        task.add_done_callback(finished)
        # Cancellation cannot abort an OS accessibility call. Keep the lock owned
        # by its task until it finishes; another request must not overlap it.
        return await asyncio.shield(task)

    async def observe(self):
        return await self._dispatch(self._observe)

    def _act(self, observation, target, operation, value):
        if observation != self.observation or target not in self.targets:
            raise ValueError('Stale or unknown target. Observe the configured app again.')
        element, original = self.targets[target]
        pid, nodes, _ = self.backend.scan()
        current = next((info for node, info in nodes if node == element), None)
        if pid != self.pid or current != original:
            raise ValueError('Application or target changed. Observe again before acting.')
        if not current['enabled'] or current['secure']:
            raise PermissionError('Disabled and secure fields cannot be operated by this adapter.')
        if operation == 'press' and not current['pressable']:
            raise ValueError('Target does not expose a press action.')
        if operation == 'fill' and not current['settable']:
            raise ValueError('Target does not expose a writable value.')
        self.observation = None  # Consume before dispatch, including ambiguous failures.
        if operation == 'press':
            self.backend.press(element)
        else:
            self.backend.fill(element, value)
        return self._observe()

    async def act(self, observation, target, operation, value=''):
        if operation not in {'press', 'fill'} or not isinstance(value, str) or len(value) > 4000:
            raise ValueError('Use press or fill with a value no longer than 4000 characters.')
        return await self._dispatch(self._act, observation, target, operation, value)


def create_desktop_server(bundle_id, token, port=8932, backend=None):
    from mcp.server.fastmcp import FastMCP
    from mcp.server.auth.provider import AccessToken
    from mcp.server.auth.settings import AuthSettings
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', token):
        raise ValueError('Set KESTREL_DESKTOP_TOKEN to a private random token of at least 32 characters.')
    resource = f'http://127.0.0.1:{port}/mcp'
    class Verifier:
        async def verify_token(self, candidate):
            if isinstance(candidate, str) and len(candidate) <= 256 and secrets.compare_digest(candidate.encode(), token.encode()):
                return AccessToken(token=candidate, client_id='local-desktop', scopes=['desktop'], resource=resource)
            return None
    adapter = DesktopAdapter(backend or MacAccessibility(bundle_id))
    server = FastMCP('Kestrel Desktop', host='127.0.0.1', port=port, json_response=True,
        token_verifier=Verifier(), auth=AuthSettings(issuer_url=f'http://127.0.0.1:{port}',
            resource_server_url=resource, required_scopes=['desktop'], validate_token_resource=True))
    @server.tool()
    async def desktop_observe() -> dict[str, Any]:
        """Observe the explicitly configured application; requires macOS Accessibility permission."""
        return await adapter.observe()
    @server.tool()
    async def desktop_act(observation: str, target: str, operation: str, value: str = '') -> dict[str, Any]:
        """Press or fill an observed app element, then re-observe. Stale, disabled, and secure targets fail."""
        return await adapter.act(observation, target, operation, value)
    return server


def serve_desktop(bundle_id, port=8932):
    create_desktop_server(bundle_id, os.environ.get('KESTREL_DESKTOP_TOKEN', ''), port).run(transport='streamable-http')
