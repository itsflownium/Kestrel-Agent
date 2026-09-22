# Implementation boundaries

`engine.py` owns task state; `providers.py` contains Codex/Jev compatibility; `tools.py` executes permitted operations; `store.py` owns evidence; `ui.py` owns interaction. The engine can run independently of the UI.

## Runtime

1. Load recent conversation and matching active workflow recipes.
2. Ask Codex for `answer`, `clarify`, or a DAG of registered actions. Validate IDs, dependencies, cycles, and result references.
3. Ask Jev about ready actions. It may execute, skip, or request context. Candidate selection can use values returned by prior tools.
4. Resolve `${action_id.field}` in code; enforce access; save in-flight checkpoints.
5. Parallelize independent reads. Serialize effects and generation.
6. Store originals with evidence IDs; include bounded excerpts in prompts. Retrieve omitted detail through `read_evidence`.
7. Check the original task and explicit criteria with Jev. Unresolved errors require replanning; a definite failure may be considered recovered only when subsequent execution evidence supports it.
8. If a completed tool result is the entire requested answer, Jev may approve returning it directly. Otherwise generate a grounded answer and check its claims about execution. Unsupported claims trigger a bounded revision.

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

## Verified result reuse and failure branches

Plans can declare `final_response_ref`, a whole-value reference to a declared action. The controller requires successful execution, binds the value without evaluation, and limits the candidate to 12,000 characters. Jev checks the original task, all completion criteria, and exact candidate formatting in one batch. Only a supported candidate can bypass final generation; missing fields, rejection, or incomplete work fall back to the existing generation/replanning path. Table results provide `json_content` with numeric JSON values without converting Decimal totals to binary floats.

Actions default to `after=success`. `after=failure` runs a recovery branch after a definite dependency error, while `after=completion` permits inspection after either outcome. Skipped branches propagate skips instead of creating spurious errors. Uncertain outcomes do not enable an automatic failure retry; completion actions directly dependent on uncertain outcomes are restricted to read tools. Existing uncertain-effect fingerprint checks remain in place.

Evidence now includes the executing tool, bound argument excerpts, and execution status alongside results. Older checkpoints without these fields remain readable. This gives Jev more execution context, but command arguments alone do not prove absence of side effects. The live recovery benchmark still shows unnecessary work, so minimal repair and broader interruption testing remain unfinished.

## Jev-driven grouped table path

For one explicitly named CSV/JSON file of at most 12 KB and 64 object rows, the router may offer grouped numeric aggregation. Jev selects an enumerated operation, source-derived columns, and up to three AND predicates. Options use only literal categorical values present in both the input and request, plus numeric thresholds parsed from the request. At most 16 common columns, 8 thresholds, and 64 predicate choices are offered; larger or incompatible queries fall back to general planning.

The ordinary permission-checked `query_table` computes the result. A fresh source read must match the original SHA256. A separate Jev call checks the chosen query, all source records, result metadata, and exact JSON answer against the whole request before returning it. Joins, OR predicates, external facts, file edits, missing options, explanations, changed sources, and rejected checks fall back. This avoids all generation calls for supported requests; it does not broaden Jev into an arbitrary text/code generator or promise that semantic checks are infallible.

The new path has independent schema/filter/source-change tests and live sum/mean/count comparisons. The benchmark fixtures are not imported by the application. A new table-with-write task checks that required file creation reaches the general controller.

## Initial source evidence

When a new request leaves the bounded fast paths, the controller inspects at most four explicitly named small local text/code/data files before planning. Existing files up to 12 KB use the normal permission-checked reader; absent destinations receive an observed existence record. This exposes source content and hashes to the first plan and avoids inspection-only planning turns. Known script extensions are not prefetched when the request contains run/execute, preserving failure-inspection sequencing. Large, denied, unsupported, and unreadable paths remain for the normal controller to handle.

This evidence does not authorize writes or prove effects occurred. Existing-file writes still require a matching observed hash, and an absent destination is checked again by write_file. A direct answer following inspection must pass both original-task completion and answer-support/format questions in the same Jev call. Initial reads count toward the action budget and reserve a step for the normal controller; unsupported output claims cause replanning rather than being treated as completion.

