# Multi-file coding assessment — 2026-09-22

## Frozen protocol

The first live assessment of this task uses the unchanged standard Kestrel controller and native Codex, both with `gpt-6-astra` at medium effort. Jev is disabled. Each arm receives an identical fresh package with three faulty modules, a complete specification, and one public example checker. The independent checker is not put into the agent workspace or prompt.

Two paired repetitions run sequentially in seeded shuffled order (`48213`), with a five-minute wall-time limit per arm. Kestrel has at most 20 model calls; native Codex has its own internal call behavior within the same wall-time limit. Network, connected apps, configured MCP servers and plugins are disabled for native Codex; Kestrel uses workspace permissions and no network. Timings exclude independent grading and teardown. The repeated task is one family, not a broad held-out benchmark.

The task requires cross-module CSV validation, exact decimal aggregation over single-pass inputs, and a UTF-8 JSON CLI with atomic replacement and failure cleanup. The grader checks 334 conditions: 100 generated valid datasets, malformed data, iterator and mutation behavior, real subprocess CLI outputs/statuses, preservation of existing output, and injected `os.replace` failure. A recursive workspace manifest independently rejects edits outside the three permitted modules. The checker runs after the agent finishes and is not used for agent repair.

Before live calls: 16 focused tests passed, including a known-correct implementation and seven broken variants (float conversion, wrong status filtering, early truncation, missing atomic replacement, leaked temporary file, duplicate-ID acceptance and dropped non-settled rows). Fixture, harness and product-source hashes are retained with the live records. No product code is changed in response to this task before its first assessment; any later fixes and reruns will be labeled as exposed-fixture results.

Command:

```sh
python benchmarks/workloads.py --tasks multifile_ledger --agent-mode standard --repeat 2 --seed 48213 --max-minutes 5 --max-model-calls 20 --output benchmarks/results-multifile-coding.json
```

This protocol does not establish universal superiority, cost advantage, secure execution of adversarial generated code, or behavior under abrupt process death/disk durability failures. The fault injection checks the specified error path, not all filesystem failure modes.


## Initial results — unchanged controller

| Execution order | Repetition | Arm | End-to-end result | Seconds | Independent saved-code checks |
| --- | --- | --- | --- | ---: | --- |
| 1 | 2 | Kestrel standard | Failed to complete within 300-second limit | 300.669 | 334/334 passed in separate audit |
| 2 | 2 | Native Codex | Passed | 139.361 | 334/334 passed |
| 3 | 1 | Kestrel standard | Failed: step budget reached | 263.971 | 334/334 passed in separate audit |
| 4 | 1 | Native Codex | Passed | 116.682 | 334/334 passed |

The seeded shuffle happened to put Kestrel first in both pairs; this is not a counterbalanced timing study. All four artifact sets stayed within the permitted file scope. Kestrel used zero Jev calls, with 7/6 generation calls and two standard decision calls respectively. The first run's exception message is empty in the original harness; the 300-second outer deadline and interruption trace identify the time-bound failure. The second records an explicit step-budget error. Initial artifacts and traces are retained unchanged in `results-multifile-coding.json`.

Both Kestrel traces record successful writes, example/edge-check actions and passed executable exit-code contracts. Their semantic reviews repeatedly report truncated specification, implementation and regression-command evidence. A repair plan retrieves the omitted snapshots, but the context packer evenly divides its excerpt budget over up to 16 observations and truncates those retrieved pages again. This is an observed completion failure, not evidence that code edits failed. The independent saved-artifact audit in `results-multifile-coding-artifact-audit.json` confirms all four implementations pass the original 334 checks. A separate, post-protocol 80-digit exact-total check also passes for all four; it does not replace or upgrade the failed end-to-end results.

The initial harness copied command output only after successful agent return, so failed Kestrel records have empty `observed_commands`. Their action and exact-contract traces remain available. Subsequent harness runs now preserve observations and command receipts in `finally` and include exception types, making incomplete-run diagnostics more direct. No initial result was overwritten.

Conclusion: native Codex completes 2/2; the unchanged Kestrel controller completes 0/2 on this new task despite correct saved code. Address the general evidence-retrieval truncation loop and rerun transparently as an exposed-fixture regression. Do not claim a quality or speed win from the artifact-only audit.
