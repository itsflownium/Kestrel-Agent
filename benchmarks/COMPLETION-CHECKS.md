# Executable completion checks

Kestrel now supports bounded deterministic comparisons of definite action results, complete JSON output, and current saved UTF-8 text/JSON artifacts. Contracts are proposed in the plan from the original request; they are not an independent guarantee that the plan covers every requirement. Jev retains original-task and semantic verification. A model verdict cannot override a failed comparison.

Contracts survive checkpoint/resume and cannot disappear through plan omission or a direct answer. Repairs may rebind a result reference to a new action but cannot change its expected outcome. File checks reread through existing file permissions after each plan and before a direct answer. These are point-in-time checks, not protection against subsequent external edits. They execute no verifier code or commands. Invalid/truncated text, missing values, uncertain/skipped execution, duplicate JSON keys, and non-finite JSON fail closed. A requested nonzero exit can be checked without reclassifying that invocation as successful.

Validation: **231 offline tests passed in 31.31 seconds**. This includes false-positive controls, checkpointed failure/direct-answer handling, exact JSON type and array order checks, file freshness, read permission enforcement, and recovery without weakening expectations. `git diff --check` passed.

## Live paired development fixtures

Model: GPT-6 Astra medium, fresh sessions/default prompt, Jev gates and reviews in Kestrel. One trial per task, shuffled arm order. These development fixtures are not a broad held-out evaluation. Both implementations passed independent output/artifact and recursive workspace-scope grading on all three tasks.

| Task | Kestrel seconds | Direct Codex seconds | Kestrel generation / Jev calls |
| --- | ---: | ---: | ---: |
| Preserve upstream edit and append exact newline | 23.855 | 12.430 | 2 / 5 |
| Run once, observe failure and counter without retry | 21.737 | 10.227 | 2 / 4 |
| Create and verify exact JSON and text artifacts | 22.292 | 12.048 | 2 / 4 |

The first fixture recorded a successful deterministic exit-code contract. The artifact fixture recorded successful `file_json_equals` and `file_text_equals` checks plus source hashes. The expected-failure fixture declared no exact contracts, and one semantic criterion caused an extra planning round; it still executed the script exactly once and returned the correct observation. All traces are retained, including that revision.

Raw evidence: `results-completion-checks.json` and `results-completion-artifacts.json`, with prompts, fixtures, source/harness hashes, traces, usage, and grader results. Kestrel was slower on this sample. The results show exercised safeguards and successful outcomes, not superiority, reliable cost savings, or improved population-level quality.