Plans are also instructed to bind already-produced text directly into downstream tools: numeric JSON from query_table can be written without another generation call. These instructions are general; there are no workload-name checks in application code.

Write receipts now include previous_sha256 and a description of the precondition actually checked. Approval can leave a dialog open while another process edits or creates the target, so write_file rechecks existence/content after approval before replacing it. This narrows the race window but cannot provide an OS-level compare-and-swap against concurrent writers. Short self-contained new content may be embedded directly in a plan's arguments; execution, permissions, and hash guards remain in the controller.

## Evidence-derived final answers

When the plan does not supply a usable `final_response_ref`, the controller offers Jev up to three bounded candidates from completed terminal actions: successful shell stdout or an execution receipt, table JSON, and generated content. It excludes results consumed by another completed action, failed/unknown command exits, known truncation, overlong output, and raw source-file text. Stderr is retained in receipts rather than silently omitted. Candidates contain actual tool results and resolved command arguments, not invented summaries.

Selection shares the existing completion-check request, so it adds no Jev round trip. Jev must select a candidate that meets the whole request and exact response format; `generate` remains an explicit option. Unfinished work, unrecovered errors, and failed completion criteria still force replanning regardless of candidate selection. Explicit plan references keep their existing verification path. Each successful reuse records its action/kind or explicit reference in the event log.

Generated final answers now pass a bounded two-attempt support/format review. A rejected draft may be revised once, and the revised answer is checked again before return. Answers beyond the 12,000-character review bound are revised rather than approved from only their prefix. If revision still cannot be verified, the task reports an error and retains its evidence/checkpoint for review or continuation. This closes a previously unreviewed revision path; Jev's support judgments remain fallible and do not establish general factual correctness.

## Requested evidence pages

An explicit `read_evidence` result now receives a contiguous `retrieved_page` view instead of being truncated again inside an evenly divided, doubly serialized result excerpt. The view identifies the original source evidence ID, source offset, visible end offset, and continuation offset. Continuation accounts for both the original tool page and context-budget omissions; it uses source character offsets even when JSON escaping or Unicode changes serialized size.

The newest distinct source/offset pages share at most 65% of the configured context character budget, measured as serialized JSON string content. Recent ordinary excerpts share the remainder of a 75% excerpt/page pool, so short pages return unused space to other observations. While requested pages are present, the historical index uses up to 10%; omitted index entries remain reported and searchable. Without requested pages, existing ordinary excerpt/index allocations remain unchanged. These are packing budgets; request, requirement, receipt and metadata overhead still exists. When retrieved-page metadata would exceed the provider decision-context limit, older observation views are omitted with an explicit count. Historical storage, all requirements/receipts and the newest observation remain intact. Essential state that still cannot fit receives the existing provider size error.

Historical records are never rewritten, retrieval is never promoted into proof of an external effect, and original invocation status/result receipts remain necessary for completion. Pages too large to fit remain explicitly incomplete. These rules apply to all tasks and contain no benchmark-specific names, answers or model IDs.

## Tool-result reference contracts

The planner receives the actual `load_skill` output fields and binds procedural text through `guidance`. Missing result fields and invalid list/scalar traversal produce bounded diagnostics naming the attempted reference and available structure, without including result values. Binding errors occur before tool dispatch; they cannot create a file or establish a completed/uncertain effect by themselves. The controller records the failed invocation and leaves recovery to an explicit valid plan.

Dependency validation walks decoded JSON argument values, as binding does. Unicode escapes therefore cannot hide a reference to an undeclared dependency. Dictionary keys remain literal. Existing valid bindings preserve their types and negative list indices; unknown names are not guessed or replaced automatically.

### Completion-review evidence capacity

Before semantic completion review, the controller uses spare space within the existing decision-state limit to expand complete retained argument/result excerpts. Source observations and executed-tool details precede generated proposals. Expansion includes serialized Unicode/escaping cost and retains original execution statuses, receipts and evidence IDs. Explicit evidence pages keep their pagination fields. Text that cannot fit remains explicitly truncated and retrievable. This can increase review input tokens; it does not waive deterministic checks, semantic review, final-answer review, or the provider's oversized-state rejection.
