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

Results are pending. This protocol does not establish universal superiority, cost advantage, secure execution of adversarial generated code, or behavior under abrupt process death/disk durability failures. The fault injection checks the specified error path, not all filesystem failure modes.
