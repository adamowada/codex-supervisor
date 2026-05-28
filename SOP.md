# Standard Operating Procedure

## Start

1. Check `git status --short`.
2. Inspect the fresh planning database with `scripts/check_planning_integrity.py`.
3. Read `HANDOFF.md`.
4. Work from the highest-priority active task unless the user overrides it.

## Work

1. State the task intent.
2. Choose an assurance level.
3. Run one attempt.
4. Capture evidence.
5. Accept, block, or leave ready.

## Source Docs

Rewrite source-of-truth docs when they are wrong. Do not build compatibility machinery to protect
stale doctrine.

## Skills

Use repo-local skills as brief operating guidance only. Do not recreate a skill router, skill mesh,
or nested workflow hierarchy.

## CI

CI should guard the current simplified contract. It should not run historical tests just because
they exist.

## Handoff

`HANDOFF.md` must stay compact and current. It is not a changelog.
