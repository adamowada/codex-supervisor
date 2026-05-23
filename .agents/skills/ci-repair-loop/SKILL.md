---
name: ci-repair-loop
description: Diagnose and repair failing checks from logs in a bounded loop. Use when CI, tests, lint, typecheck, or build output needs to be summarized, fixed, and re-run.
---

# CI Repair Loop

1. Read the failing command and the smallest useful log excerpt.
2. Classify the failure: test, typecheck, lint, build, environment, flaky, or infrastructure.
3. Identify the smallest likely fix.
4. Apply the fix.
5. Re-run the failing command first.
6. Re-run the broader gate only after the narrow failure is resolved.
7. Record residual risk and follow-up tasks.
