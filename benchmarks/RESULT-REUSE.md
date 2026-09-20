# Result reuse and recovery experiments — September 20, 2026

This follow-up tests controller changes rather than claiming universal superiority. Both arms use GPT-6-Astra at medium reasoning. Kestrel also uses Jev. Inputs, outputs, action traces, source hashes, timings, and failures are retained in the JSON files.

## Added capabilities

- An optional `final_response_ref` lets Jev verify and return an existing tool answer, avoiding final generation when the exact answer is already available. It cannot override incomplete task checks or failed execution.
- Explicit success/failure/completion dependencies support recovery branches. Skipped recovery branches propagate skips. Transport failures remain uncertain rather than ordinary retryable failures.
- Evidence includes tool names, arguments, and execution status, helping judgments distinguish execution from proposed work.
- Table tools provide numeric JSON without loss through a binary-float conversion.

These are generic application features. Benchmark prompts, file names, and expected answers are confined to the benchmark harness.

## First iteration

`results-result-reuse.json` records the version before evidence provenance and recovery-prompt improvements.

| Task | Kestrel | Direct Codex | Correctness | Direct tool-answer reuse |
| --- | ---: | ---: | --- | --- |
| CSV totals | 19.909 s | 30.597 s | Both pass | Rejected by Jev; generation fallback |
| Command recovery | 65.785 s | 19.247 s | Both pass | None |
| Tied selection | 28.031 s | 10.608 s | Both pass | Used; final generation skipped |

The recovery plan retried before discovering the required input, then successfully recovered on a later plan. Verification also caused a redundant replan over a no-file-edits criterion. Result reuse worked for tied selection but did not make the task faster than direct Codex. Keep these regressions visible when evaluating the feature.

## Final-source comparison

`results-evidence-context.json` records the final application source, with richer evidence and recovery input discovery guidance. All four cases passed for both arms, including the harness's file-scope checks. Jev participated in every Kestrel task.

| Task | Kestrel | Direct Codex | Kestrel generation / Jev calls | Tool-answer reuse |
| --- | ---: | ---: | --- | --- |
| code_edit | 41.384 s | 115.756 s | 3 / 7 | None |
| csv_totals | 22.479 s | 15.084 s | 1 / 4 | Used |
| table_mean_variant | 16.615 s | 30.115 s | 1 / 4 | Used |
| recovery_variant | 43.191 s | 19.418 s | 2 / 7 | Used |

Kestrel was faster in two of four final trials; measured correctness matched Codex on these checks. The CSV path used only one generation call but remained slower than Codex. The changed-schema mean task also used one generation call and was faster. Recovery successfully used failure branches and reused the command output, but still needed two planning calls and took over twice as long as direct Codex. Coding verification triggered a redundant replan despite independently passing the evaluator. These observations favor reducing planning and verification overhead next, rather than adding more Jev calls indiscriminately.

The old CSV baseline varied from 12.743 seconds in the previous report to 30.597 seconds in the first iteration here and 15.084 seconds in the final trial. Fewer generation calls are a demonstrated architectural effect; lower typical latency and dollar cost are not established.

## Validation boundaries

57 offline tests pass, covering result-reuse acceptance/fallback, unfinished-task blocking, dependency outcomes, skipped branches, uncertain effects, execution provenance, and existing provider/tool behavior. Live third-party generation providers were not exercised.

These are small synthetic workloads, not a frozen external benchmark. Each task/arm/version has one trial. Changed-input cases were added before their first run, but are not an independently curated held-out suite. Latency varies substantially, so comparisons are observations rather than estimates of typical speed or causally isolated feature gains. No billing-based cost claim is made.

Reproduce the follow-up with:

```sh
python benchmarks/workloads.py --tasks code_edit,csv_totals,table_mean_variant,recovery_variant --output benchmarks/results-evidence-context.json
```

This uses live provider usage. The latest harness additionally checks that original files other than the authorized coding target retain their contents and that no extra small top-level files appear. It does not exhaustively audit directory trees, large files, or side effects outside the fixture. Table and recovery variants change input schemas/operations and command flags; application code is unchanged between those trials.
