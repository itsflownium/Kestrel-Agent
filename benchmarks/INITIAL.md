# Initial live comparison — September 20, 2026

These measurements do **not** establish that Kestrel is better, faster, or cheaper than Codex. Direct Codex was faster on both small tasks. Both returned the expected arithmetic result and plan selection.

Both arms used `gpt-6-astra`, medium reasoning, the same account/SDK, fresh threads, and identical isolated task inputs. Kestrel additionally used `jev-latest`. Execution was sequential; order alternated by task. Timings include runtime/thread startup and task execution, excluding cleanup. Authentication/model-list calls and offline checks are outside task timings.

| Task | Direct Codex, initial | Kestrel, initial | Direct Codex, after fixes | Kestrel, after fixes |
| --- | ---: | ---: | ---: | ---: |
| 17 × 23 | 5.810 s | 6.192 s | 4.524 s | 5.321 s |
| Select cheapest eligible plan from JSON | 12.560 s | 46.433 s | 9.241 s | 20.227 s |

The final selection run used two Kestrel Codex calls and four Jev API calls. Arithmetic used one Codex call and zero Jev calls. Both selected Cedar at 12/month. The baseline added a dollar symbol although the input did not specify currency: the automated check only checks the plan name and amount, not full factual grounding.

## Bugs found and addressed

- The configured `jev-1.13` model was rejected by the live service. Its model-list endpoint returned `jev-latest` and `jev-preview`; the default now uses `jev-latest`.
- A planner bound numbered file text into the candidate-selection API. Small JSON files now expose parsed `data`, with explicit binding guidance and a regression test.
- Plans unnecessarily generated a reply before the controller generated its final answer. Planning guidance now avoids that redundant action.

The improved selection run still replanned following a Jev completion check. Reducing unnecessary criteria and orchestration overhead remains future work; no blanket performance claim is justified.

## Usage and limits

On the final selection run, Kestrel reported 35,364 Codex input tokens, 241 output tokens, and 3,524 Jev input tokens. Direct Codex reported 26,298 total input tokens and 57 output tokens. Input counts include cached tokens; cache conditions differed between runs. Subscription usage cannot be translated into a reliable per-request dollar price here, and Jev dollars were not measured.

Only two synthetic tasks were used, with one observation per version/task/arm. There are no statistically meaningful medians or p95 estimates. Both systems could read the same file, but the tool harnesses differ: Kestrel uses its file/decision tools, whereas the baseline uses native Codex tools. This is a system comparison, not an isolated test of Jev model speed. Neither workflow memory nor GEPA was trained or activated; their benefits are not measured. MCP, web research, complex coding, writes, interruption recovery, and broad UI behavior remain unvalidated.

`results-initial.json` preserves the initial trials; `results-before-fastpath.json` contains the post-fix trials. `compare.py` is the post-fix runner. Run explicitly with the installed Python environment; it makes live provider calls and overwrites `results.json`. Credentials are loaded from the normal private Kestrel configuration, and benchmark state is isolated in a temporary directory.

Additional checks: nine offline tests passed in 1.15 seconds; compilation and Git whitespace checks passed. A PTY smoke check rendered the welcome screen, accepted `/help`, and exited cleanly using isolated writable storage. A first attempt with the default data directory hit this testing environment's filesystem restriction; it was not treated as a product startup failure.
