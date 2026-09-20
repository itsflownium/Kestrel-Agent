# Compact command recovery — September 20, 2026

A new `repair_command` step reads bounded program/input evidence after an observed nonzero exit and asks the selected generation provider for corrected arguments. It preserves the executable and named script, uses the stored original user request, and returns an unresolved result when it cannot justify a repair. It does not run the command. Execution remains a separate shell action with the normal Jev decision, permissions, and observed-exit verification.

This removes several discovery and planning steps in the tested argument-recovery workflows. It is generic application logic; it contains no fixture names, expected totals, or benchmark-specific branches.

## Paired live results

| Task | Kestrel | Direct Codex | Result | Kestrel calls |
| --- | ---: | ---: | --- | --- |
| tool_recovery | 27.745 s | 17.988 s | Both pass | 3 generation / 6 Jev |
| recovery_variant | 31.210 s | 15.989 s | Both pass | 3 generation / 6 Jev |
| recovery_two_arguments | 33.519 s | 20.345 s | Both pass | 3 generation / 6 Jev |

All six runs passed the independent checks, including successful command output and no file edits. The new two-argument case requires a data path plus a numeric value from the original request, with a distractor data file present. Jev participates throughout each Kestrel run.

The variant previously took 50.170 s in the initial-context report. Its new 31.210 s is a useful observed reduction, but it is a cross-run comparison with substantial model/runtime variability. **Direct Codex is still faster on every recovery case here.** Kestrel still spent a final generation call summarizing the retry; output reuse was not selected. This is progress on orchestration overhead, not evidence of overall superiority or lower billed cost.

Both arms use GPT-6-Astra at medium effort, with isolated workspaces and alternating arm order. There is one trial per arm/case; no statistical speed claim or p95 is supported. Timing excludes independent grading and cleanup. Raw fixtures, outputs, traces, source hashes, and graders are retained in `results-compact-recovery.json` and `workloads.py`.

The benchmark used a frozen copy of application source before the independent provider-onboarding changes in the same PR. Its recorded source hash identifies that recovery implementation. Provider setup was subsequently checked with mocked transports, CLI, and interactive tests; these recovery numbers are not live measurements of the newly added providers.

Reproduction (consumes live provider usage):

```sh
python benchmarks/workloads.py --tasks tool_recovery,recovery_variant,recovery_two_arguments --output NEW_RESULT_PATH
```

Offline tests additionally reject unknown/successful exits, executable/script changes, identical retries, invalid argv, unresolved commands with fabricated actions, and undeclared whole-result dependencies. Evidence is capped at four small sources; larger or ambiguous repairs remain the general controller's responsibility. Generated arguments are proposals, not a proof of safety or correctness.
