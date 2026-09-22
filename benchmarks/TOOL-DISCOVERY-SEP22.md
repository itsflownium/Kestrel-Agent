# Connected-tool discovery — 2026-09-22

The previous planner interpolated the first 12,000 characters of the serialized MCP catalog. This could omit registered tools or cut a schema mid-field. The new preview contains only complete JSON entries with explicit omissions, plus on-demand search and complete-definition retrieval.

The 101-tool loopback integration fixture places the target outside the initial preview. It exercises the Engine's normal action dispatch: discover the target, inspect its typed schema, and invoke it once through the regular permission check. Discovery itself never calls a remote operation or asks for effect approval. Tests also cover native name-keyed catalogs, direct tool lists, exact server filters, full-description search, pagination, duplicate identities, network-disabled behavior and changed-definition chunk rejection.

Two initial integration-fixture assumptions were corrected: a short target definition fitted the remaining preview space, so its description was lengthened to test an actually omitted target; an untyped dict return did not provide MCP structuredContent, so the fixture now declares a Pydantic output model. These were fixture failures, not passing runs.

`tool_discovery_agent.py` provides a separate explicit live standard-mode Astra medium task. It exposes only a disposable local service containing 100 unrelated tools and one shipping lookup. The target must be omitted from the initial preview. A random order is requested; the backend holds an undisclosed random status. The grader requires successful discovery and schema inspection, exactly one correct lookup, the exact returned status and no workspace edits. It does not supply tool names or schemas in the user task, and product code contains no fixture-specific routing.

This evaluates discovery and execution on a synthetic catalog. It is not a direct-Codex comparison, external-service conformance test, or proof of broad agent superiority. No user accounts or personal services are used.

## Live result

The retained `results-tool-discovery-agent.json` reports a pass in **68.374 seconds**, with three generation calls, three standard-mode model decisions and zero Jev calls. The target was absent from the initial preview. Observations show successful discover_tools, inspect_tool and MCP lookup actions; the independent service log records one lookup with the correct random order. The final answer exactly matches the backend's random status and no workspace files changed.

The full regression suite ran concurrently, so elapsed time is descriptive rather than an isolated latency measurement. The task was completed in three planning phases and still pays for an original-task review after each incomplete phase; this test does not resolve the separate compact-loop architecture assessment.

## Final validation

The full regression suite passed **490 tests in 346.10 seconds**. The focused discovery/contract/loopback suite passed 37 tests in 10.31 seconds. Source and wheel builds passed; archive inspection confirms the new discovery module and typed tool names are included. `git diff --check` passed. All tests used disposable fixtures; external provider and personal-service compatibility remain unverified.
