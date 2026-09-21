"""Shared setup interview for the CLI and interactive terminal."""
from __future__ import annotations

from .config import Settings
from .provider_presets import PRESETS, select


async def configure(settings: Settings, ask, tell) -> Settings:
    """Collect into a copy; an interrupted interview never partially saves settings."""
    tell('Choose a model, decision mode, and where commands run. Keys are entered separately with hidden input.')
    tell('Providers: ' + ', '.join(PRESETS))
    provider = await ask('Provider', settings.provider_profile or settings.provider)
    current_provider = settings.provider_profile or settings.provider
    candidate = settings.model_copy(deep=True) if provider == current_provider else select(settings, provider)
    if candidate.provider != 'codex':
        from .generation import endpoint
        candidate.provider_base_url = await ask('API base URL', endpoint(candidate))
        endpoint(candidate)
    candidate.model = (await ask('Model ID (default uses provider default)', candidate.model or 'default')).strip()
    if candidate.model == 'default':
        candidate.model = None
    if candidate.provider != 'codex' and not candidate.model:
        raise ValueError('API providers require an exact model ID.')
    candidate.effort = await ask('Reasoning effort: low / medium / high', candidate.effort)
    candidate.agent_mode = await ask('Decision mode: standard / jev', candidate.agent_mode)
    tell('standard uses your selected model; jev uses Jev for structured decisions and needs its own key.')
    candidate.execution_backend = await ask('Command execution: codex / docker', candidate.execution_backend)
    if candidate.execution_backend == 'docker':
        candidate.docker_image = await ask('Docker image (must already be installed)', candidate.docker_image)
        tell('Docker mounts only this workspace. Containers are temporary; changes in the workspace persist. No automatic image pulls.')
    candidate.permission = await ask('File access: read-only / workspace / full', candidate.permission)
    network = await ask('Allow network: yes / no', 'yes' if candidate.network else 'no')
    if network not in {'yes', 'no'}:
        raise ValueError('Network must be yes or no.')
    candidate.network = network == 'yes'
    if candidate.permission == 'full' and not candidate.network and candidate.execution_backend == 'codex':
        raise ValueError('Use workspace access to disable network with Codex execution.')
    confirmation = await ask('Confirm shell commands: yes / no', 'yes' if candidate.confirm_shell else 'no')
    if confirmation not in {'yes', 'no'}:
        raise ValueError('Shell confirmation must be yes or no.')
    candidate.confirm_shell = confirmation == 'yes'
    return candidate
