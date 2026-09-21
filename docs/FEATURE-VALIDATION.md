# General-feature validation

Testing resumed after the user's explicit request to build and test the full system. The earlier implementation PRs retain their original untested-at-publication history.

- Existing suite: 260 passing tests, 54.19 seconds.
- Dashboard and terminal interruption: 7 passing focused tests. An initial 40-column footer wrap was fixed; all controls remain readable at tested widths of 40, 60, 80, 100, and 140 columns. Rich SVG output was rendered and visually inspected.
- Setup/workflow/execution/connection boundaries: added tests for interrupted setup leaving settings unchanged, API/Docker/Jev configuration, typed parameters, unknown parameters and tool names, cyclic dependencies, external schema restrictions, workspace-only Docker mounts, network disabling, no implicit pulls, endpoint credential restrictions, and pre-dispatch validation.
- Actual MCP transport: a temporary loopback FastMCP server exercised catalog discovery, a typed structured-output call, worker reuse, and shutdown. Initial execution was blocked by the filesystem/network sandbox; rerun with loopback permission passed. An initial fixture used an untyped dict return, which the SDK emitted without structuredContent; changing the fixture to an explicit result model exercised the intended structured-output path.

These tests do not establish external-provider quality, live Docker execution, browser/desktop capability, skill effectiveness, or benchmark superiority. Those remain separate work. No benchmark answer or provider model ID is hardcoded by these changes.

Expanded full regression result: **278 passed in 52.15 seconds**, including the loopback integration test. This is regression/integration evidence for the covered paths, not an agent-task benchmark.

Memory/resizing update: full suite **284 passed in 56.00 seconds**. The real CLI pseudo-terminal test resized 80→207→60 columns without restarting, switched to a compact 24-row view, and exited cleanly on Ctrl+C. Memory tests cover workspace isolation, override/edit revisions, expiration, forgetting, known credential rejection, bounded retrieval, and separation from action observations. After exposing saved context to final-response generation, focused memory/evidence/UI checks were rerun.
