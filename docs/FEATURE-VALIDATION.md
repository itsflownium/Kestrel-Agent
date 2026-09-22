# General-feature validation

Testing resumed after the user's explicit request to build and test the full system. The earlier implementation PRs retain their original untested-at-publication history.

- Existing suite: 260 passing tests, 54.19 seconds.
- Dashboard and terminal interruption: 7 passing focused tests. An initial 40-column footer wrap was fixed; all controls remain readable at tested widths of 40, 60, 80, 100, and 140 columns. Rich SVG output was rendered and visually inspected.
- Setup/workflow/execution/connection boundaries: added tests for interrupted setup leaving settings unchanged, API/Docker/Jev configuration, typed parameters, unknown parameters and tool names, cyclic dependencies, external schema restrictions, workspace-only Docker mounts, network disabling, no implicit pulls, endpoint credential restrictions, and pre-dispatch validation.
- Actual MCP transport: a temporary loopback FastMCP server exercised catalog discovery, a typed structured-output call, worker reuse, and shutdown. Initial execution was blocked by the filesystem/network sandbox; rerun with loopback permission passed. An initial fixture used an untyped dict return, which the SDK emitted without structuredContent; changing the fixture to an explicit result model exercised the intended structured-output path.

These tests do not establish external-provider quality, live Docker execution, browser/desktop capability, skill effectiveness, or benchmark superiority. Those remain separate work. No benchmark answer or provider model ID is hardcoded by these changes.

Expanded full regression result: **278 passed in 52.15 seconds**, including the loopback integration test. This is regression/integration evidence for the covered paths, not an agent-task benchmark.

Memory/resizing update: full suite **284 passed in 56.00 seconds**. The real CLI pseudo-terminal test resized 80→207→60 columns without restarting, switched to a compact 24-row view, and exited cleanly on Ctrl+C. Memory tests cover workspace isolation, override/edit revisions, expiration, forgetting, known credential rejection, bounded retrieval, and separation from action observations. After exposing saved context to final-response generation, focused memory/evidence/UI checks were rerun.

Browser adapter: initial launch failed because the installed Playwright version required a Chromium revision absent from the machine cache. Downloaded the matching runtime into `/tmp/kestrel-browser-runtime`; no user browser/profile was used. Real-browser tests then passed for observed form filling, saving, outcome text, stale token rejection, changed target rejection, URL/key restrictions, and cleanup. A second test exercises the same form through the actual direct MCP client/server transport with a non-Codex provider configuration and structured tool outputs. These are integration tests, not model-quality benchmarks.

Full suite with the browser extra and matching runtime: **286 passed in 60.91 seconds**. Command: `PLAYWRIGHT_BROWSERS_PATH=/tmp/kestrel-browser-runtime python -m pytest -q` in the development environment. Browser tests explicitly skip when the optional Python package is not installed; a missing runtime with the package installed fails rather than silently passing.

## Skill browser and native browser comparison — 2026-09-22

- Full suite after the library change: 292 passed in 62.80 seconds.
- Additional real CLI pseudo-terminal test: `/skills`, search, 80-to-60-column resize, Escape return, idle Ctrl+C exit passed.
- All 13 bundled SKILL.md packages passed the skill format validator. New skill behavioral quality remains unevaluated.
- Generation boundary regression and browser-grader checks: 14 passed; subsequent native-scope grader expansion: 3 passed.
- Live native Astra medium and current Kestrel+Jev both passed the isolated browser outcome oracle. Native: 66.379 seconds. Kestrel+Jev: 46.854 seconds. Different approval mechanisms, one current run each, no universal quality/speed/cost claim.

## Docker process lifecycle follow-up

Fixed ignored nonzero cleanup exit codes, retained unresolved container names for retry, prevented new commands before cleanup confirmation, and made runtime shutdown close remaining clients after a cleanup error. Six process-level tests use a fake Docker executable to exercise actual subprocess cancellation/output handling and failure paths. They do not establish container isolation or replace a live Docker daemon test. The configured Colima socket remains unavailable.

