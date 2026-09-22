---
name: incident-triage
description: Investigate service failures from logs and local diagnostics, establish impact, and propose evidence-based remediation.
metadata:
  category: operations
---

# Incident Triage

Establish the incident time window and affected behavior. Inspect available logs, recent changes, and health indicators; use bounded queries so large logs do not erase useful context. Do not print credentials or customer data unnecessarily.

Create a timeline separating observed failures from hypotheses. Compare healthy and failing cases. Prefer read-only diagnostics until a remediation is justified and authorized; restarting a service can destroy evidence and does not identify a root cause.

For an authorized repair, record the precondition, rollback route, and health condition that would demonstrate recovery. Inspect the resulting state before repeating actions. Deliver impact, supporting evidence, current status, and unresolved causes without claiming resolution from a successful command alone.
