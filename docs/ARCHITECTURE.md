# Implementation boundaries

`engine.py` owns task state; `providers.py` contains Codex/Jev compatibility; `tools.py` executes permitted operations; `store.py` owns evidence; `ui.py` owns interaction. The engine can run independently of the UI.

## Runtime

1. Load recent conversation and matching active workflow recipes.
2. Ask Codex for `answer`, `clarify`, or a DAG of registered actions. Validate IDs, dependencies, cycles, and result references.
3. Ask Jev about ready actions. It may execute, skip, or request context. Candidate selection can use values returned by prior tools.
4. Resolve `${action_id.field}` in code; enforce access; save in-flight checkpoints.
5. Parallelize independent reads. Serialize effects and generation.
6. Store originals with evidence IDs; include bounded excerpts in prompts. Retrieve omitted detail through `read_evidence`.
7. Check explicit criteria with Jev. Errors override optimistic judgments. Replan when necessary.
8. Generate a grounded answer and check its claims about execution. Unsupported claims trigger a bounded revision.

Arguments are JSON strings inside the strict plan schema because arbitrary tool-specific objects otherwise require enumerating every connected schema. They are decoded as JSON, validated by the selected tool, and never evaluated as code. Commands use argv arrays.

## Runtime compatibility and authentication

The official `openai-codex==0.154.0` package supplies a pinned runtime. Its private JSON-RPC client is accessed in one adapter for direct command/MCP methods missing from the high-level API. Upgrades must review that boundary against SDK source.

Codex owns OAuth and refresh. Generation threads are ephemeral and read-only; shell, code-mode, connected apps, and MCP are disabled. Research may use web search. Direct command/MCP execution does not require a generation turn.

The SDK's default handler accepts certain approval requests; Kestrel explicitly replaces it. Model-requested command/file escalation is declined. Connected approval questions are shown to the user. Unsupported forms are declined.

## Interruption and evidence

Commit an in-flight checkpoint before effects, then record results. Reject repeated identical effects within the same task. Interrupted or transport-failed effects have uncertain outcomes and need explicit permission before retrying. A crash after an effect but before its result never proves the action did not happen.

Ctrl+C cancels the controller job, interrupts the Codex turn, and terminates tracked commands. Resume restores the checkpoint without silently replaying uncertain effects.

## Configuration and learning

Configuration is outside task workspaces. No project `.env` is implicitly loaded. Jev's key loads from the environment/private secret file and is cleared from the Codex subprocess environment. Logs redact known token formats.

Profiles control file checks and command sandboxing; roots are canonicalized; replacements require content hashes. These controls are not an OS disk quota or a read boundary for user-authorized unrestricted commands.

Workflow learning creates inactive recipes from completed traces. GEPA uses a custom evaluator and Codex reflection callable to modify question text, not model weights. It uses supplied examples and never task tools. Promotion is explicit and should follow held-out evaluation. No unmeasured performance gains are claimed.
