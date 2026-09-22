# Portable skills

Kestrel discovers bundled skills, explicitly installed local packages, and trusted project skill directories. Skills use Agent Skills-style YAML frontmatter (`name`, `description`) plus Markdown instructions. Discovery supplies metadata; instructions and relative references load on demand. Thirteen bundled procedures cover coding, terminal work, research, documents, data, browser workflows, and related tasks.

```sh
kestrel skills list
kestrel skills show data-audit
kestrel skills check
kestrel skills install /absolute/path/to/my-skill
kestrel skills install /absolute/path/to/my-skill --replace
kestrel skills versions my-skill
kestrel skills rollback my-skill VERSION_HASH
kestrel skills trust /absolute/project/root
```

In chat: `/skills`, `/skills search-words`, `/skills show NAME`, `/skills use NAME your task`, or `/NAME your task`. `check` validates metadata and declared prerequisites; it is not a behavioral evaluation. Each reference load records its content hash. Install stores complete version snapshots for rollback; the catalog version identifies entrypoint/capability metadata, not a behavioral certification.

Project discovery looks for `.agents/skills` and `.kestrel/skills` at the nearest Git root (or the working directory outside a repository), and requires explicit trust. Project packages override installed packages, which override bundled packages. Built-in command names cannot be shadowed by skills. Packages cannot change tool permissions, auto-execute scripts, or grant network/account access.

A skill can include optional `kestrel.json` with `required_tools` and `required_env` identifier lists. Missing declared prerequisites block loading with an explanation; only variable names, never values, appear in diagnostics. Standard packages without this sidecar still load. `disable-model-invocation: true` is honored: these packages require an explicit user slash invocation. Other vendor-specific execution features (dynamic shell expansion, forked subagents, permission grants) are not implemented or silently executed.

Limits: names must match the lowercase hyphenated directory name; frontmatter is bounded, aliases/anchors are rejected, skill/reference bodies are bounded, and symlink packages/references are rejected. Local installation copies at most 128 non-hidden files and 2 MB. Remote hub installation and arbitrary script execution are not part of this release. Inspect imported packages before using them; static validation does not prove instructions are trustworthy or useful.

Package reads pin each directory below the package root and reject symlinks, non-regular files and oversized content. The byte limit applies to the actual read, not just an earlier file-size check. Metadata rejects duplicate YAML/JSON keys, including nested YAML keys. Entrypoint versions are calculated from the same text that was parsed.

Rollback verifies the recorded archive hash before changing the active package. Modified, added or symlinked archive content causes refusal; the current installation remains intact. Reinstalling an existing version also verifies its archive rather than silently overwriting it. Installation copies a bounded in-memory snapshot and never executes package scripts. These checks protect local package integrity; they are not a sandbox against another process that controls the configured Kestrel home or its ancestor directories, nor behavioral certification of a skill.

## Verification

Existing 253-test suite passed after integration. Seven additional skill tests cover progressive discovery, references/path escape, symlinks, missing capabilities, explicit-only policy, project trust, install/update/rollback, nonexecution of scripts, and engine invocation preserving the original task. All five bundled entrypoints pass the skill-creator validator.

A live `data-audit` invocation on CSV aggregation passed numeric and recursive file-scope grading: Kestrel 13.809 seconds (one Astra-medium generation, two Jev decisions), direct Codex 9.268 seconds. Raw evidence is in `benchmarks/results-portable-skills.json`, including the selected skill snapshot. This checks one skill integration, not general superiority or comprehensive validation of all procedures.

## Interactive library

`/skills` and `/skills browse [query]` open a searchable local library. Type to filter names, descriptions, categories, or origin; use Up/Down to select, Tab to focus the scrollable guidance preview, Enter to inspect, and Escape to return. Opening or selecting an entry never executes it. Invoke `/NAME your task` to use it.

`/skills search QUERY` prints matching entries; `/skills list` prints the catalog. `/skills inspect NAME` aliases `/skills show NAME`. Slash completion includes subcommands and installed skill names. Packages can provide `metadata.category` in SKILL.md; absent categories appear under general. The home screen groups a selection by category.

The bundled library now includes code-review, debug-root-cause, workflow-designer, web-research, document-drafting, and incident-triage alongside the original seven skills. These provide task procedures, not new tools: document rendering, external services, and desktop access still require actual available capabilities. New skill guidance has schema/discovery validation, not independent proof of improved task quality.

Design references: [OpenCode TUI](https://opencode.ai/v2/docs/cli/tui/) for command discovery and [Pi interactive mode](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/README.md#interactive-mode) for a compact editor/status layout. Kestrel keeps its own commands, styling, and permission model.