## HTTP provider fault contracts

51 provider/generation tests pass after rejecting malformed response objects, malformed messages/content blocks, explicit refusals and unexpected tool calls, and invalid token counters. HTTP redirects remain disabled even if an injected client enables them, and invalid JSON errors do not echo response bodies. These are protocol fixtures, not live conformance claims for every named provider. Missing usage still maps to zero in the existing adapter and must not be interpreted as a verified zero cost.

## Final regression and standard-mode checkpoint

After provider fault handling, Docker cleanup, and Mac shortcut fixes: **319 tests passed in 73.14 seconds**. Standard Kestrel (zero Jev calls) and native Astra medium both passed two small coding repair repetitions. All four retained implementations passed 500 further randomized cases each. Standard browser smoke passed in 71.867 seconds, compared with the retained native baseline at 66.379 seconds. See `benchmarks/STANDARD-QUALITY-SEP22.md` and `COMPLETION-AUDIT-SEP22.md` for scope and remaining gaps; the overall goal is not declared complete.

## Image-input checkpoint

Bounded image validation/cache and the inspect_image tool now send actual pixels through the selected model protocol. Five new tests and an expanded real MCP transport test pass; full suite **324 passed in 70.97 seconds**. A live Astra medium smoke correctly read a random green-button label from the retained `benchmarks/vision-fixture.png`; one generation call, zero Jev calls. The first attempt to run the loopback test under the restricted shell failed at socket binding; it passed under the loopback-enabled test invocation. Native desktop actions and broad visual competence remain unverified.

## Experimental native desktop boundary

App-scoped macOS Accessibility observation/press/fill tools and a bearer-authenticated localhost MCP server are implemented. Nine adapter tests plus general feature checks: 21 passed. The actual macOS permission query returned false; the denial path was tested without changing permissions or inspecting personal apps. Real app interaction remains unvalidated. See DESKTOP.md for limits and setup. The requested deadline elapsed before full native validation; this is not marked as complete or superior.

## Workflow artifacts and release checkpoint

Nine new cases execute the copy-text template through the actual dependency scheduler, file tools, permission checks and SQLite storage. Empty, Unicode and whitespace-sensitive text is compared byte for byte. Negative cases cover missing input, existing destination, read-only permission, rejected approval, an outside-workspace destination and truncated input. A missing-input case exposed a checkpoint gap: blocked descendants were not saved when no further tool ran. The scheduler now persists these transitions immediately. Model generation and model decisions are asserted unused in this unconditional-template test; these cases do not evaluate final-answer quality or certify other workflows.

The first complete regression invocation omitted the development Chromium path: 331 passed and two browser-launch tests failed because the default cache lacked the executable. With the matching runtime configured, the final complete suite passed **342 tests in 133.28 seconds**, including real Chromium, MCP transport, PTY interaction, native adapter contracts and workflow artifacts. Command: `PLAYWRIGHT_BROWSERS_PATH=/tmp/kestrel-browser-runtime python -m pytest -q`.

`uv build` produced both the source distribution and wheel successfully. Wheel inspection confirmed all 13 bundled skills and the desktop/vision modules. This validates packaging and the covered regression paths; live Docker, live native desktop interaction, external-provider conformance and broad superiority remain unverified.

## Learned-recipe provenance

Learned recipes now record their source session, state/trace/recipe hashes and source completion-check outcomes. Pending/failed checks and unresolved actions prevent learning before a provider call. Manual activation is explicitly unverified planning guidance; source observations are not certification on new inputs. Legacy recipes migrate without losing their content or active state and display missing provenance honestly.

Full suite: **351 passed in 142.47 seconds**. Subsequent focused checks cover a strengthened legacy migration case and an additional real CLI-output test: **10 provenance tests passed**. After updating planner guidance, provenance/evidence checks also passed (20 tests). The extra CLI test was added after full-suite collection and is not included in the 351 count. Independent skill/workflow behavioral certification and automatic promotion remain incomplete.

