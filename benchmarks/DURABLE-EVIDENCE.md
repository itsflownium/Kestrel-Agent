# Durable task evidence

This change retains derived requirements across replans with stable IDs, current review verdicts, and IDs of observations supplied during that review. These are review provenance, not a claim that every listed observation proves the requirement. Every plan verification rechecks retained criteria; the original user request remains in context and receives its own Jev completion check.

Context includes a bounded evidence index as well as recent excerpts, explicit omission counts, excerpt truncation flags, and full serialized-result lengths. `search_evidence` performs session-scoped literal search across stored snapshots; `read_evidence` retrieves character ranges with explicit continuation offsets. Evidence remains historical: retrieval does not prove a source is unchanged or authorize repeating an effect. Existing write hash checks remain authoritative.

A separate no-progress budget stops repeated planning when no new successful evidence appears. Duplicate successful results with new action IDs do not reset it. It complements the existing generation, Jev, time, and tool-step budgets; it is not a general semantic-equivalence detector for shell commands.

Offline controls cover old evidence beyond the last 16 observations, truncated tails, cross-session isolation, search offsets, requirement persistence through two plans and checkpointing, duplicate-read stagnation, and repeatedly rejected direct answers. Live regressions are preserved in `results-durable-evidence.json`; the long-document case places required records at opposite ends of a 362-line fixture.

This is an incremental reliability change. Typed executable completion contracts, partial-subgraph repair, dependency scheduling, validated replay workflows, and independent GEPA test activation remain tracked separately in `docs/ARCHITECTURE-IMPLEMENTATION.md`.


The first live candidate is retained even though it regressed: recovery and exact command output failed after a successful command when Jev requested more evidence and the generated answer incorrectly carried a plan-only result reference. The edit passed at 33.501s versus 26.227s; long evidence passed at 62.370s versus 9.549s but needed five generation calls. These results do not support a speed claim.

The revised candidate addresses the observed causes: expose source pagination metadata independently of excerpts; include explicitly offset tail excerpts; prefer targeted searches for named records; allow only one schema correction before execution; and attach bounded workspace snapshots to command results. Workspace receipts compare net content/path/mode changes at command boundaries, not transient writes or changes outside the workspace. A scan that exceeds its entry/byte/time budget or encounters unreadable files reports unknown, never unchanged. Neither the receipt nor a Jev verdict changes execution permissions.

The benchmark harness now retains usage and traces on failed runs too. The separately saved first recovery failure trace preserves the evidence that led to the revisions.


## Revised paired results

| Case | Kestrel | Direct Codex | Independent result |
| --- | ---: | ---: | --- |
| Exact command JSON | 12.482s | 14.047s | Both passed |
| Two-argument command recovery | 25.143s | 19.520s | Both passed |
| Long source, separated records | 26.828s | 8.849s | Both passed |

Each row is one paired trial with GPT-6 Astra medium; source hashes and traces are retained in `results-durable-evidence-revised.json`. Kestrel uses Jev at action and completion boundaries. The long-source case improved from five generation/nine Jev calls to three/five; its remaining replan came from an overly broad literal query matching routine entries before the target record. Recovery and long-source latency still lose to direct Codex. These are diagnostic fixtures, not untouched held-out evaluations or evidence of universal superiority. No dollar-cost claim is supported.

All 151 offline tests passed before publication; the final filesystem hardening additionally uses nonblocking no-follow file opens to avoid following a substituted symlink or blocking on a substituted FIFO. Workspace audit snapshots are bounded and report unknown when incomplete.
