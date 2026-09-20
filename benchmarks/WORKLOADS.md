# Broader workload comparison — September 20, 2026

For the newer result-reuse, failure-branch, and changed-input experiments, see [the follow-up report](RESULT-REUSE.md).

The initial broader suite exposed a completion failure and substantial overhead on several general tasks. Kestrel initially passed 4/5 tasks; direct Codex passed 5/5. After targeted fixes, Kestrel and Codex each passed all four retested tasks. The coding task passed in the initial run and was not rerun after the controller changes. These results do not establish general superiority.

Both arms used GPT-6-Astra with medium reasoning, the same account/SDK, identical isolated workspace fixtures, and workspace-scoped access. Kestrel additionally used Jev. Task execution is timed end-to-end; independent grading and cleanup are excluded. Model API access remained available; task instructions prohibited outside data and network work. Each trial used a fresh workspace, thread, and Kestrel session. Arm order alternated by task.

| Task | Kestrel before | Kestrel after | Direct Codex in matching after trial | Outcome |
| --- | ---: | ---: | ---: | --- |
| code_edit | 40.73 s | Not rerun | 67.60 s (initial trial) | Both pass |
| multi_file | 24.84 s | 24.06 s | 13.89 s | Both pass |
| csv_totals | 51.34 s | 26.25 s | 12.74 s | Both pass |
| tool_recovery | 38.72 s (failed) | 43.02 s | 20.67 s | Both pass |
| ambiguous_selection | 26.57 s | 17.13 s | 11.60 s | Both pass |

## What the checks actually verify

- Coding: an independent evaluator imports the edited function and checks empty lists/iterators, generators, negatives, and floating-point inputs. Model-written tests are not the sole oracle. Scope assertions about unrelated file changes are not exhaustively graded.
- Multi-file policy: parse the final JSON and require the correct release plus a nonempty explanation. The deterministic check does not grade every nuance of the explanation; raw answers are retained for inspection.
- CSV: parse final JSON and compare exact regional totals against an independent expected result, including cancelled rows, refunds, and invalid amounts.
- Recovery: require the correct final result and successful command output in the recorded trace, not merely a proposed command.
- Ambiguity: require exactly TIE for equal cheapest eligible records.

## Fixes made from evidence

1. **Completion now checks the original request.** The initial recovery plan stopped at diagnosis because its own partial criteria passed. A Jev completion question now checks every original requested action, including before an answer-only replan can finish.
2. **Answer-format checks happen at the right stage.** Final-response-only criteria can be deferred until a response exists. Final review includes requested formatting; the finalization prompt no longer demands citations when the user explicitly asks for JSON only.
3. **Generic table queries replace generated scripts where possible.** query_table supports CSV/JSON filtering and sum/mean/count/min/max with dynamic column names and Decimal arithmetic. It reports invalid values, skips, precision, and rounding. CSV generation calls fell from three to two and latency fell about 49%, but remained slower than direct Codex.
4. **Single-file fast paths exclude named multi-source requests.** A JSON record selection cannot shortcut a request that also depends on a separate policy document.

## Limits and what to add next

These are small synthetic engineering tasks, with one observation per task/arm/version. There are no statistically meaningful p95 measurements, dollar-cost measurements, or broad real-world quality scores. Baseline latency varied between runs. Kestrel’s coding win is one observation; its weaker general-task results should not be hidden by averaging in cheap arithmetic tests.

Forty offline tests pass, including new completion, response-stage, multi-source, and table-operation regressions. The earlier provider mocks and UI checks remain separate; this suite does not validate live third-party providers, all security boundaries, memory learning, GEPA optimization, or long-running interruption recovery.

See [ranked next steps](NEXT-STEPS.md) for the roadmap based on these failures. Highest priorities are explicit failure branches and minimal repair, deterministic data tools, and a provider-native execution loop that reduces planning/finalization overhead while retaining Jev bounded decisions.

## Reproduction

`python benchmarks/workloads.py` runs the full live suite. Use `--tasks multi_file,csv_totals,tool_recovery,ambiguous_selection --output PATH` for targeted reruns. This spends provider usage. Fixtures are embedded only in the benchmark harness; application code does not import them or inspect benchmark names.

`results-workloads.json` preserves initial trials and failures. `results-workloads-after.json` preserves the targeted reruns. Both include input fixtures, raw answers, traces, artifacts, grading results, timings, and source hashes. Temporary workspace links in raw model answers no longer resolve after cleanup; source contents are preserved in the result files.
