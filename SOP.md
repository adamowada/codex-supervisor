# Standard Operating Procedure

## Start

1. Check `git status --short`.
2. Inspect the planning database with `scripts/check_planning_integrity.py`.
3. Read `HANDOFF.md`.
4. Work from the highest-priority active task, unless the user gives a direct task.

## Work

1. State the task intent.
2. Choose an assurance level.
3. Record the task with `task-create` when it is new.
4. Run one attempt with `attempt-transition` or `attempt-run`.
5. Capture evidence.
6. Accept, block, or leave ready.

## Source Docs

Keep source-of-truth docs concise and present-tense. Update hashes after intentional protected-doc
changes.

## Skills

Use repo-local skills as brief operating guidance.

## CI

CI guards the active contract.

## Handoff

`HANDOFF.md` stays compact, current, and action-oriented.
