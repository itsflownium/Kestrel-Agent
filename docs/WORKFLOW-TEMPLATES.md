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
