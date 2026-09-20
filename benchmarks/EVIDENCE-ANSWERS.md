# Verified evidence answers — September 20, 2026

Kestrel can now propose a final answer from completed tool results even when the planner omitted `final_response_ref`. Jev selects a complete candidate or requests generation in the existing completion-check batch. The new path accepts bounded successful command output, command receipts, table JSON, and generated content. It excludes failed/unknown command outcomes, known truncation, intermediate results consumed by completed actions, and raw file text. Whole-task completion and recovery checks still apply.

Final generated answers also have a stronger review path: rejected drafts are revised once and reviewed again. Previously the revision was returned without another check. Overlong drafts are revised instead of being approved from only a prefix. If the revision still fails, Kestrel reports the verification failure and preserves its checkpoint.

## Repeated live comparisons

Both arms use GPT-6-Astra medium; Jev participates in every Kestrel run. Each case has two trials per arm, alternating arm order and using isolated fixture workspaces. All 12 runs passed execution, answer, and file-scope checks.

| Task | Kestrel trials | Direct Codex trials | Kestrel median | Codex median | Kestrel generation / Jev calls |
| --- | --- | --- | ---: | ---: | --- |
| Exact JSON command output | 10.703, 11.132 s | 11.807, 7.634 s | 10.918 s | 9.721 s | 1 / 3 |
| Missing-argument recovery | 24.725, 26.251 s | 23.367, 19.604 s | 25.488 s | 21.486 s | 2 / 5 |
| Two-argument recovery | 26.855, 24.236 s | 19.342, 24.928 s | 25.546 s | 22.135 s | 2 / 5 |

Three recovery runs used the new automatically offered command receipt; one used the existing explicit stdout reference. Both JSON-only runs used the existing explicit-reference path, preserving exact JSON output. No final generation call was needed in these six Kestrel runs.

The preceding compact-recovery report used 3 generation / 6 Jev calls per recovery case. These runs use 2 / 5: one fewer generation call and one fewer Jev round trip. That is a measurable orchestration reduction, not a billed-dollar estimate. Kestrel won two individual paired timings but **direct Codex has the lower median in all three cases**. Two trials per case are insufficient to establish statistical speed or quality superiority.

## Coding and file-writing regression checks

| Task | Kestrel | Direct Codex | Outcome |
| --- | ---: | ---: | --- |
| Iterable normalization edit | 27.972 s | 37.984 s | Both pass |
| Table aggregation written to JSON | 18.779 s | 20.255 s | Both pass |

These are one paired trial per case, retained in `results-evidence-answer-regressions.json`. Kestrel used 2 generation / 5 Jev calls in each. Jev rejected the coding task's raw test output as an insufficient answer, so Kestrel generated the explanatory response. The table-writing task also retained generation and returned the required exact confirmation after the independent grader verified the file. Both cases preserved file scope. These timings are observations, not established speed wins. Across both result files, each arm passes 8/8 runs.

## Grading improvements

Recovery now requires a recorded successful command with the expected output line. An answer or trace merely claiming that output cannot pass. The new JSON case checks actual execution output and exact response formatting. Tests reject claimed success without execution, nonzero/unknown/invalid exit codes, and Markdown around JSON. Saved runs were also checked against the final stricter grader after adding integer-type validation and exact text matching.

These checks remain task-specific. They do not establish general answer quality or audit every possible external effect. Baseline command observations use the SDK's aggregated command output, whereas Kestrel retains stdout separately. The fixture scripts do not rely on stderr for their expected answer.

## Validation and reproduction

121 offline checks pass, including missing-work guards, declined reuse, unknown exits, truncation, stderr preservation, and review of revised answers. Application logic contains no benchmark names, expected totals, or fixture imports. The application source hash is unchanged across the live runs and matches the submitted source.

Raw repeated results: `results-evidence-answers.json`. Run explicitly (consumes live usage):

```sh
python benchmarks/workloads.py --tasks command_json,tool_recovery,recovery_two_arguments --repeat 2 --output NEW_RESULT_PATH
python benchmarks/workloads.py --tasks code_edit_variant,table_write_variant --output OTHER_NEW_RESULT_PATH
```

Timing includes orchestration/model/tool work and excludes the independent grader and cleanup. Inputs, original answers, execution observations, traces, file artifacts, and source hashes are retained. Model/cache/runtime variability is substantial; no overall superiority or cost claim is made.
