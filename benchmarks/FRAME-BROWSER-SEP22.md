# Embedded-frame browser evaluation

The isolated registration fixture now supports `--frames`, placing its form at a different origin (`localhost` versus `127.0.0.1`). The task requests a random record name, one save, visible confirmation, and no file edits. The existing grader checks the actual server-side submission ledger, observed confirmation and final answer, not just a click receipt.

Both agents used GPT-6 Astra medium, the same browser adapter/tool catalog, isolated temporary workspaces and no Jev. Native Codex used auto-review; Kestrel used fixture-only tool confirmation. Paired processes ran concurrently on this machine, so timings include possible shared-resource contention and are descriptive, not a controlled speed estimate.

| Adapter stage | Standard Kestrel | Direct Codex | Outcome |
| --- | --- | --- | --- |
| Initial frame support | 157.653 s | 46.380 s | Both passed |
| With bounded observation-only retries | 73.769 s | 41.394 s | Both passed |

Reports are the four `results-browser-frames-*.json` files. The initial Kestrel run encountered a frame-loading observation error, recovered through tab inspection, later encountered duplicate-snapshot effect suppression and an incorrect image reference, and ultimately completed with exactly one save and affirmative visible evidence. Those internal errors are retained in the report. They remain controller/planning concerns even though the final task passed.

The retry fix applies only to collecting observations when the frame tree changes. It never replays an action. The second Kestrel run opened the form successfully on its first tool call and passed with three generation calls and four standard decisions. One before/after trial cannot isolate the latency effect from model variability. Correctness ties and slower Kestrel times do not establish superiority.

Thirteen focused regression/integration tests pass after the change. These cover nested cross-origin frames, fill/save/verification, frame navigation/removal, hidden ancestors, bounds, observation-only retry limits, existing MCP browser transport, image handling and grading. Native desktop, canvas actions and broad browser quality are not established by this fixture.
