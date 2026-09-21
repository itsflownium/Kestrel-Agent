# Architecture foundations: measurement before default changes

Live runs on 2026-09-21 used GPT-6 Astra at medium effort for both arms, Jev for Kestrel decisions, isolated identical fixtures, randomized case/arm order (seed 20260921), and independent outcome/workspace grading. There was one paired trial per case per session setting. This is a diagnostic experiment, not a statistically powered superiority study. The session experiments ran sequentially and are subject to service and generation variance.

| Case | Fresh Kestrel | Paired Codex | Experimental reuse Kestrel | Paired Codex |
| --- | ---: | ---: | ---: | ---: |
| Missing two command arguments | 27.991s | 25.270s | 24.312s | 25.445s |
| Aggregate and write JSON | 21.716s | 24.615s | 18.905s | 24.288s |
| Exact command JSON | 11.120s | 8.755s | 16.883s | 9.627s |
| Iterable normalization edit | 27.469s | 38.975s | 29.364s | 29.141s |

All 16 runs passed the automated artifact/output/scope graders. **The reuse code-edit answer nonetheless exposed a response-quality defect:** the SDK retained the previous structured output format and returned a plan JSON envelope instead of normal prose. The artifact grader did not check this unconstrained prose presentation. That candidate is rejected for cross-schema reuse; its automated pass must not be described as a complete quality pass.

The fix starts a new generation thread whenever the output schema changes (including structured-to-plain), even in optional task-session mode. Setup caching remains task-scoped and independently invalidates on configuration changes. All generation failures, including turn-start failures, discard reusable state. Fresh sessions remain the default. The follow-up live regression passed and returned normal prose: Kestrel 29.282s, paired Codex 32.315s. It is retained separately in `results-foundations-schema-fix.json`.

Fresh-session recovery stage measurements: first/second thread starts 0.169/0.096s, account check 0.012s, config read 0.023s, generation streams 13.307/7.810s. Model response time dominates this sample; avoiding thread setup alone cannot justify a multi-second speed claim.

SDK-reported Kestrel input tokens for fresh versus experimental reuse were 31,484/35,748 for recovery, 31,872/37,537 for the table write, and 30,747/36,709 for the edit. Reuse did not reduce reported input in these samples. Cached input was zero except 3,840 tokens in the reuse edit. These are SDK usage fields, not verified invoices; subscription usage cannot be converted to dollar savings from these results.

Implemented foundations:

- Cumulative per-thread token high-water accounting prevents duplicate or out-of-order usage notifications from double counting.
- Content-free timings cover setup, generation, Jev, tools, and approvals. Nested durations are attribution, not additive wall time.
- Conversation context excludes internal event noise.
- No routing classifier call when neither choice could enter an executable fast path. Direct answers instead receive a Jev support check.
- Initial source evidence is reused only while the source SHA256 matches.
- Strict JSON, observed-command checks, and recursive manifests catch nested/binary/large-file/symlink scope changes. Prose heuristics remain limited and should not be called semantic proofs.

All 138 foundation offline tests pass. Offline validation covers repeated/out-of-order usage, same-schema reuse, changed-schema isolation, model/task invalidation, cancellation and failed turn startup, stale source rereads, direct-answer rejection, and false-pass grader controls. The full implementation scope remains in `docs/ARCHITECTURE-IMPLEMENTATION.md`.

Raw results include source hashes, fixtures, prompts, event traces, outcomes, timings, token reports, and before/after manifests. Files `results-foundations-fresh.json` and `results-foundations-task.json` retain the original experiment before the schema guard; do not relabel them as runs of the fixed revision.
