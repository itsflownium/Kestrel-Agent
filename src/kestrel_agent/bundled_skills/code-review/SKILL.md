---
name: code-review
description: Review a code change for correctness, regressions, and missing validation, with actionable findings grounded in the diff.
metadata:
  category: coding
---

# Code Review

Read project instructions and establish the requested comparison base. Inspect the diff, surrounding callers, and relevant tests. Distinguish defects introduced by this change from pre-existing behavior.

For each suspected issue, trace a concrete trigger to the affected behavior. Use a minimal reproduction or a focused test when feasible. Report file and line, impact, trigger, and confidence. Avoid speculative findings and style preferences unless they violate project requirements.

Review authentication boundaries, data lifetime, error handling, concurrency, and compatibility only where the change touches them. Report checks actually run. If no actionable findings survive verification, say so and identify remaining coverage gaps. Reviewing does not authorize fixing, committing, or publishing the review.
