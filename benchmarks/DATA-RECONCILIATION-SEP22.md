# General-agent data reconciliation

This new fixture tests deduplication before filtering, exact decimal totals, invalid/non-finite amounts, Unicode/quoted CSV fields, audit counts, a saved JSON artifact, and final file scope. The independent grader rejects boolean/fractional counts, numeric strings, floating-point residue, extra groups, duplicate JSON keys and non-finite output. The product contains no fixture-specific logic.

Run: `python benchmarks/workloads.py --agent-mode standard --skill data-audit --tasks data_reconciliation --repeat 2 --seed 222 --output benchmarks/results-data-reconciliation-standard.json`.

Both arms used GPT-6 Astra medium, isolated workspaces, no network or external connectors, and the same task/input files. Kestrel explicitly used its bundled data-audit skill; direct Codex used its normal native tool workflow without that skill. There were zero Jev calls. These are two repetitions of the same fixed dataset, with randomized arm/trial order, not two unseen parameter sets or independent skill certification.

| Arm | Trial 1 | Trial 2 | Completed task passes |
| --- | --- | --- | --- |
| Standard Kestrel + data-audit | Pass, 57.755 s | Fail, 86.587 s | 1/2 |
| Direct Codex | Pass, 46.319 s | Pass, 53.060 s | 2/2 |

All four retained report.json artifacts pass the exact independent artifact oracle, and all four final workspace manifests pass scope checks. The separate artifact audit deliberately supplies the required response marker only to isolate artifact correctness; it does not replace the full task verdict. The failed Kestrel run remains failed because it did not complete the response.

The failed run computed, saved and checked a correct report. Its semantic verifier then marked the unchanged-source requirement unclear because the command excerpt cut off the hash assertion. A repair plan repeatedly referred to a completion-check action absent from the new plan, so schema validation stopped the task. The successful repetition completed without repair. This reveals evidence-visibility and recovery reliability gaps, not a successful claim of superiority.

Current context excerpts cap invocation arguments at 500 characters. read_evidence retrieves retained tool results, while the full invocation arguments currently live in session observations rather than an independently addressable evidence record. A general fix should make omitted invocation evidence retrievable and clarify retained completion-check semantics during repair. Do not solve this fixture by weakening checks or inserting expected report values into product logic.

The reports retain task verdicts, traces, inputs, artifacts, timings, usage and scope checks. `results-data-reconciliation-artifact-audit.json` records a hash of the original report and separate artifact-only verdicts. Twenty-nine grader/benchmark regression tests passed. This narrow evaluation does not establish broad data, document, research or skill quality.

## Invocation-evidence follow-up

The controller now retains session-scoped invocation records linked to result evidence, uses spare context space to show more arguments, and clarifies that repair plans need not redeclare unchanged retained checks. Missing-action references remain invalid; failed checks remain enforced. This is a general evidence/recovery change, with no fixture-specific product logic.

The same command, seed, dataset and two repetitions were rerun into `results-data-reconciliation-invocations.json`. Kestrel passed **2/2**, at 55.457 and 61.829 seconds; direct Codex passed **2/2**, at 34.457 and 51.357 seconds. Both Kestrel runs completed with one generation call and one standard decision call, zero Jev calls, and no repair round. The original 1/2 result remains unchanged and retained.

These are diagnostic reruns of an already examined fixture, not unseen generalization or a superiority claim. The full regression suite ran concurrently on this machine, so wall times can include contention. Two trials cannot establish a causal latency improvement. Separate tests cover retrieval of truncated invocations after restart, session isolation, legacy records and bounded context allocation; all **380 regression tests passed in 162.45 seconds**. The live runs exercised the improved visible excerpt path; on-demand invocation retrieval is established by the regression tests, not claimed as a live model action in these runs.
