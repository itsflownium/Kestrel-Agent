# Dependency-driven read scheduling

The old scheduler waited for every ready read in a batch before releasing any descendant. The new scheduler collects completed reads individually, so a fast read's descendant can proceed while an unrelated slow read is still running. Jev still gates each newly ready group. `max_parallel_reads` defaults to four, effects run serially after in-flight reads finish, and cancellation joins every in-flight read before returning.

Offline tests prove a descendant can unblock an unrelated slow read (the old barrier deadlocks that dependency pattern), enforce the concurrency and step budgets, check effect ordering, and confirm cancellation clears all in-flight reads. The full suite passes 155 tests.

## Synthetic timing

`benchmarks/scheduling.py` uses the same three-read DAG with a 20ms fast read, a 200ms unrelated read, and a 200ms descendant of the fast read. Jev is mocked as instantaneous. Five interleaved randomized trials per scheduler all completed correctly:

| Scheduler | Median |
| --- | ---: |
| Original whole-batch barrier | 402.8ms |
| Dependency-driven | 222.9ms |

This demonstrates removal of unnecessary waiting in that topology, not an end-to-end Codex speedup. Actual latency depends on tool durations, Jev calls, provider load, and plan shape. A concurrency limit can add decision batches for large independent groups. Raw traces and the scheduler source hash are in `results-scheduling.json`.

Live GPT-6 Astra medium / Jev regressions are retained separately in `results-scheduling-live.json`. These fixtures are development diagnostics, not an untouched held-out evaluation.


Live regression results: both agents passed the edit and long-evidence cases. Kestrel took 29.898s versus Codex 28.010s for the edit, and 27.702s versus 11.179s for long evidence. These local reads are short, so removing the batch barrier does not overcome generation/Jev overhead or the planner's overly broad first search. The change is justified by the dependency and cancellation controls, not a claim that these two workloads became faster than Codex.
