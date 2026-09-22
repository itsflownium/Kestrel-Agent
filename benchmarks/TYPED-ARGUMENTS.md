# Typed tool argument boundaries

Every tool named in the plan schema now has a strict argument contract. Plan acceptance rejects missing fields, unknown keys, invalid literal types, invalid operations, and out-of-range limits. This prevents errors such as writing the string representation of a null/object value, accepting a shell command string instead of argv, or silently ignoring a misspelled option.

Whole-value result references may defer type validation only at the referenced field. Missing fields and unknown keys are never deferred, and invalid unrelated fields still reject the plan. After reference binding, every tool dispatch validates the complete arguments before storage checks, permission prompts, provider calls, or filesystem effects. Existing path, hash, permission, and sandbox checks still apply; a well-typed call is not automatically authorized.

Existing controller tests that used empty or mismatched fake tool arguments were corrected to use valid examples without changing their behavioral assertions. New controls cover every tool's valid arguments, malformed literals, nested references, wrong bound types, and rejection before any write or command call.

This implements argument contracts, not the separate proposal for executable completion contracts. The latter remains tracked in `docs/ARCHITECTURE-IMPLEMENTATION.md` alongside the other outstanding architecture work.

Live dependent-repair and table-write comparisons are retained in `results-typed-arguments.json`; these are development regression fixtures, not a held-out evaluation.

All **190 offline tests pass**. Both live paired regressions passed for both agents:

| Case | Kestrel | Direct Codex |
| --- | ---: | ---: |
| Dependent command repair | 28.361s | 22.451s |
| Table aggregation bound into a JSON file | 21.195s | 20.157s |

Kestrel used two generation calls in each case, with four Jev calls. No malformed argument correction was needed in either trial. The result supports compatibility of strict contracts with these workflows, not universal quality or speed superiority.
