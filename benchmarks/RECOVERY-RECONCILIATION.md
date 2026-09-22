# Recovery and effect reconciliation

Plans now retain an unchanged successful subgraph during repairs. Local read hashes and write artifact hashes are checked again; changes invalidate dependent reuse. Unrecognized read kinds are rerun. Completed command receipts describe historical execution, not current file freshness. This conservative mechanism may reread an input changed by its own downstream write; it does not assume general program equivalence.

Effect identities normalize argument defaults, workspace paths, write targets/content, and explicit script paths for a bounded set of interpreters. They do not reorder options or reinterpret arbitrary command operands. Failed identical effects require retry approval. Related command/MCP retries also require review when prior effects are uncertain or workspace snapshots show changes or are incomplete. Receipts survive interruption; approval shows the proposed retry and prior receipt. Workspace snapshots cannot prove absence of transient or external effects, and these guards do not implement automatic rollback.

Validation: 242 tests passed in 40.15 seconds. After refining the retry review text and pre-dispatch cancellation handling, 41 focused recovery/command-repair/interrupt tests passed in 14.14 seconds. Tests exercise actual engine replanning, no replay of completed commands, source invalidation, canonical retries, partial failure and process-death restoration.

The initial full suite caught an accidental collision with the existing command-repair module (10 failures). The original module was restored and the new implementation moved to `reconciliation.py`. The initial live trace is retained in `results-recovery-reconciliation-initial.json`: both tasks eventually passed via fallback, with recovery taking 58.384 seconds versus direct Codex 19.657 seconds. This is not the final implementation's timing.

After the correction, fresh GPT-6 Astra medium/Jev paired runs passed both independent graders:

| Task | Kestrel | Direct Codex |
| --- | ---: | ---: |
| Recover two required command arguments | 26.067 s | 21.050 s |
| Observe partial failure without retrying | 19.830 s | 11.741 s |

Raw final traces: `results-recovery-reconciliation.json`. Each is one development trial, not a broad held-out result. There is no overall quality or speed superiority claim. The live tasks cover compatibility with recovery/failure observation; subgraph reuse and retry-denial properties are established by targeted engine tests.
