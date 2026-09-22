# Standard Kestrel versus direct Codex — 2026-09-22

Jev was disabled for every Kestrel run in this report. Both arms used `gpt-6-astra` with medium reasoning. Results are small-task evidence, not a claim that either agent is generally better.

## Small coding repair

Task: repair a Python normalization function to support arbitrary string iterables, trim/lowercase values, omit blanks, deduplicate in first-occurrence order, and preserve its input. Only `labels.py` could change. Each arm received an identical isolated fixture. Two repetitions used shuffled arm order (seed 221).

| Arm | Passed | Times | Scope violations |
| --- | --- | --- | --- |
| Kestrel standard | 2/2 | 47.365 s, 45.519 s | 0 |
| Direct Codex | 2/2 | 24.227 s, 35.891 s | 0 |

Independent checks imported the actual edited module rather than trusting the answer. A subsequent regrade applied 500 seeded cases to each of the four saved implementations: lists, tuples, iterators, generators, one-pass iterables, Unicode, whitespace, duplicates, empty inputs, and preservation of the original collection. All four passed all 500 cases. The regrade was never shown to the agents. Retained implementations use general normalization logic, not fixture-specific answers.

Kestrel made two generation calls and two same-model decision calls per run, with zero Jev calls. Its verification remained enabled. Direct Codex was faster here; observed correctness was tied. These tests do not prove behavior on every possible iterable or invalid input outside the task's contract.

## Browser form task

| Arm | Outcome | Time | Jev calls |
| --- | --- | --- | --- |
| Kestrel standard, current build | Pass | 71.867 s | 0 |
| Direct Codex, retained native baseline | Pass | 66.379 s | 0 |

Both used the same local form and browser adapter. Each had to save a fresh record name exactly once, observe the visible confirmation, report the correct name, and leave workspace files unchanged. The independently recorded server ledger and browser observations support both passes.

The baseline was run earlier in this session and uses automatic approval review, while Kestrel uses fixture-scoped controller approval. Timings are not controlled paired performance measurements. This tests a browser workflow, not native desktop/canvas/vision competence. Observed quality is tied; Kestrel superiority is not established.

## Artifacts and reproduction

- `results-standard-coding-sep22.json`: full coding traces, artifacts, manifests, oracle results and usage.
- `results-standard-coding-regrade-sep22.json`: independent randomized regrade.
- `results-browser-standard-sep22.json`: current standard-mode browser observations and server ledger.
- `results-browser-direct-codex-reviewed.json`: native browser baseline.

```sh
python benchmarks/workloads.py --agent-mode standard --tasks code_edit_variant --repeat 2 --seed 221 --output benchmarks/my-standard-coding.json
python benchmarks/regrade_coding.py benchmarks/my-standard-coding.json benchmarks/my-coding-regrade.json
python benchmarks/browser_agent.py --mode standard --output benchmarks/my-standard-browser.json
```

The first and third commands contact the configured model. The regrader uses the command sandbox, with no model generation. It executes retained code only in disposable workspaces. The browser test requires the browser extra and its matching Chromium runtime.