## Embedded-frame browser support

The browser adapter now observes nested/cross-origin frames, labels target ownership, excludes hidden ancestor frames and invalidates observations when any frame attaches, navigates or detaches. Bounds and truncation are reported. Read-only collection retries up to three times after frame-tree changes; actions are never replayed. Thirteen browser/frame/vision/grader tests pass, including real Chromium and MCP transport.

Two live standard Kestrel/native Codex pairs passed the independent embedded-form oracle with zero Jev calls and exactly one saved record each. The first Kestrel run exposed a loading race and later recovery issues, all retained. With observation retries, Kestrel passed in 73.769 seconds versus Codex at 41.394 seconds. See `benchmarks/FRAME-BROWSER-SEP22.md` for all results and limitations. This expands tested capability, not a superiority claim.

## Repeatable MCP observations

An explicit per-connection `read_only_tools` setting distinguishes trusted observations from external effects. CLI `--read-tool` and chat `/connections reads` declarations allow repeated current-state reads, retain normal approvals and network/access restrictions, and leave unlisted calls protected against duplicate effects. Server hints never enable this behavior. Repair discards old read results; recorded action classifications preserve that distinction if settings change later. Calls remain serialized.

Ten focused tests cover refresh, denied access, duplicate submissions, failed-read retries, repair freshness across configuration changes and CLI/chat configuration. A real HTTP MCP integration case changes server state between identical observations and verifies the engine receives the new value while asking approval twice. The final complete suite passed **366 tests in 151.93 seconds**. An earlier full run passed 364 before the final checkpoint/retry cases were added. No new live model benchmark was run for this change; the earlier latency results are not attributed to it.

## Connector image references

Single-image MCP results now expose a locally validated top-level image_id; multiple-image results expose indexed image_refs. Invalid input cannot preserve a remote-supplied cache ID, and images evicted by a large response are omitted from the usable reference list. Tool guidance documents exact result-binding paths.

**47 focused tests passed in 16.33 seconds**, covering vision protocols, malformed inputs, cache limits, actual Chromium screenshots, real MCP transport, typed tool contracts and observation recovery. The MCP integration test binds `${shot.image_id}` into inspect_image and verifies exact cached pixels at the model interface; generation in that test is mocked. No fresh live-model perception or task-quality benchmark was run. The preceding complete-suite result remains 366, before this alias addition.

## General-agent data reconciliation

A new independently graded saved-report task compares standard Kestrel with its data-audit skill against direct Astra medium. Kestrel completed 1/2 repetitions; native Codex completed 2/2. All four saved artifacts and final workspace scopes pass separately. Kestrel's failed run stopped during repair after its verifier could not inspect a truncated invocation, despite a correct saved report. That task remains failed. See `benchmarks/DATA-RECONCILIATION-SEP22.md` for timings, trace findings and limitations. Twenty-nine grader/benchmark regression tests passed; no fixture-specific product changes were made.

## Retrievable invocation evidence

Tool results now link to separate redacted invocation records, with status and executor-boundary flags. Context exposes those IDs and uses spare excerpt space for arguments. Repair guidance explains how retained checks persist without invalid references. Three new tests cover restart/retrieval/session isolation, larger complete argument excerpts within budget, and honest handling of legacy records. Existing tests still reject dropped failing checks and invalid references.

The full suite passed **380 tests in 162.45 seconds**. Repeating the same data fixture produced Kestrel **2/2** and native Codex **2/2** passes, with no Kestrel repair rounds. The original failure remains retained. Rerunning an examined fixture is evidence for this repair, not broad task superiority or independent skill certification. See EVIDENCE.md and the benchmark follow-up for details and timing caveats.

## Runtime readiness diagnostics

