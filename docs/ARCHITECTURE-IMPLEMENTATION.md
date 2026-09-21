# Architecture implementation audit

User priority update: correctness, completeness, and reliable recovery come first; roughly Codex-level latency is acceptable. Beating Codex on every timing is not a release requirement.

Objective: review all proposed improvements, implement those supported by evidence, and test them. The research proposal is preserved at ../../../research/kestrel-architecture-review-2026-09-21.md in this local workspace. This checklist records the complete scope; a partial PR does not complete the goal.

| Requirement | Status | Required evidence |
| --- | --- | --- |
| Timing, cache/usage accounting, approval/tool durations | Verified foundation | SDK snapshot tests; live stage measurements |
| Strict answer and recursive workspace graders | Verified foundation | False-pass controls; binary/nested/symlink scope tests |
| Remove ineffective routing, preserve meaningful Jev checks | Verified foundation | Direct-answer rejection; action and completion checks; live comparison |
| Reuse fresh initial observations | Verified foundation | No duplicate read; changed hash forces reread |
| Generation setup/context/session experiments | Fresh default retained; schema isolation verified; compact prompt remains optional pending broader quality evidence | Fresh versus task sessions, schema changes, cancellation/config invalidation, cost/latency evidence |
| Durable requirements/evidence ledger, truncation and retrieval | Implemented and tested; source extraction/hash snapshot consistency and exact raw-text reuse added; live latency mixed | Long history, lost-prefix data, stable references, changed sources |
| Typed tool arguments and executable completion checks | Pending | Invalid plans prevented; exit/artifact/format checks and original-task coverage |
| Partial plan repair, no-progress budgets and effect reconciliation | No-progress budget and workspace receipts implemented; subgraph repair/reconciliation pending | Resume, partial side effects, equivalent retries, no completed-effect replay |
| Dependency-driven read scheduling | Verified; 155 offline tests, synthetic timing, live regressions 2/2 pass; no live speed claim | Fast read descendants proceed; bounded concurrency and cancellation |
| Validated parameterized workflows | Pending | Review/promotion, applicability abstention, prerequisites, unseen parameters and effect controls |
| GEPA independent test splits and outcome labels | Pending | Family separation, untouched final evaluation, activation guards |
| Generator/decision/execution/tool capability boundaries | Pending | Provider adapter conformance; existing sandbox guarantees retained |
| Broader held-out evaluations and fair baselines | Pending | Frozen task families, randomized paired repeats, independent grading, failures retained |
| Compact action loop versus current DAG | Pending assessment | Evaluate after measured simpler changes; retain or reject with reasons/evidence |
| Publication and final completion audit | Pending | Reviewed PRs, source hashes, all requirements verified or explicitly rejected on evidence |
