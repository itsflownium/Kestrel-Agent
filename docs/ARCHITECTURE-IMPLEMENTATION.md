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
| Typed tool arguments and executable completion checks | Typed argument boundaries and bounded exact-result/text/JSON completion contracts implemented; broad coverage still requires held-out evaluation | Invalid plans prevented; exit/artifact/format checks and original-task coverage |
| Partial plan repair, no-progress budgets and effect reconciliation | No-progress budget, workspace receipts, conservative successful-subgraph retention, normalized retry guards and interruption receipts implemented; broad recovery evaluation pending | Resume, partial side effects, equivalent retries, no completed-effect replay |
| Dependency-driven read scheduling | Verified; 155 offline tests, synthetic timing, live regressions 2/2 pass; no live speed claim | Fast read descendants proceed; bounded concurrency and cancellation |
| Validated parameterized workflows | Typed templates, isolated file fixtures and exact-version tested skill exports implemented; independent certification/applicability still pending | Review/promotion, applicability abstention, prerequisites, unseen parameters and effect controls |
| GEPA independent test splits and outcome labels | Implemented; offline isolation/promotion tests; no live optimization quality claim | Family separation, untouched final evaluation, activation guards |
| Generator/decision/execution/tool capability boundaries | HTTP generation/decision/file-tool boundaries verified through real loopback protocols; full backend/live-provider matrix pending | End-to-end successful and denied file tasks, exact-check rejection of affirmative false reviews, native-tool-response rejection; live provider and sandbox conformance remain required |
| Broader held-out evaluations and fair baselines | Pending | Frozen task families, randomized paired repeats, independent grading, failures retained |
| Compact action loop versus current DAG | Two paired dynamic-browser variants assessed; quality tied, fewer calls and lower time for benchmark-only one-action mode; graph default retained | Broader task families, recovery and counterbalanced comparisons required before promotion |
| Publication and final completion audit | Pending | Reviewed PRs, source hashes, all requirements verified or explicitly rejected on evidence |

## General-agent extension requested 2026-09-21

The user additionally requested portable skills and commands comparable to Hermes, API-model choice, and Jev as an optional mode. Research and concrete acceptance criteria are in [GENERAL-AGENT-ROADMAP.md](GENERAL-AGENT-ROADMAP.md). Standard/Jev modes are implemented and tested (see benchmarks/STANDARD-MODE.md). These remain pending: skill discovery/loading/invocation; versioned skill evaluation/promotion; provider-independent execution/general tool adapters; terminal capability UX; general-task comparisons against Hermes using matched models. Preserve the original architecture scope above.

## Current general-agent checkpoint (2026-09-22)

The initial pending list above records the original audit, not the current feature inventory. Portable skills, standard/Jev modes, direct MCP execution, typed local workflow templates, explicit scoped memory, guided provider/Docker setup, and a live-resizing terminal are implemented. PR #28 adds a searchable skill library and six task-focused procedures. [TASK-ARCHITECTURE.md](TASK-ARCHITECTURE.md) maps the shared controller and task-specific paths to enforced checks and open gaps.

The generation-only Codex adapter now explicitly disables installed plugins as well as configured MCP servers, apps, and shell execution. The native browser benchmark exposed why plugin configuration must be included; native tool calls belong to the controller's execution path, not its generation component.

Still unverified or incomplete: native desktop/vision, live Docker daemon execution, broad provider conformance, independent skill/workflow behavioral certification, compact-loop assessment, and repeated held-out comparisons. Neither passing regression tests nor a faster isolated browser task establishes universal superiority or completes the original goal.

## Docker recovery checkpoint

The Docker execution backend now persists pre-launch cleanup receipts, holds OS-level workspace ownership during execution/recovery, and verifies run labels before removal. It checks cleanup after ordinary client exit as well as cancellation, and rejects a changed Docker-target fingerprint. Process-fixture tests kill a real worker and verify recovery by a new executor before another run starts. This improves the execution/recovery boundary; it does not establish actual daemon isolation or replace the pending live Docker and provider-conformance gates.

## HTTP controller conformance checkpoint

Real loopback HTTP tests now run both supported provider protocols through planning, generation, permission-controlled file writes, deterministic completion checks and semantic review without starting Codex or Jev. Negative controls verify that the model cannot override a denied write or an incorrect artifact by affirming success. These are scripted-protocol tests, not external-model quality evaluations. See `benchmarks/PROVIDER-CONTROLLER-SEP22.md`; external-provider availability and execution-backend validation remain separate.