`doctor` now distinguishes credential presence, model selection, installed dependencies and actual runtime probes. Standard mode labels Jev disabled instead of warning about a missing optional key. Explicit `--runtime-checks` or `/doctor runtime` queries Docker daemon/image metadata and launches/closes isolated Chromium; no containers, pulls or pages are involved. Local macOS diagnostics read only the current process's Accessibility flag.

**50 focused readiness/setup/provider/UI tests passed in 6.91 seconds**, including actual subprocess timeout/kill/reap, no-probe defaults, credential redaction boundaries and explicit chat flags. Live runtime checks on this machine reported Chromium ready, Docker daemon unavailable and Accessibility missing. No native app was inspected, no OS permission changed, and no live Docker execution is claimed. The previous full regression result is 380 before this diagnostic feature.


## Skill package integrity and final regression checkpoint

Rollback and reinstall now verify recorded archive hashes before modifying an active skill. Skill file reads pin package-relative directories, reject symlinks and non-regular files, and enforce actual byte limits. Discovery versions hash the same entrypoint bytes that were parsed. Duplicate YAML/JSON metadata keys are rejected and `/doctor` cannot be shadowed by a skill.

Nine new cases cover duplicate/nested metadata, duplicate capability fields, symlink reference directories, a file changed between parsing and hashing, modified/added/symlinked rollback archives, oversized files and FIFOs. The focused skill/library/general suite passed **32 tests**. The final complete regression suite passed **399 tests in 171.20 seconds**, including the readiness additions and real browser/MCP/PTY fixtures. No new live-model quality claim is attached to this integrity change.

The first packaging invocation was denied access to the uv cache by the restricted shell. The approved build then produced both the source distribution and wheel; wheel inspection found all 13 bundled skills and the readiness, registry, browser, desktop and vision modules. This validates packaging, not the pending live runtime and broad behavioral gates in COMPLETION-AUDIT-SEP22.md.


## User-runnable workflow behavior fixtures

`kestrel workflows test TEMPLATE SUITE` now executes unconditional file workflows in a separate process with temporary task directories and private session storage. Exact full-file-tree bytes, every action status, expected error fragments and positive-case completion contracts are checked without model calls or repair. Other tools and conditional actions are rejected before execution. Reports include template/suite hashes and remain explicitly uncertified; caller-supplied oracles do not prove independent evaluation, held-out quality or broad skill applicability.

The first manual attempt incorrectly placed fixtures under protected Kestrel storage; real file permissions rejected the inputs. The harness now separates private state from task directories. Negative cases also require matching error fragments so an unrelated permission failure cannot be accepted as a missing-input success.

Thirteen new tests cover real worker execution, parent-storage isolation, wrong artifacts, unrelated errors, extra files, failed completion contracts, unsafe paths, unsupported tools, CLI failure exit codes and generated parameters. Initial twelve tests passed; a separate generated-input/CRLF test passed after byte-comparison strengthening. The final full suite passed **412 tests in 268.97 seconds**. The sample CLI's four cases passed and its report is retained in `examples/workflows/copy-text.report.json`. Wheel/source builds succeeded and wheel inspection confirmed the new module.

This advances the workflow-evaluation infrastructure; independent skill certification, automatic promotion and external-tool behavioral suites remain pending. No new live-model benchmark or superiority claim is made.


## Active-task steering and approval-wait controls

`/steer UPDATE` now cancels and awaits the owned worker, saves the update and resumes through normal planning/reconciliation. Evidence, exact completion checks and completed/uncertain effect receipts remain. Updates are persisted, bounded, included in conversation history and cleared for a new task. Resumed tasks correctly enter running state. `/cancel`, `/status`, `/help` and `/details` work during active tasks; steering, cancellation and exit work during approval waits without granting permission.

The full regression suite passed **423 tests in 278.65 seconds**. After collection, a completion-race test was added and update logging was extended to ordinary conversation history. The final focused steering/interrupt/dashboard suite passed **20 tests in 13.54 seconds**, including those changes. Tests cover cancellation ordering, approval wait cleanup, restart persistence, preserved requirements/receipts, a real completed file write retained without replay, and refusal to restart work that completes during steering. They use controlled model boundaries rather than a live-model quality benchmark.

