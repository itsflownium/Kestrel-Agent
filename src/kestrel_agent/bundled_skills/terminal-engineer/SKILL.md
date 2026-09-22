---
name: terminal-engineer
description: Implement or repair software and command-line workflows with focused exploration, scoped edits, and evidence of outcomes. Use for coding, debugging, repository maintenance, and terminal automation.
metadata:
  category: coding
---

# Terminal engineering

Inspect applicable project instructions and the current repository state before editing. Identify the concrete user-visible behavior to change. Preserve unrelated edits and use the project's existing conventions.

Read the smallest relevant source and configuration set, then form a specific hypothesis. Use commands as argv arrays with an explicit working directory. In Docker, use container paths inside commands and host paths for file tools. Never assume a dependency, executable, account, or environment exists.

Make a coherent change. Use source hashes when overwriting existing files. Keep effects sequential and parallelize only independent reads. After a failed command, inspect the error and prepare a minimal repair. Do not repeat a command whose external effect is uncertain.

Validate the changed behavior with focused checks when the user authorizes testing. If the user postpones testing, do not run it: clearly record untested changes and the deferred checks. Do not invent a successful test, benchmark, build, or deployment.

Inspect the final diff for accidental edits and unsupported assumptions. Report the behavior changed, evidence collected, and remaining uncertainty. Never optimize for a benchmark's known answer or claim superiority from one workload.
