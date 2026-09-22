# Evaluated skill-workflow exports — 2026-09-22

Skills can declare named version-1 JSON workflow exports. A caller explicitly tests an export against a suite, receives a controller-recorded evaluation ID, and may install that workflow only if positive and negative cases passed and the complete skill package still matches the evaluated version. The installed artifact is copied from a frozen snapshot of the exact evaluated template. Skill prose/scripts and other exports are not executed or certified. Installation does not run the workflow.

`skill_workflow_export.py` exercises the bundled workflow-designer copy-text export in private temporary storage, with four seeded positive cases containing different filenames, Unicode, tabs and CRLF endings, plus missing-input and existing-output negative cases. The real isolated file runner passed all six cases. The exported template exactly matched the evaluated template, and no caller task workspace was created. Model calls were disabled; no credentials or external services were used. The script and report preserve package/template/suite hashes and the fixture seed.

This is scoped file-workflow evidence, not independent skill certification, unseen-task performance, or evidence of superiority over another agent. The fixture author controls the expected outputs. Independent authorship, applicability across task families, external-tool workflows and automatic promotion remain unverified.

Focused tests also cover mismatched or missing evaluation IDs, changed instructions/templates/references, symlinked package content, failed and positive-only suites, explicit replacement, invalid export paths, disallowed executable tools, CLI reporting and export, and network-disabled capability declarations. Recovery fixtures now use the scheduler's actual skip status; positive cases may skip unused branches, while a skipped branch alone does not count as a negative case. Suite reads reject symlinks, FIFOs and oversized inputs before launching a worker.

## Validation

The full regression suite passed **528 tests in 455.96 seconds**. The focused skill/library suite passed 34 tests; the workflow fixture suite passed 14 tests before adding three passing regular-file boundary checks. The six-case bundled-export smoke passed with zero model calls. Source and wheel builds passed, and archive inspection confirms the evaluation module, export metadata and parameterized template are included. `git diff --check` passed.
