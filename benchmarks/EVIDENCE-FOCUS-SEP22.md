# Evidence-context repair assessment — 2026-09-22

## Observed defect

The first multi-file coding assessment is preserved in [MULTIFILE-CODING-SEP22.md](MULTIFILE-CODING-SEP22.md). Both Kestrel runs produce code that passes the independent checks, but one hits the 300-second deadline and the other reaches the step limit. Reviews request missing implementation/command evidence; subsequent `read_evidence` pages are truncated by the same equal-share excerpt packing that omitted the details originally.

## Generic change

Explicitly retrieved pages now receive a bounded contiguous view, prioritized by recency and deduplicated by source ID/offset. The view preserves original metadata and exposes a continuation offset for any additional context truncation. Serialized JSON size, including escaping and Unicode, determines the text allowance; offsets still address original source characters. Unused page capacity is returned to ordinary observations. No completion requirement, effect permission, review question, task budget, or model setting is relaxed.

Focused checks cover several retrieved pages among older results, Unicode and escaping, source-aligned continuation across actual stored evidence, unchanged historical receipts, failed-effect status preservation, deduplication/recency, and reclaiming spare capacity. An initial regression run was deliberately interrupted after 159 passing tests to add the spare-capacity case; it is not counted as a completed suite.

## Follow-up protocol

After the final regression suite finishes, rerun the same two matched multi-file pairs with the same seed, Astra medium, standard mode, five-minute wall limit and 20 model-call cap. The independent grader remains unchanged. Save follow-up results separately; the task is now an exposed-fixture regression, not new held-out evidence. Preserve every failure and any slower result. Independent artifact checks cannot turn an incomplete agent run into a pass.

```sh
python benchmarks/workloads.py --tasks multifile_ledger --agent-mode standard --repeat 2 --seed 48213 --max-minutes 5 --max-model-calls 20 --output benchmarks/results-multifile-evidence-focus.json
```

The first finalized allocation passed 547 tests (20 focused plus 527 remaining regressions). A subsequent low-context metadata stress check exposed another size edge, now addressed by omitting older observation views with an explicit count while preserving historical records, task requirements and the newest page. The final guard passed 21 evidence tests and 69 related completion/decision/recovery checks; the refreshed wheel/source build also passed. These focused final checks followed the earlier complete 547-test run; the entire suite was not repeated after the narrow metadata guard. Live results follow below. Broader coding/task-family performance and universal superiority remain unestablished.


## Follow-up results

| Execution order | Repetition | Arm | End-to-end result | Seconds |
| --- | --- | --- | --- | ---: |
| 1 | 2 | Kestrel standard | Timeout during additional-test generation | 301.132 |
| 2 | 2 | Native Codex | Passed all 334 independent checks | 111.094 |
| 3 | 1 | Kestrel standard | Passed all 334 independent checks | 217.155 |
| 4 | 1 | Native Codex | Passed all 334 independent checks | 108.908 |

All four runs respected the permitted file scope. Kestrel used zero Jev calls, six generation calls in each run, and one/three standard decision calls respectively. The timed-out generation has missing token usage in telemetry; zero reported tokens for that cancelled call must not be treated as zero cost.

In the successful Kestrel run, the first original-task review reports missing truncated evidence. After one retrieval plan, the next review marks the task complete, and final-answer review succeeds. This directly exercises the repaired retrieval path. The initial unchanged-controller runs were 0/2; follow-up Kestrel is 1/2 while native Codex remains 2/2. The successful Kestrel run is roughly twice as long as its paired native run. Two repetitions of an exposed task do not establish a general quality or speed improvement.

The failed follow-up starts with a reference to `${skill.content}` although `load_skill` returns `guidance`. The tool catalog did not document that output field. The controller recovers by replanning, writes the modules and runs the example checker, then reaches the wall-time limit while generating additional tests. Telemetry attributes about 87 seconds to initial planning, 65 seconds to replanning, and 57 seconds to the three completed code-generation calls, followed by roughly 50 seconds in the cancelled test-generation call. This is a distinct remaining usability/reliability issue; it is retained rather than excluded from the score.

Raw records are in `results-multifile-evidence-focus.json`. A no-model audit of the retained artifacts is in `results-multifile-evidence-focus-artifact-audit.json`; all four saved implementations pass the original 334 checks and the separate 80-digit exactness check. These artifact diagnostics do not upgrade a timed-out run. The configured 20-call cap exceeds the product's default six-generation-call cap, so this assessment is not an out-of-box default-settings claim.

Next targets are explicit built-in tool output contracts and actionable failed-reference diagnostics, followed by measuring whether related artifact generation can be consolidated without weakening execution or verification. The observed comparison still favors native Codex for this task; universal superiority and overall project completion remain unproven.
