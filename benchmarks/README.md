# Jev-led comparison — September 20, 2026

The final version was faster on five of six small tasks, with the expected answers from both systems. Open-ended writing was slower. This is evidence for bounded-workload improvements, not proof of overall superiority or lower dollar cost.

Both arms used GPT-6-Astra with medium reasoning through the same installed Codex SDK/account. Kestrel used jev-latest. Fresh isolated workspaces contained identical inputs; requests ran sequentially with alternating arm order. Times include startup and execution, excluding cleanup. This compares complete tool harnesses, not isolated model latency.

| Task | Direct Codex | Kestrel | Kestrel Codex/Jev calls | Checks |
| --- | ---: | ---: | ---: | --- |
| arithmetic | 4.64 s | 1.42 s | 0/1 | Both pass |
| selection | 8.19 s | 1.88 s | 0/2 | Both pass |
| renamed_fields | 7.97 s | 2.01 s | 0/2 | Both pass |
| shuffled_values | 7.34 s | 1.65 s | 0/2 | Both pass |
| no_match | 10.33 s | 1.85 s | 0/2 | Both pass |
| open_ended | 6.36 s | 12.02 s | 1/1 | Both pass |

## What changed

Jev now routes each new request before any Codex planning call. Read-only, bounded recipes handle exact single-expression arithmetic and selection over small JSON arrays. Jev selects a candidate and output fields from the actual schema, then separately checks the result. Open-ended work falls back to the general Codex/controller loop. Unsupported/ambiguous results do not become invented fast answers.

No benchmark names, prices, expected winners, or task-string lookups exist in application code. The schema suite changes field names, generates new supplier IDs/prices with independent reproducible seeds, and shuffles input order. Test-only oracle code computes the expected supplier using constraints; it is not imported by the application. Fast paths are intentionally limited reusable capabilities, not unrestricted task understanding.

## Quality and cost interpretation

All six final prompts passed their stated checks: exact numeric answers, correct selected ID and amount, exact no-match marker, and a two-sentence list/tuple explanation covering mutability. Both systems met those checks. These small checks do not establish general answer-quality superiority. Codex inferred a dollar symbol on an input without currency in the original selection case; Kestrel preserved the actual field labels and values. The renamed-schema cases explicitly specify EUR.

The five bounded cases used zero Codex calls and one or two Jev calls. This reduces Codex subscription usage on those cases; it does not prove lower dollar cost, because subscription billing is not per-request API billing and Jev charges were not measured. The general-generation case used one Codex call plus a Jev routing call and was slower.

## Coverage and limitations

- Twenty-one offline tests pass, including permissions, bindings, arithmetic boundaries, failed-verification fallback, and schema-derived output fields. Compilation and whitespace checks pass.
- Terminal startup, help, and clean exit were exercised in an isolated PTY. Full visual and interaction acceptance remains pending.
- Earlier additional-suite tests included alternative choices, a different domain, and an instruction hidden inside a record. Both systems selected correctly. Those results predate the final schema-independent formatter and are retained separately.
- One final observation per task/arm is too few for statistical claims, p95 latency, or a realistic overall workload score. Earlier measurements varied with network/cache conditions. The suite is biased toward capabilities deliberately optimized during development.
- No broad coding, MCP, writes, web research, GEPA, learned memory, or recovery benchmark is represented. No model weights were trained.

## Reproduction and preserved evidence

Run `python benchmarks/compare.py --suite original --output benchmarks/results.json` and `python benchmarks/compare.py --suite schema --output benchmarks/results-schema.json` with the installed environment. These commands make live requests. The final records include input data and an application-source SHA-256; credentials and private account data are excluded.

`results.json` and `results-schema.json` are final-version trials. `results-initial.json` and `results-before-fastpath.json` preserve the slow initial design and its first repair. `results-fastpath-v1.json`, `results-fastpath-v2.json`, and additional-suite files preserve intermediate versions. See INITIAL.md for the initial comparison narrative; its claims describe that earlier implementation only.
