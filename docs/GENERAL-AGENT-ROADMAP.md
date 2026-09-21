# General CLI agent: research and implementation direction

Research date: 2026-09-21. Requested direction: make Kestrel a general terminal agent with API-provider choice, portable skills, useful commands, and optional Jev assistance. This extends the architecture checklist; it does not replace unfinished recovery, workflow, or evaluation work. Features below are proposed unless explicitly marked current.

## Findings from official sources

Hermes uses on-demand skill documents, automatic skill slash commands, progressive loading of supporting references, and standard SKILL.md packages. Its documented implementation also includes skill installation, source/hash tracking, project trust, scanning, staged skill updates, and learning from supplied materials. These are existing capabilities, not novel differentiators we should claim. [Hermes skills documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)

Hermes exposes commands for models, tools, skills, sessions, background work, and interaction during an active task. We should adopt a discoverable command surface without making a large inventory the startup screen's primary content. [Hermes command reference](https://hermes-agent.nousresearch.com/docs/reference/slash-commands), [CLI documentation](https://hermes-agent.nousresearch.com/docs/user-guide/cli)

The open Agent Skills format separates metadata and Markdown instructions from optional scripts, references, and assets. Implement that format first; place Kestrel-specific executable contracts in an optional sidecar so ordinary skills remain usable. A portable instruction package does not guarantee its referenced tools exist on every host. [Agent Skills specification](https://agentskills.io/specification)

## Current Kestrel gaps found in source

- Generation already supports Codex OAuth, OpenAI-compatible API providers, and Anthropic. Provider presets are not evidence of live compatibility with every model.
- `Judge` always calls Jev, and setup/UI assume a Jev credential. This prevents a true single-provider experience.
- `Runtime` owns generation, terminal execution, research, and MCP integration. Shell execution still uses the Codex app-server path even with API-based generation; native research/MCP are Codex-specific. Selecting another model is not yet independent of that execution dependency.
- Workflow memory stores searchable Markdown recipes, not a complete portable skill registry or independently validated executable workflows.
- Slash commands cover basic model/session/settings operations but lack skill discovery, invocation, version inspection, mode switching, and general capability diagnostics.
- Exact completion checks, durable evidence, source hashes, bounded concurrency, and permissions provide useful foundations for general tasks. They do not prove overall superiority.

## Product and architecture decisions

### Separate model choice from agent mode

Proposed commands:

- `/model`: choose provider/model and privately configure its API key or supported OAuth.
- `/mode standard`: the selected main model handles planning and semantic decisions; no Jev credential or Jev request.
- `/mode jev`: the same capabilities and permissions, with Jev handling bounded choices, applicability checks, and verification decisions.
- `/mode` with no argument: show active mode, decision provider, and any setup requirement.

Use standard mode as the proposed default for new installs. Preserve existing users' Jev behavior through an explicit migration rather than silently changing their configuration. Do not add an automatic mode until matched-task evidence identifies when Jev improves quality, latency, or cost. Jev cannot replace arbitrary generation or share another provider's decoding state. All modes retain deterministic completion checks and controller-owned permissions.

### Provider-independent capability boundaries

The controller owns the task ledger, scheduling, permissions, budgets, recovery, and evidence. Separate interfaces cover `Generator`, `DecisionService`, `ExecutionBackend`, `ToolRegistry`, `SkillRegistry`, and `MemoryStore`. Provider choice must not imply a tool exists. Advertise tested capabilities and unavailable dependencies truthfully.

Add an explicitly configured execution backend independent of the generator. Preserve the existing Codex backend until a replacement meets cancellation, working-directory, credential isolation, timeout, output-bound, and permission tests. An unrestricted subprocess backend must not be described as equivalent to an OS sandbox. Web search, browser automation, document operations, and MCP need explicit adapters, not model-specific prompt promises.

### Skills with measurable quality

Implement ordinary Agent Skills packages first, with metadata-only discovery, bounded on-demand loading, declared dependencies, explicit invocation, collision handling, and provenance. Proposed commands: `/skills`, `/skills search`, `/skills show`, `/skills use`, `/skills test`, `/skills versions`, and `/skills rollback`. Add direct `/<skill-name>` aliases without allowing skills to shadow built-in commands.

An optional Kestrel sidecar should define typed parameters, prerequisites, supported tools, output contracts, and isolated test fixtures. It is an extension, not a new required format. Missing capabilities produce a clear abstention/setup explanation. Instructions cannot grant permissions or silently install/run scripts.

Learning produces a candidate version with a diff, provenance, and evaluation report. Promote only after independent tests with new parameters and negative applicability cases; keep rollback versions. Label observed success separately from user satisfaction, model judgment, and unverified claims. Learned workflows must not copy instance secrets or hardcode fixture answers. Reuse the current completion-contract and held-out-promotion foundations, but do not treat successful prompt evaluation as skill validation.

This is the proposed differentiator: users can inspect evidence that a particular skill version works for a stated scope on a particular capability set. Whether it outperforms Hermes must be measured, not inferred from this design.

### General-purpose UX and memory

Start with a compact header showing the selected model/provider, mode, working directory, and ready/disabled tool and skill counts. Provide `/help` search and completion, `/tools` dependency diagnostics, `/memory` inspect/edit/forget, `/sessions`, `/resume`, `/plan`, `/status`, `/cancel`, and `/exit`. Preserve idle Ctrl+C exit and active-task cancellation. Add background work and steering only after ownership and cancellation semantics are tested.

Keep task evidence, durable user preferences, retrieved knowledge, and procedural skills separate. Store provenance and freshness rules. Do not treat old source snapshots as current facts or inject the full memory/skill library into every model call.

Initial skill families should cover research with citations, documents/PDFs, CSV/JSON/spreadsheets, file organization, meeting-note extraction, and software work. Use installed capabilities rather than promising unavailable browser, calendar, email, or desktop access.

## Ordered deliverables and acceptance evidence

1. Finish and publish current recovery work. Preserve regression traces and distinguish completed historical work from current artifacts.
2. Implement standard/Jev mode abstraction and private credential setup. Prove standard mode runs with no Jev credential/client calls, mode changes persist, invalid decisions fail closed, cancellation closes both providers, and telemetry attributes costs correctly.
3. Build portable skill registry, invocation, reference loading, and CLI discovery. Test malformed metadata, collisions, path traversal, changed package content, missing dependencies, explicit invocation, and bounded context loading.
4. Add versioned skill candidates and executable sidecars with isolated tests, promotion, and rollback. Verify unseen parameters, negative applicability, partial failure, and no repeated completed effects.
5. Separate execution and general tool adapters from generation. Run the same conformance suite on each supported backend/provider combination before claiming support.
6. Improve terminal layout and interaction around real capabilities. Verify narrow terminals, long model names, interrupted work, missing keys, and skill errors.
7. Freeze a general-task evaluation set. Compare Kestrel standard, Kestrel Jev, and Hermes using the same model/settings/tools/data wherever supported. Include research correctness/citations, document content and render checks, data accuracy, file-change scope, resumption, and prompt-injection cases. Report failures, repeated-trial distributions, wall time, tool calls, and priced token usage; mark unavailable prices rather than inventing savings.

General-agent work will ship in successive reviewable PRs. The broader goal remains open until implementation and matched-scope evidence support completion. No model-weight training is required.

## UI research update

OpenCode documents discoverable slash commands, toggled tool details, file references and session switching; Aider documents concise command-driven interaction and explicit context control. Use those interaction patterns as inspiration for a compact Kestrel dashboard and searchable commands, with its own teal/slate visual language. Do not copy Hermes's large banner or dense inventory. [OpenCode TUI](https://opencode.ai/docs/tui/), [Aider commands](https://aider.chat/docs/usage/commands.html).

## Codex and Claude Code research; expanded coverage

Codex documents metadata-first skill discovery with full instructions loaded when needed. Claude Code documents explicit-only skill invocation and separate filesystem/network sandbox controls. Adopt progressive loading and make invocation/permission boundaries explicit; do not silently emulate vendor-specific permission grants or command interpolation. Sources: [Codex skills](https://learn.chatgpt.com/docs/build-skills), [Claude Code skills](https://code.claude.com/docs/en/skills), [Claude Code sandboxing](https://code.claude.com/docs/en/sandboxing).

The user's further request includes first-run model/auth/mode/execution setup, Docker as a real execution backend, and broad terminal-coding/computer-use/workflow capabilities. These extend the pending scope. Desktop and browser work require explicit observation/action adapters, application/account permissions, recovery from stale UI state, and outcome evidence. Skills cannot create those capabilities by mentioning them. Keep computer-use setup unavailable until a working adapter is configured.

Evaluation must separately cover: multi-file coding with hidden tests; terminal recovery and cancellation; browser form/navigation tasks in isolated test sites; desktop document interaction in disposable fixtures; parameterized multi-step workflows with partial failure; research citation support; document rendering/content; and data transformations. Compare matching model/provider settings and tool access where possible, publish failures, and avoid extrapolating a win in one category to all tasks.