This implements bounded steering for one owned task. Detached/background jobs, concurrent tasks and broad external-action steering validation remain pending. Conflicting exact completion requirements require a new task. Usage shown after resumption is per-run; logs retain preceding runs.


## Local background jobs and input handoff

Detached workers now have private launch files, separate sessions, OS lock ownership, same-workspace exclusion within one Kestrel home, cooperative cancellation and CLI/chat inspection. They never signal a recorded PID or automatically retry a lost worker. Interactive resumption refuses a session owned by a live job. Required approvals stop for interactive continuation; clarification questions now leave needs_input rather than completed. Terminal job results are published after cleanup, and cleanup failures remain failures.

The full regression suite passed **435 tests in 291.23 seconds**. A subsequent cleanup-cancellation refinement and extra parametrized case passed with the final **24 job/steering tests in 24.44 seconds**. Coverage includes actual interprocess ownership/cancellation, real engine file permissions, private launch files, workspace contention, stale-PID handling, ownership beyond the list page, cleanup failures, clarification state and steering. Wheel/source builds passed; wheel inspection confirmed the worker module.

A real detached Astra-medium standard-mode smoke read a temporary file and returned its random one-line content exactly, with no workspace changes. Worker wall time **18.204 seconds**, engine run **16.86 seconds**, one generation, one decision and zero Jev calls. The retained report is `benchmarks/results-background-job-smoke.json`. This is a functional integration check, not a comparison or broad quality claim. See JOBS.md for limits around cooperative cancellation, foreground/overlapping workspaces, machine availability and continuation after approval/input waits.


## Source-grounded general-task comparison

Two new document variants exercise per-field authority/date selection, exact citation/quote support, unknown-field abstention, a source instruction trap and saved-artifact scope. Both standard Kestrel with research-brief and direct Astra medium passed both variants with no file-scope violations. Kestrel took 68.214/69.824 seconds; native Codex took 32.773/31.970 seconds. Concurrent variant execution and different architectures limit timing interpretation. The result is a correctness tie on one structured local-source task family, not superiority or independent skill certification.

Thirty-eight grader/benchmark regression tests passed in 0.82 seconds, including a hand-authored oracle check and mutations for unsupported claims, wrong citations, quotes, types and duplicate keys. Product behavior was unchanged. Raw artifacts/traces and limitations are linked in `benchmarks/SOURCE-SYNTHESIS-SEP22.md`. Separate final-answer generation/review calls are an identified architecture investigation, not an optimization already claimed to work.


## Verified fixed-response contract

Plans may propose final_response_text only for exact fixed wording requested by the user. The field is bounded, execution-plan-only and mutually exclusive with tool result references. The existing outcome review checks this candidate alongside original-task completion, exact contracts and outstanding failures. Rejected candidates retain ordinary generation/review; failed checks or incomplete work still repair. No acknowledgement phrase lookup or benchmark-specific product path was added.

Initial focused response/evidence/workflow tests passed 54 cases. Coverage was expanded to standard and Jev mode, and the final complete suite passed **466 tests in 331.09 seconds**. Negative cases cover unsupported candidates, missing sources, unfinished tasks and failed exact contracts; positive cases preserve Unicode and exact output.

Live comparisons passed an examined source variant and a new input variant, with clean artifact/scope grades. Each Kestrel trace used the verified planned response and reduced calls from the earlier three generation/two decision calls to two generation/one decision call. Times were 54.361/53.405 seconds versus direct Codex 39.108/33.538 seconds. This is a demonstrated call reduction and correctness tie on these samples, not general superiority or a dollar-cost estimate. Raw results and timing limitations are in `benchmarks/SOURCE-SYNTHESIS-SEP22.md`. Product regression tests ran after the live comparisons.
