# Optional Jev mode

New installations use standard mode; existing mode-less configurations preserve Jev mode. Standard mode uses the selected provider for planning and bounded decisions, without constructing a Jev client or requesting a Jev key. Decisions use separate bounded call accounting; input/output/cache telemetry is attributed without double-counting concurrent calls. Invalid or missing model choices fail closed. All modes retain controller permissions and deterministic completion checks.

Standard mode executes unconditional model-planned actions without a second inference gate. Runtime conditions still receive decisions. This does not bypass tool validation or permissions. Jev mode retains its existing per-action relevance checks.

One live development fixture (`exact_artifact`, GPT-6 Astra medium) passed independent artifact and scope checks in both arms. Initial standard mode took 103.579 seconds versus Codex 15.624 seconds, with 3 generation calls and 7 model-decision calls. After removing redundant unconditional gates, a fresh trial took 62.167 seconds versus Codex 12.554 seconds, with 3 generation calls and 3 model-decision calls. Both standard runs made **zero Jev calls**. Both needed an additional workspace-inspection plan to support the no-other-files requirement.

Raw evidence: `results-standard-mode-initial.json` and `results-standard-mode.json`. These single development trials are not a matched repeated ablation or proof of general performance. Standard mode remains slower on this case; this change establishes a working single-provider decision path, not superiority.

Final full suite: **253 passed in 36.01 seconds**.
