"""Named setups over protocol adapters; model IDs remain user-selected."""
from dataclasses import dataclass

from .config import Settings


@dataclass(frozen=True)
class Preset:
    label: str
    base_url: str | None
    key_env: str
    protocol: str = "openai-compatible"
    auth_header: str = "authorization"
    token_parameter: str = "max_tokens"


PRESETS = {
    "codex": Preset("Codex (OAuth)", None, "KESTREL_MODEL_API_KEY", "codex"),
    "openai-compatible": Preset("Custom / local OpenAI-compatible", "https://api.openai.com/v1", "KESTREL_MODEL_API_KEY"),
    "openai": Preset("OpenAI API", "https://api.openai.com/v1", "OPENAI_API_KEY", token_parameter="max_completion_tokens"),
    "deepseek": Preset("DeepSeek", "https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "mimo": Preset("Xiaomi MiMo", "https://api.xiaomimimo.com/v1", "MIMO_API_KEY", auth_header="api-key", token_parameter="max_completion_tokens"),
    "anthropic": Preset("Anthropic", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY", "anthropic"),
    "moonshot": Preset("Moonshot / Kimi", "https://api.moonshot.ai/v1", "MOONSHOT_API_KEY"),
    "glm": Preset("GLM / Z.ai API", "https://api.z.ai/api/paas/v4", "ZAI_API_KEY"),
    "glm-coding": Preset("GLM / Z.ai Coding Plan", "https://api.z.ai/api/coding/paas/v4", "ZAI_API_KEY"),
    "poolside": Preset("Poolside", "https://inference.poolside.ai/v1", "POOLSIDE_API_KEY"),
    "groq": Preset("Groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "mistral": Preset("Mistral", "https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    "openrouter": Preset("OpenRouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
}
ALIASES = {"xiaomi": "mimo", "xiaomei": "mimo", "kimi": "moonshot", "zai": "glm",
           "z.ai": "glm", "zhipu": "glm", "claude": "anthropic", "poolside-ai": "poolside", "custom": "openai-compatible"}


def select(settings: Settings, name: str, *, base_url: str | None = None, model: str | None = None) -> Settings:
    name = ALIASES.get(name.strip().lower(), name.strip().lower())
    if name not in PRESETS:
        raise ValueError("Unknown provider. Choose: " + ", ".join(PRESETS))
    preset = PRESETS[name]
    values = settings.model_dump()
    values.update(provider=preset.protocol, provider_profile=name,
                  provider_base_url=base_url or preset.base_url, provider_api_key_env=preset.key_env,
                  provider_auth_header=preset.auth_header, provider_token_parameter=preset.token_parameter,
                  provider_json_mode="prompt", provider_send_reasoning_effort=False, model=model)
    candidate = Settings.model_validate(values)
    if candidate.provider != "codex":
        from .generation import endpoint
        endpoint(candidate)
    return candidate


def label(settings: Settings) -> str:
    preset = PRESETS.get(settings.provider_profile or "")
    return preset.label if preset and preset.protocol == settings.provider else settings.provider


def credential_envs(settings: Settings) -> set[str]:
    return {"TYPESAFE_API_KEY", "CODEX_API_KEY", settings.provider_api_key_env} | {p.key_env for p in PRESETS.values()}
