# Initial evidence and direct content plans — September 20, 2026

This iteration targets wasted planning/generation in general tasks. The controller now reads small explicitly named files before the first general plan, retains source hashes and observed missing destinations, and checks direct answers against both original-task completion and answer support. Plans can bind existing tool text directly into later actions.

The final version also permits short self-contained content directly in action arguments, reports the prior hash and verified write precondition, and rechecks file content after user approval. It reserves controller capacity when the configured step budget is very small.

## First iteration

`results-initial-context.json` records the initial evidence/prompt version, before direct inline content and write-receipt improvements.

| Task | Kestrel | Direct Codex | Outcome |
| --- | ---: | ---: | --- |
| code_edit | 40.955 s | 30.147 s | Both pass |
| multi_file | 11.312 s | 14.905 s | Both pass |
| recovery_variant | 50.170 s | 17.668 s | Both pass |
| table_write_variant | 20.252 s | 20.713 s | Both pass |
| multi_file_variant | 8.701 s | 10.899 s | Both pass |

The file-writing plan bound the table's numeric JSON directly to write_file, cutting generation calls from four in the preceding report to two here. Both multi-file tasks completed with one generation call. Coding still triggered an unnecessary replan after Jev rejected the hash-protection criterion despite a successful write and passing checks. Recovery remained much slower than direct Codex; this loss is retained.

## Final-source comparison

The final source passed all four paired comparisons. Jev participated in every Kestrel run. Coding and artifact creation used two generation calls; multi-file ranking used one.

| Task | Kestrel | Direct Codex | Outcome |
| --- | ---: | ---: | --- |
| code_edit | 29.390 s | 39.748 s | Both pass |
| code_edit_variant | 28.618 s | 31.471 s | Both pass |
| table_write_variant | 20.565 s | 18.983 s | Both pass |
| multi_file_variant | 9.825 s | 8.604 s | Both pass |

Both coding plans directly embedded the small edit and passed their verification criteria without replanning. The independent grader checked the resulting files, including generator/empty-input behavior and normalization without input mutation. File creation bound numeric JSON directly into the writer. Relative to the preceding report, that task's Kestrel generation calls fell from four to two and its observed time fell from 51.506 s to 20.565 s; direct Codex remained slightly faster in this final trial. Multi-file ranking had lower Kestrel overhead than the prior general pipeline but still lost this particular paired timing. These measured call reductions are firmer evidence than the small single-trial timing differences.

## Validation and limits

71 offline tests pass. New coverage includes access/size limits for initial evidence, absent outputs, minimal step budgets, unsupported direct answers, post-approval file changes, and clear write receipts. Both newly appearing files and changes to existing files during approval are rejected without overwriting their changed contents. The final hash check narrows the race window; it is not an operating-system compare-and-swap guarantee against simultaneous writers.

The live fixtures include a new coding task (normalization of iterable strings without input mutation) and a new multi-file eligibility/ranking task. Application code uses no benchmark names or expected answers. Coding is checked by independent executable assertions; artifact creation is checked by reading the resulting file. The graders also check allowed file changes, but do not exhaustively audit outside effects or large/directory artifacts.

Both arms use GPT-6-Astra medium; Kestrel uses Jev throughout. Timing includes task execution but excludes the independent grader and cleanup. Each arm has an isolated workspace, and arm order alternates. Each case/version has one trial, so apparent ties and speed differences are not statistically established. Baseline variability remains substantial. No dollar-cost claim is made, and correctness on these checks is not general quality superiority.

Reproduction (uses live provider usage):

```sh
python benchmarks/workloads.py --tasks code_edit,code_edit_variant,multi_file_variant,table_write_variant --output NEW_RESULT_PATH
```

Raw fixtures, answers, timings, source hashes, traces, and output artifacts are retained in results-initial-context.json and results-initial-context-final.json. The first file intentionally represents the earlier source version. Recovery was not rerun after the final small prompt/receipt changes; its slower earlier result must not be counted as a final-version win.
