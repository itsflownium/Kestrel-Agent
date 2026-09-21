---
name: debug-root-cause
description: Diagnose reproducible failures in software or terminal commands and verify a targeted repair.
metadata:
  category: coding
---

# Debug Root Cause

Capture the exact failure, command, working directory, and relevant environment versions without exposing credentials. Reproduce in the smallest practical fixture. Separate a failure to run the test from a failure in the application.

Form competing explanations from observed evidence. Choose a discriminating inspection or test before changing code. Trace the failing value through the actual call path; do not add retries or suppress exceptions without identifying the mechanism.

Apply the smallest coherent repair that preserves intended behavior. Check the original trigger and a nearby boundary case. Record whether the reproduction now passes and whether unrelated checks failed. When the effect of a previous operation is uncertain, inspect its state before retrying.
