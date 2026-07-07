# Standard Operating Procedure

## Start

1. Check `git status --short`.
2. Inspect the planning database with `scripts/check_planning_integrity.py`.
3. Read `HANDOFF.md`.
4. Read `SUBSTRATE_PLAN.md` when working on `feature/substrate`.
5. Work from the highest-priority active task, unless the user gives a direct task.

## Work

1. State the Goal Mode work unit as task intent.
2. Choose an assurance level.
3. Record the task with `task-create` when it is new.
4. Write or identify the launch packet and verifier intent when the work will run through a worker.
5. Use `attempt-transition` only for supervisor/admin state or evidence that does not mutate product
   files. Use `attempt-run` for product-file mutation.
6. Capture launch metadata, evidence, artifacts, risks, gaps, next actions, and acceptance.
7. Let Goal Mode decide whether to advance, retry, repair, review, ship, or stop.

## Source Docs

Keep source-of-truth docs concise and present-tense. Update hashes after intentional protected-doc
changes.

## Skills

Use repo-local and packaged skills as brief operating guidance. They should teach that Goal Mode
owns judgment and Supervisor owns durable proof.

## CI

CI guards the active substrate contract.

## Handoff

`HANDOFF.md` stays compact, current, and action-oriented. Any current-state handoff edit must move
with `plans/planning.sqlite3`.
