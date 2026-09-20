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

## Jev-led fast paths

Every new request first goes through a bounded Jev routing question. Supported single-expression arithmetic is computed with a bounded Decimal parser (no eval, no silent recurring-decimal rounding). For an explicitly named small JSON array, the existing permission-checked reader supplies candidate records. Jev selects a route, candidate, response shape, and requested fields in one batched call. Field options come from the source schema, not domain-specific names. A separate Jev call checks the result against all candidates and the requested fields before deterministic rendering.

No-match responses require an explicit supported response marker in the user request and a separate check that zero candidates satisfy the constraints. Ambiguous/tied results, complex output requirements, unsupported files, or failed checks return to the normal Codex/controller loop. Provider errors are reported and fall back; this does not guarantee progress if later task decisions also need an unavailable Jev service.

These are generic, read-only capability recipes, not a lookup of task answers. They avoid a Codex planning/finalization round trip when generation is unnecessary. General tasks still incur routing overhead. Benchmark fixtures and grading criteria exist only under benchmarks/ and are never imported by application code. Learned workflow memory and offline GEPA remain separate, manually activated features.

## Generation-provider boundary

`Runtime.complete` dispatches to Codex OAuth or an HTTP generator. The HTTP generator supports OpenAI-compatible Chat Completions and Anthropic Messages, accepts arbitrary model IDs, and supplies the same controller-owned-action instructions and plan schema. It performs no model-side tool execution; the controller validates plans and executes authorized tools. Non-Codex usage is recorded as generation usage rather than incorrectly labeled Codex usage. Workflow learning and GEPA reflection reuse this boundary.

Codex remains the default and the local sandbox runtime dependency. Non-Codex generation does not start its app-server or require Codex authentication. Native research and MCP discovery are explicitly unavailable for HTTP providers rather than silently invoking a different model/account. HTTP model calls use configured credentials independently of task-tool network access.

API keys are private per-user files, scoped to protocol plus endpoint; an explicit environment override is supported. Codex OAuth uses the official SDK login and credential storage for each user. No shared OAuth client secret, shared account token, or Jev key is shipped in source. Password entry uses an explicit prompt-toolkit output to prevent its minimal-terminal echo shortcut from exposing input.

## Completion and table-workload revisions

Completion criteria now cover the original user request as well as the latest plan. A recovery plan that merely diagnoses a failure cannot finish a task that requires a successful rerun. Answer-only replans after tool execution also pass this guard. These are Jev judgments over recorded evidence, not infallible proofs; independent graders remain important.

Final-answer-only criteria can be deferred until generation, then checked in the final support/format review. Missing tool work cannot be deferred as presentation. The single-record fast path is unavailable when the request names multiple source files.

`query_table` is a permission-checked read tool over bounded CSV/JSON inputs. Operations and comparisons are enumerated; columns and filter values come from the request/plan. It never evaluates code. Decimal values are returned as strings with precision/rounding metadata, and invalid/missing rows are counted. Existing file/size limits and the operation's stricter row/group limits bound execution.
