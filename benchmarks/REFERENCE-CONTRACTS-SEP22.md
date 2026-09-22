# Tool-result reference contracts — 2026-09-22

The previous multi-file follow-up contains a timeout after a plan referenced `${skill.content}`. The actual `load_skill` result exposes `guidance`; the catalog did not document that field. The prior failure remains in `results-multifile-evidence-focus.json` and is not upgraded by this work.

## Changes

- Document the actual skill-result shape, including `${action.guidance}` for both skill bodies and reference files. Describe generation/choice through the selected services; retain the explicit Codex-only limitation of built-in web research.
- Failed bindings identify the attempted reference, object/list location, available key names or list length. Values are omitted, terminal controls are escaped, and diagnostics are bounded. Missing fields are errors, never guessed aliases or silent fallbacks.
- Validate dependency references in decoded JSON argument values, matching actual binding. JSON Unicode escapes cannot hide a dependency, and dictionary keys remain literal.
- Preserve whole-reference value types, existing negative list indexing, and the rule that binding does not evaluate code.

## Validation

Targeted checks cover dictionary/list/scalar failures, bounded Unicode diagnostics, hidden dependency references, literal dictionary keys, unchanged successful binding, actual skill output, and a rejected write's saved invocation receipt. The rejected reference must not dispatch the tool, create a file, or become an uncertain external effect. The complete regression suite passed: **564 tests in 539.33 seconds**. Wheel and source distribution builds also passed. The full-suite run includes the final decoded-reference validation and bounded-diagnostic changes.

The live smoke uses Astra medium in standard mode with zero Jev calls. A disposable skill contains a new random marker and Unicode text. The harness supplies an initial plan with the deliberately wrong `${skill.content}` reference; the real controller must handle the failure and replan. It does not supply a recovery plan or the expected artifact to the model. An independent grader compares saved bytes with the loaded guidance, rejects nonregular/symlink output, checks workspace scope, and verifies that the failed invocation never reached the executor.

Result: **passed**, 106.003 seconds, three generation calls and four standard decision calls. The bad binding was recorded without dispatch, the diagnostic named `guidance`, the exact text was saved, no other workspace paths changed, and the agent returned `SAVED`. Source/harness hashes, observations, invocation-related traces and outcome hashes are in `results-reference-recovery.json`.

This is a controlled fault-recovery smoke, not a native-Codex comparison or evidence that naturally generated plans never make reference mistakes. Extra reviews and a workspace inventory were needed before completion, so it does not demonstrate a speed win. The larger coding comparison was not rerun for this contract-only change; its last measured result remains Kestrel 1/2 versus native Codex 2/2.
