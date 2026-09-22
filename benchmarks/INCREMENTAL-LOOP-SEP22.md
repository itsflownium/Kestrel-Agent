# One-action controller assessment — 2026-09-22

## Question and policies

Does planning one action at a time improve completion on a browser interface whose next controls and values appear only after an earlier effect?

The existing graph controller remains the production default. The internal `_incremental_experiment` switch is used only by this benchmark; it is not a saved setting or CLI mode. It constrains plans to one action and returns each resulting observation to the planner without a separate whole-task semantic review after every incomplete step. Proposed final answers still pass original-task and answer-support reviews, and retained exact contracts are checked before answering. Permissions, action conditions, effect receipts, dependency execution, time/model/step budgets and no-progress limits use the existing controller. This compares two execution policies, not merely two prompts with identical decision-call counts. The experiment does not individually review every accumulated semantic criterion at each intermediate step; original-task final review receives the retained requirement ledger.

## Frozen task and grading

`incremental_browser.py` opens an isolated local shipping form. Prepare replaces the initial control with a confirmation code and input. Submit replaces those controls with a receipt. Both backend transitions delay their response by 250 ms, so a tool's immediate observation can show a transition rather than the final state. Controls and observation tokens must be refreshed as needed. Neither controller receives the expected code or receipt in the task.

Each pair uses the same seed-generated values and task, a separate browser/context/workspace, the same Astra medium model, standard mode with no Jev, the same browser adapter and fixture-only approval policy, and the same tool/model/time budgets. Arm order is shuffled with seed 52913. Two pairs run sequentially; no regression suite or other live model benchmark runs concurrently. This is one synthetic task family with two parameter variants, not broad held-out agent coverage.

The independent grader requires exactly one prepare followed by exactly one submit with the correct code, a successful browser observation of the resulting receipt, the exact receipt as final answer, no workspace changes and no out-of-scope tools/services. False-pass tests reject duplicate/reversed effects, incorrect inputs/answers, missing or failed observations, unexpected files and service/tool scope violations.

## Decision rule set before results

Do not change the global default based on these four runs. Any incremental failure prevents promotion on this evidence. If both policies pass, compare their individual timings and model/decision counts descriptively; a quality tie is not superiority. A promising result justifies broader tests across other task families. Preserve all failures and setup exclusions, including slow runs; do not rerun selectively to obtain a favorable result.

## Guard validation

Eight experiment tests exercise the single-action schema and unchanged default, real file execution, final original-task/answer-support rejection, exact-contract rejection before semantic review, multi-action workflow rejection before effects, no-progress limits and denied writes, and model-schema correction. Combined with the existing fixed-response tests, 24 passed. Twelve independent browser-grader cases passed. The focused 24-test command was accidentally submitted twice while the first was pending; both completed before live trials began (72.12s and 71.82s). No live trial was duplicated for that reason.

## Results and decision

| Pair | Policy | Passed | Seconds | Generation calls | Decision calls | Total model calls |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 0 | One action | Yes | 93.274 | 8 | 1 | 9 |
| 0 | Graph | Yes | 124.295 | 6 | 6 | 12 |
| 1 | One action | Yes | 83.043 | 7 | 1 | 8 |
| 1 | Graph | Yes | 125.343 | 6 | 6 | 12 |

Both policies passed 2/2, including independent effect counts, code/receipt correctness and scope checks. No Jev calls occurred. The one-action mean was 88.159 seconds versus 124.819 seconds for graph execution, a descriptive 29.4% reduction in this sample. Its runs used more generation turns but fewer intermediate whole-task decisions. Recorded input/output tokens were 177,499/1,065 and 154,993/966 for one-action planning, versus 211,842/1,745 and 211,483/1,693 for graph planning. These totals do not establish dollar savings: caching and subscription pricing are not normalized.

The seeded shuffle happened to put one-action first in both pairs, so order was not counterbalanced. Runs 2–4 logged an ASGI incomplete-response / GET-stream reconnect warning during catalog startup; POST tool calls and both effect ledgers succeeded. Those runs and their timings are retained. Model nondeterminism, provider caching and host conditions are uncontrolled. These are not four independent task families, and no native-Codex or Hermes arm was evaluated.

Decision: retain the graph controller as the default. Keep the one-action path restricted to the benchmark harness while broader coding, research, recovery and visual evaluations are missing. The evidence supports further testing for dynamic browser interactions; it does not establish superior quality, general speed, or readiness as the default for coding and other work. The experiment also does not certify resuming a task under a changed controller policy or persisting per-criterion semantic verdicts after its final aggregate review.

Raw plans, observations, action ledgers, timings and model usage are retained in `results-incremental-browser.json`. The harness SHA-256 is recorded. Reproduce explicitly with:

```sh
PLAYWRIGHT_BROWSERS_PATH=/path/to/runtime python benchmarks/incremental_browser.py --repeat 2 --seed 52913 --output benchmarks/my-incremental-browser.json
```

This command contacts the configured Codex account and controls only isolated local browser fixtures.

## Final regression

After all four live trials ended, the full regression suite passed **510 tests in 376.83 seconds**. Source and wheel builds passed, and wheel inspection confirms the experiment guard defaults to false. `git diff --check` passed. The live trials were not repeated after seeing their outcomes.
