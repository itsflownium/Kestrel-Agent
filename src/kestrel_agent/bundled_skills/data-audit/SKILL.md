---
name: data-audit
description: Validate and analyze CSV or JSON tables, check data quality, and produce reproducible aggregates.
metadata:
  category: data
---

Inspect actual columns, types, row counts, units and missing-value representations. Apply the user's inclusion/exclusion rules explicitly; do not silently turn invalid numbers into zero. Prefer query_table for supported aggregates, keeping decimal precision and numeric JSON types. Report excluded counts when relevant. For unsupported joins or transforms, use an authorized command and verify row conservation, grouping keys and a sample of independently computed values. Preserve input files unless the user requested changes. When exporting an artifact, reread it and check its schema and representative values. Explain ambiguous definitions before choosing a consequential interpretation.
