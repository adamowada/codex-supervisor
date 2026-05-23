---
name: failure-loop-triage
description: Classify a failed command, CI job, test, lint, typecheck, build, shell, git, network, or tool run and choose the next bounded repair step. Use after any failed verification or repeated failed command loop.
---

# Failure Loop Triage

Read the smallest useful failure excerpt and classify before fixing.

## Failure Classes

- missing path or wrong cwd;
- shell quoting or PowerShell parse;
- syntax or import;
- test assertion;
- lint or format;
- typecheck;
- build or bundler;
- environment or missing tool;
- sandbox or permission;
- network or remote;
- flaky or timeout.

## Loop

1. State the class and evidence.
2. Pick the smallest likely fix.
3. Re-run the exact failing command.
4. Broaden only after the narrow command passes.
5. After three related failures, write a handoff with attempts, evidence, and next hypothesis.
