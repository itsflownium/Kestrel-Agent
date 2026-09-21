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
