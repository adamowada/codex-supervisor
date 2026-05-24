---
name: ci-repair-loop
description: Summarize CI/check failures and route repair through failure-loop-triage. Use when CI, tests, lint, typecheck, or build output needs a concise diagnosis before a bounded repair loop.
---

# CI Repair Loop

If the current user turn is read-only, review-only, audit-only, no-edits, or no-mutation, do not
edit files, rerun jobs, push commits, update trackers/databases, or start repair. Return the failure
summary, likely class, and proposed bounded repair loop only.

1. Identify whether the failure source is local output, GitHub check metadata, workflow job logs, or
   another CI provider.
2. For GitHub PR/check state, route remote inspection through `git-pr-ci-operator`; for local test,
   lint, typecheck, or build output, inspect the smallest useful log excerpt directly.
3. Summarize the failing command or job, first bad frame, affected owner area, and whether the
   failure is likely infrastructure, dependency, flaky test, product regression, type/lint drift, or
   missing fixture/setup.
4. Route actual repair to `failure-loop-triage`; use its richer failure classes and result contract.
5. Re-run the failing command or job first after repair.
6. Re-run the broader gate only after the narrow failure is resolved.
7. Record residual risk, commands/logs inspected, follow-up tasks, and whether any reruns were
   requested.
