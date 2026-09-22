# Canvas visual integration — 2026-09-22

The retained `results-canvas-vision-smoke.json` reports one passing standard-mode GPT-6 Astra medium run, with two image-generation calls and zero Jev calls. A generated isolated canvas contains green Confirm and red Reject rectangles. The model locates the green rectangle from actual pixels; the adapter clicks those coordinates; a second image call reads the random saved code. An independent HTTP ledger records exactly one green click and the returned code matches the generated nonce. Before/after PNGs are retained.

This is a perception → browser action → visual readback integration smoke, not a full autonomous Engine run, direct-Codex comparison, native desktop benchmark, or superiority claim. The harness parses the coordinate JSON and orchestrates these calls. Its SHA-256 is recorded with the result; the fixture seed controls geometry while the saved nonce varies. No task answers or coordinates are encoded in product code.

The production MCP screenshot now returns structured observation metadata, and strict JSON image interpretations expose data fields for ordinary dependency binding. Regression tests cover that binding separately. Coordinate clicks intentionally reject changing/animated pixels and hover changes; inspection and input remain non-atomic. Native desktop coordinates, canvas dragging, and canvas keyboard interaction remain outside this change.

## Autonomous controller follow-up

`canvas_agent.py` supplies only the task and the isolated MCP catalog to the normal Engine. The expected random code is held by the fixture backend and returned only after a green click; the task does not disclose it. The grader requires completed status, exactly one green submission, an image-inspection result containing the code, the correct final answer and no workspace edits.

- Initial run: passed in **112.391 seconds**, five generation calls, three standard model decisions, zero Jev calls. It first used an incorrect root-level tab reference, then recovered through normal replanning. Preserved in `results-canvas-agent-initial.json`.
- After generic MCP-envelope guidance: passed in **93.404 seconds**, five generation calls, three standard model decisions, zero Jev calls. No failed tool observation; the planner still used two planning phases. Preserved in `results-canvas-agent.json`.

These are two runs of one small synthetic task, with different random saved codes. Regression tests ran concurrently. The timing difference is descriptive, not an isolated performance experiment; there is no direct-Codex baseline for this canvas task and no general superiority claim.

## Regression and packaging

The full suite passed **482 tests in 336.12 seconds**. After the final catalog-guidance edit, the focused image/MCP suite passed **25 tests in 17.35 seconds**, followed by the second live autonomous run above. The earlier browser/coordinate/image subset passed 24 tests. Source and wheel packages built successfully; the wheel includes the coordinate implementation and updated bundled browser skill. `git diff --check` passed.
