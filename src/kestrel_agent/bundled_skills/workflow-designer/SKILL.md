---
name: workflow-designer
description: Design reusable parameterized workflows with typed inputs, dependencies, and observable completion conditions.
metadata:
  category: workflows
---

# Workflow Designer

Identify which inputs vary between runs, which outputs the user needs, and which operations change external state. Inspect available tools and existing workflow templates before choosing a format. Never fabricate tool names or schemas.

Use Kestrel version-1 JSON templates for replayable plans when appropriate: consult the repository workflow template schema or an installed example before writing. Keep input validation and parameter substitution distinct from instructions. Express dependencies explicitly and give each material output a check against an actual artifact or external state.

Keep independent reads parallelizable and order dependent mutations. Define recovery for partially completed operations: detect prior completion before repeating external writes. Preview the expanded plan with representative inputs before executing. A syntactically valid template is not evidence of successful behavior; report each validation level separately.
