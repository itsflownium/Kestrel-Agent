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
