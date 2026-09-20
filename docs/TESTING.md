# Owner-controlled acceptance guide

The owner authorized testing on September 20, 2026. Thirty-five offline checks pass. Terminal startup, `/help`, and exit were exercised in a PTY with isolated session storage. Live comparisons ran using GPT-6-Astra medium and Jev, including renamed schemas, changed data, no-match cases, and open-ended fallback. See `benchmarks/README.md` for results and limitations. The remaining checklist below is not yet fully executed. No automatic test workflow is configured.

## Local checks

1. Type `kestrel` in a new terminal. Check the banner, prompt, status bar, completion, multiline input, `/help`, and exit at narrow/wide sizes.
2. Run `kestrel doctor`. Confirm managed storage below 3 GB and that secrets are shown only as configured/missing.
3. Run `kestrel doctor --online` when ready for authentication checks.
4. Run `uv run --extra dev pytest` for offline contracts.

## End-to-end scenarios

- General chat: Jev routing, one Codex call, no unnecessary tool loop.
- Select relevant documents and summarize them; inspect Jev choices and evidence references.
- Create, read, and revise a small file; require the observed hash for replacement.
- Request harmless commands; decline one and allow another; inspect output.
- Interrupt a long command, exit, resume, and confirm uncertain effects cannot silently rerun.
- Attempt an outside-root write under read-only/workspace profiles.
- A failed command must never be reported as successful.
- Research a topic with citations; `network=false` must block network tools.
- Discover a configured MCP server and exercise a read. Use disposable accounts for effects.
- Learn, review, activate, and reuse a workflow with fresh inputs.
- Run a small GEPA experiment on separate train/validation examples; ensure the candidate remains inactive and no task tools execute.

## Evaluation

Compare identical tasks against Codex alone with the same model, effort, tools, and permissions. Record success, median/p95 latency, generation tokens/calls, Jev tokens, and retries. Include initial planning/final generation and keep held-out cases for learned changes.

Runtime areas still requiring validation: Codex sandbox compatibility, inherited MCP settings, terminal rendering/cancellation, provider schemas, and the full GEPA path. Source inspection and package installation do not prove these work.

Provider additions: mocked OpenAI-compatible/Anthropic requests, controller dispatch without Codex startup, per-endpoint credential isolation, HTTP error redaction, and truncated-output rejection pass. A PTY smoke check verified masked Jev key entry and provider configuration with dummy credentials. No live third-party generation credentials were available.
