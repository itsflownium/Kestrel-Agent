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

The first finalized allocation passed 547 tests (20 focused plus 527 remaining regressions). A subsequent low-context metadata stress check exposed another size edge, now addressed by omitting older observation views with an explicit count while preserving historical records, task requirements and the newest page. The final guard passed 21 evidence tests and 69 related completion/decision/recovery checks; the refreshed wheel/source build also passed. These focused final checks followed the earlier complete 547-test run; the entire suite was not repeated after the narrow metadata guard. Live results are pending. Broader coding/task-family performance and universal superiority remain unestablished.
