# Live browser-agent smoke evaluation

2026-09-22. Real Astra medium generation, actual Jev or same-model decisions, headless Chromium, and the real direct MCP connection. The fixture is an isolated localhost form with a newly generated record name. A server-side submission ledger is independent of the agent's answer and verdicts.

| Mode | Outcome | Wall time | Generation calls | Decision calls | Jev calls |
|---|---|---:|---:|---:|---:|
| Kestrel Jev | Pass | 47.647 s | 3 | 10 | 10 |
| Kestrel standard | Pass | 70.033 s | 3 | 4 | 0 |

A pass requires task completion, exactly one submission with the requested value, no workspace file changes, a successful browser observation containing the saved confirmation, and the requested record name in the answer. Both runs passed all these checks. No external site or personal account was used. Standard mode used seven provider calls in total; Jev mode used three provider generation calls plus ten Jev decisions. This is not a direct-Codex baseline and not a priced cost comparison.

The initial Jev run passed a weaker submission/scope check in 49.771 seconds. Its report is retained as `results-browser-agent-jev-initial.json`; it did not retain the observations required by the stronger grader and is not counted in the table above. The two revision-2 reports retain observations, events, usage, and independent oracle data. After these runs, the equivalent grader was extracted into a function and tested with missing effects, duplicate submissions, incorrect values, missing browser evidence, model-generated claims, and unexpected files. Raw harness fingerprints refer to the source at each run; later grader extraction changes the current file hash.

This demonstrates a genuine browser task through the agent, beyond tool integration tests. One run per mode cannot establish a robust performance difference, broad browser competence, desktop capability, or superiority over Codex/Hermes/Claude Code. A fair direct-Codex comparison needs the same available browser tools and permissions. Provider prices were not supplied, and Codex subscription usage is not converted into invented API dollars.

Reproduce explicitly (contacts the configured model and, in Jev mode, Jev):

```sh
python benchmarks/browser_agent.py --mode jev --output benchmarks/my-browser-jev.json
python benchmarks/browser_agent.py --mode standard --output benchmarks/my-browser-standard.json
```

Install the browser extra and its matching Chromium runtime first. The development runs set `PLAYWRIGHT_BROWSERS_PATH=/tmp/kestrel-browser-runtime`. The harness gives the agent only the fixture's actual MCP catalog, disables shell tools, and declines unrelated connected actions. These controls are part of the evaluation scope.
