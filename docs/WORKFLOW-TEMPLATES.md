# Typed workflow templates

Templates are explicit reusable plans, separate from learned Markdown recipes. They use JSON Schema to validate parameters, typed parameter substitution, the regular tool argument contracts, and the existing dependency scheduler. They do not bypass permissions, completion checks, recovery, or model/Jev review.

Learned Markdown recipes have a separate provenance record and remain unverified even after manual activation. A source session must be completed with no failed/pending exact checks or unresolved actions before it can propose a recipe. Source hashes and recorded check outcomes support inspection, not a claim that new parameters or tasks will work. Independent behavioral certification and automatic promotion are still pending.

```sh
kestrel workflows install examples/workflows/read-document.json
kestrel workflows templates
kestrel workflows preview read-document '{"path":"notes.md"}'
```

In chat: `/workflow preview read-document {"path":"notes.md"}` or `/workflow run read-document {"path":"notes.md"}`. Run shows the compiled plan and asks for confirmation before executing it. Individual tool permissions still apply. The template hash is recorded with the session. No automatic replay or behavioral certification is implied by installation.

A version-1 template contains `name`, `description`, `parameters`, `actions`, `success_criteria`, optional `completion_checks`, and optional `final_response_ref`. Parameters must use an object JSON Schema with `additionalProperties: false`. External schema references are rejected. In action `arguments`, an object exactly equal to `{"$param":"name"}` is replaced with that typed parameter. No string interpolation, shell evaluation, or generated code is used for substitution. Tools and dependencies are fixed by the template. Standard `${action.field}` references continue to bind prior tool results.

Completion checks accept a typed `expected` value, converted to the existing `expected_json` contract, and may bind a parameter as their source path. The compiled plan is validated before any action runs. Runtime repair can still replan under the original task and retained completion contracts; this is an agent workflow, not a guarantee of executing only a fixed script.

The `copy-text.json` example copies complete small UTF-8 text to a new destination without generating replacement content. It preserves whitespace and refuses to overwrite existing destinations without an observed hash. Install it like the read-document example, then pass `source` and `destination` parameters. Its limit is the file reader's complete-text limit (40,000 characters and 1,000 lines); extracted PDF/DOCX/XLSX text is not supported by this copy template.

Behavioral regression tests execute this compiled template through the real scheduler, permission checks, file tools and SQLite checkpoints. They compare saved bytes for empty, Unicode and whitespace-sensitive inputs, and verify missing sources, existing destinations, read-only access, rejected approval, paths outside the workspace and truncated input. They stop before model repair or final-answer generation, so repair cannot hide a failing original template. This is narrow template coverage, not certification of arbitrary templates, semantic summaries or automatic promotion.

## Run your own behavioral fixtures

```sh
kestrel workflows test examples/workflows/copy-text.json examples/workflows/copy-text.tests.json
```

The command runs the template in a separate process, with temporary task directories and separate temporary Kestrel storage. It does not modify your installed workflow, session database or selected model. Provider credentials are not passed in the child environment. The worker uses the actual scheduler and file-tool permissions; it does not call a model or repair the template. This is application-level isolation for the supported file tools, not a Docker or operating-system sandbox.

A version-1 suite contains 1–24 named cases. Each case supplies `kind` (`positive` or `negative`), typed `parameters`, initial UTF-8 `files`, the complete `expected_files` tree, and `expected_statuses` for every action. An `error` status also requires a nonempty `expected_errors` substring for that action. Extra files, changed source files, wrong statuses and unrelated errors fail the case. Positive cases must complete every action and pass the template's completion checks. Unexpected runner exceptions cannot pass a negative case.

The current runner supports unconditional `read_file`, `write_file`, `list_files` and `search_files` actions only. It rejects shell, model, network, connector and conditional actions before launching the worker. Suite size, case count and fixture file sizes are bounded; paths cannot escape their temporary workspace. Each case has a 20-second execution timeout, and the parent also bounds the worker's total lifetime. Exit code 0 means all specified expectations passed; 1 means at least one failed. Invalid input produces a command error.

Reports include exact template/suite hashes and positive/negative case counts. They deliberately say `not_certified`: the caller authors the expectations, and the runner cannot prove independent authorship, held-out inputs, semantic quality, skill applicability or broad generalization. Use varied inputs and negative cases, review the oracles independently, and retain both passing and failing reports. Reports do not activate or promote workflows. Behavioral skill certification, external-tool fixtures and promotion remain separate pending work.
