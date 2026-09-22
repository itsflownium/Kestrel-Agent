# Review evidence capacity — 2026-09-22

The final reference-contract coding run completed correctly but needed a repair plan solely to retrieve specification, write invocation and verification-command text already held in memory. Its first review explicitly reported truncated parser, CLI and regression evidence; after retrieval it accepted the same code and checks. Both agents passed 334 conditions, but Kestrel took 235.894 seconds versus native Codex's 132.722 seconds. That result is preserved.

## Change

Before the post-execution completion review, Kestrel expands existing argument/result excerpts when the complete text fits the decision provider's existing `2 * max_context_chars` serialized-state limit. Execution and source observations have priority over generated proposals. The decision view includes the existing request, requirements, receipts, saved context and response candidate when measuring space. No extra tool or model call is required to expose retained text.

Expansion is all-or-nothing per argument/result field. A field that cannot fit keeps its original truncation flag and evidence references. Explicitly requested evidence pages retain their offsets. Historical records, execution status, exact completion checks, semantic review and final-answer review remain in place. Oversized essential state still reaches the provider's explicit size rejection; requirements are not discarded to make a review pass.

Ordinary excerpt allocation now measures serialized JSON string cost, including Unicode and escaping. This prevents non-ASCII excerpts from unexpectedly exceeding their text allowance while preserving complete short commands when enough capacity exists.

The change can increase input tokens per review. Fewer repair calls or lower total cost are hypotheses until measured; it is not a free speed optimization.

## Validation

The recorded coding trace is replayed structurally: the full saved write arguments and verification command fit before review, with original result receipts and source data intact. Additional tests exercise Unicode limits, failed/uncertain effects, immutable histories, retained explicit-page offsets and essential-state rejection. All **111 related tests passed in 67.62 seconds**, including evidence retrieval, invocation receipts, answers, completion checks, tool contracts and standard/Jev decision paths. Wheel and source builds passed. The complete 564-test suite passed for the preceding checkpoint; it was not repeated for this change. Initial test failures exposed Unicode-cost and spare-capacity mistakes, both corrected before the final passing run.


## Live paired follow-up

The unchanged multi-file harness ran one pair on the same exposed task, with Astra medium, standard mode, seed 48213, a five-minute limit and 20 permitted generation calls. Native Codex ran first. This is a repeated-fixture regression, not a new held-out result or a counterbalanced multi-trial experiment.

| Agent | Completion/grading | Seconds | Scope |
| --- | --- | ---: | --- |
| Native Codex | Passed, 334/334 | 121.196 | Passed |
| Kestrel standard | Passed, 334/334 | 200.306 | Passed |

Kestrel used one plan and one completion review, then generated and reviewed its final response: five generation calls, two decision calls, zero Jev calls. It did not need an evidence-retrieval repair plan. All original-task requirements were accepted from observed writes and verification. Independent saved-artifact grading also passed the original 334 conditions and the additional post-protocol 80-digit exactness diagnostic for both agents.

Against the preceding Kestrel run, observed elapsed time fell from 235.894 to 200.306 seconds (about 15%), generation calls from six to five, and decision calls from three to two. Recorded generation/decision input tokens were 75,679/47,910 versus 104,815/68,594 previously. These are SDK-reported token counts, not dollar prices or proof of a repeatable cost reduction; sampled plans and model timing vary. Native Codex remained about 1.65 times faster in this pair. The larger task corpus and prior failures are unchanged.

Raw results: `results-multifile-review-capacity.json`. Independent audit: `results-multifile-review-capacity-artifact-audit.json`. Source and grader hashes, traces, retained artifacts, usage and scope manifests are preserved.
