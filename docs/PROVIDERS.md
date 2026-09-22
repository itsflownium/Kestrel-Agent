# Provider setup and Jev credentials

Run `kestrel providers` to see named setups. Select a generation provider with an exact model ID available to your account:

```sh
kestrel provider deepseek --model YOUR_MODEL_ID
kestrel provider mimo --model YOUR_MODEL_ID
kestrel provider anthropic --model YOUR_MODEL_ID
kestrel provider moonshot --model YOUR_MODEL_ID
kestrel provider glm --model YOUR_MODEL_ID
kestrel provider poolside --model YOUR_MODEL_ID
```

Setup asks for the provider API key when missing. In **Jev mode**, it also asks for the Jev API key; **standard mode does not require or call Jev**. Inputs are hidden and saved or environment-provided keys are reused. Skipping a required key leaves that service unavailable. Use `/mode standard` for the main model alone, or `/mode jev` to enable Jev decisions.

Inside the terminal, `/provider poolside` (or another name) asks for an editable base URL and model ID, then missing keys. `/provider` lists all names. `/model` lists model IDs from the active service when supported; `/model EXACT_ID` selects one. There is no hardcoded model catalog. `/model jev-key` and `/model provider-key` replace keys privately.

To store credentials separately without switching the current model:

```sh
kestrel auth provider deepseek
kestrel auth poolside
kestrel auth jev
```

`kestrel auth login` retains the official Codex OAuth flow. A Jev key is needed only when Jev mode is enabled. Other providers use API keys. No consumer-account OAuth is assumed for those services.

## Named setups

| Name | Default base URL | Key environment variable | Official reference |
| --- | --- | --- | --- |
| codex | Codex-managed OAuth | — | Existing bundled Codex SDK |
| openai | https://api.openai.com/v1 | OPENAI_API_KEY | [API reference](https://platform.openai.com/docs/api-reference/chat) |
| deepseek | https://api.deepseek.com | DEEPSEEK_API_KEY | [Quickstart](https://api-docs.deepseek.com/) |
| mimo | https://api.xiaomimimo.com/v1 | MIMO_API_KEY | [First API call](https://mimo.mi.com/docs/en-US/quick-start/summary/first-api-call) |
| anthropic | https://api.anthropic.com/v1 | ANTHROPIC_API_KEY | [Messages](https://platform.claude.com/docs/en/api/messages) |
| moonshot | https://api.moonshot.ai/v1 | MOONSHOT_API_KEY | [Kimi platform](https://platform.kimi.ai/docs/overview) |
| glm | https://api.z.ai/api/paas/v4 | ZAI_API_KEY | [API introduction](https://docs.z.ai/api-reference/introduction) |
| glm-coding | https://api.z.ai/api/coding/paas/v4 | ZAI_API_KEY | [Coding configuration](https://zcode.z.ai/en/docs/configuration) |
| poolside | https://inference.poolside.ai/v1 | POOLSIDE_API_KEY | [Official integration](https://github.com/poolsideai/n8n-poolside-node) |
| groq | https://api.groq.com/openai/v1 | GROQ_API_KEY | [Compatibility](https://console.groq.com/docs/openai) |
| mistral | https://api.mistral.ai/v1 | MISTRAL_API_KEY | [API reference](https://docs.mistral.ai/api) |
| openrouter | https://openrouter.ai/api/v1 | OPENROUTER_API_KEY | [Quickstart](https://openrouter.ai/docs/quickstart) |
| openai-compatible | Editable; defaults to OpenAI API | KESTREL_MODEL_API_KEY | Your compatible server's documentation |

Aliases include `xiaomi`/`xiaomei` → `mimo`, `kimi` → `moonshot`, `zai`/`z.ai` → `glm`, `claude` → `anthropic`, and `custom` → `openai-compatible`.

All endpoints can be overridden using `--base-url` or the interactive prompt. Use the endpoint appropriate to your account, region, deployment, and subscription. MiMo Token Plan and GLM Coding Plan credentials/endpoints can differ from general API access. A custom localhost HTTP server may omit its provider key; optional Jev mode needs its own key.

MiMo uses the `api-key` header and `max_completion_tokens`. OpenAI uses `max_completion_tokens`; other compatible presets default to `max_tokens`. Anthropic uses native Messages with `x-api-key`; other listed services use Chat Completions with Bearer authentication. Advanced configuration can override these fields. JSON-schema support differs across models, so setup defaults to a prompted schema with local validation instead of assuming native structured-output support.

Keys are stored in owner-only files in Kestrel's private data directory, separate from project files. Provider credentials are scoped by protocol and endpoint; the configured environment variable takes precedence. Changing providers resets the key variable, header, token field, JSON mode, and model selection. Known provider credential variables are removed from sandbox command environments. Never supply keys as model IDs or command arguments.

## Validation and current limits

Mocked transport tests cover every HTTP preset, headers, paths, model IDs, and token fields. CLI tests cover hidden input, missing Jev prompts, saved-key reuse, custom endpoints, and Poolside authentication without changing the active model. Interactive startup checks cover missing versus configured keys. A real pseudo-terminal smoke check also verified hidden Jev entry under `TERM=dumb`, clean exit, and saved-key reuse on restart. These tests do not demonstrate that every account/model works live: only Codex/Jev were available for live tests.

Generation uses the selected service. Shell execution continues to use the bundled Codex sandbox runtime; native research and the current MCP bridge remain Codex-only. Provider selection is not an assertion of feature parity across APIs.
