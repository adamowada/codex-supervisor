---
name: planning-sqlite-operator
description: Operate codex-supervisor planning SQLite safely through typed helpers. Use when creating, updating, inspecting, or verifying plans, milestones, decisions, progress events, tasks, or worker-run records.
---

# Planning SQLite Operator

Use `plans/planning.sqlite3` for operational planning state.

## Rules

- Use `codex_supervisor.planning` helpers and `codex-supervisor` CLI commands first.
- Use read-only CLI commands for orientation; do not initialize or migrate the database just to
  answer status questions.
- In strict read-only, readonly, review-only, audit-only, no-edits, no-mutation, or unsynced
  environments, run `uv run` commands only when dependencies are already present. Otherwise use
  existing command output, Git state, or read-only SQLite inspection and report that typed CLI
  orientation needs dependency setup.
- Do not write ad hoc SQL for mutations. If read-only SQL is the only available way to answer a
  planning question, open the database with `mode=ro`, state that the helper surface is missing, and
  propose the smallest typed helper. Add that helper only when the current turn permits edits.
- `task-upsert` and `worker-run-upsert` preserve omitted optional contract/evidence fields on
  existing rows. Use `--replace` only when intentionally resetting omitted fields.
- Keep open AFK tasks on active or blocked plans execution-ready even while blocked: nonempty
  acceptance criteria, cache-safe verification commands, and repo-relative allowed paths.
- Record decisions before or during meaningful tradeoffs.
- Record progress when work starts, completes, blocks, unblocks, verifies, or hands off.
- Store Goal Contract and Story Loop metadata in task `scope_json`, `acceptance_criteria_json`,
  `verification_commands_json`, and worker-run `metadata_json` until the schema gains dedicated
  tables.
- Completed worker runs must use `result_path` for an existing repo-local JSON artifact satisfying
  `../worker-result-contract.md`. Link the exact JSON result path through `plan_artifact_links` with
  relationship `worker-result`; link markdown reports separately as supporting artifacts.
- Keep markdown source-of-truth docs human-facing; do not hide stable doctrine only in SQLite.

## Current Task Rule

When the user says "check `plans/planning.sqlite3`" or asks what the current task is, treat that as
queue-state discovery, not as permission to dump historical tables. Start with typed helpers and only
inspect all history after the live queue is clear.

When asked "what is the current task?", use `story-loop-status` as the queue state machine and
`task-current` as the executable AFK selector.

Never answer the current-task question from `task-current` alone. `task-current` intentionally cannot
select HITL checkpoints, running work, or blocked queues.

- `ready`: report the highest-priority unblocked ready `AFK` task on an active plan.
- `running`: report the claimed task and worker-run state; do not start a second worker unless the
  active plan explicitly permits parallel writers.
- `hitl`: report the current HITL checkpoint as the next human action; do not call it drift.
- `blocked`: report blockers and the task IDs that need resolution.
- `completed` or `empty`: report that no executable AFK task remains.

By default, `story-loop-status` covers active and blocked current-queue plans. Use `--all` only when
you need completed, abandoned, or superseded historical plans.

Fresh-thread recipe:

1. Run `uv run codex-supervisor story-loop-status --json`.
2. Read top-level `queue_state`; do not infer queue state from `current_task` alone.
3. If `queue_state` is `hitl`, read `current_task_id` from that output and run
   `uv run codex-supervisor task-show <current_task_id> --json`.
4. If `queue_state` is `ready`, run `uv run codex-supervisor task-current --json`, report the
   selected AFK task, and route execution to `story-loop-runner`.
5. Use `uv run codex-supervisor task-list --current-queue-plans-only --json` for current-queue task
   audits that include active and blocked plans.
6. Use `uv run codex-supervisor plan-summary --current-queue --json` for current-queue milestones,
   criteria, decisions, progress, artifact links, or worker runs. Use active-only flags only for a
   deliberately narrow active-plan audit, and use `story-loop-status --all` or `plan-list` when
   historical rows are in scope.
7. Do not inspect all historical `supervisor_tasks` as a current queue unless debugging drift.

If fallback read-only SQL sees `ready` tasks on completed, abandoned, superseded, or otherwise
historical plans, classify those rows as historical or drift evidence. A blocked plan is still a
current-queue plan, but its ready AFK tasks are not executable until the plan or task blocker is
resolved. Do not report historical rows as "the current task" or "the next task" unless the user
explicitly asks for historical backlog rows or reopens the plan.

If the user asks for all rows after queue-state discovery, separate the answer into `Current Queue`
and `Historical Rows`. Never phrase historical ready tasks as "one other ready task" without naming
their terminal or non-current plan status. That wording caused fresh-thread confusion in this repo.

`task-current --json` returning `null` means "no executable AFK task was selected." It does not mean
"nothing is happening" until `story-loop-status` also reports `completed` or `empty`.

Strict read-only fallback SQL:

```sh
python -B -c "import json, sqlite3; c=sqlite3.connect('file:plans/planning.sqlite3?mode=ro', uri=True); c.row_factory=sqlite3.Row; rows=c.execute(\"\"\"SELECT p.plan_id,p.status AS plan_status,p.priority,st.task_id,st.title,st.status AS task_status,st.task_type,st.worker_backend,st.blocked_by_json FROM supervisor_tasks st JOIN plans p ON p.plan_id=st.plan_id WHERE p.status IN ('active','blocked') ORDER BY p.status='active' DESC,p.priority DESC,st.status='ready' DESC,st.updated_at DESC,st.task_id\"\"\").fetchall(); print(json.dumps([dict(r) for r in rows], indent=2)); c.close()"
```

Treat drift as a mismatch between durable sources or invalid queue shape, such as handoff prose
claiming a task the database does not expose, a ready AFK task attached to a terminal or historical
plan, pending criteria without an open task, or raw read-only SQL revealing rows that typed helpers
cannot surface.

## Queue Authority Rule

Treat `plans/planning.sqlite3` as canonical for active and blocked current-queue plans, current
tasks, task status, worker runs, and handoff order. Treat `HANDOFF.md` as a mutable convenience
snapshot that can drift. If a fresh thread sees a conflict between handoff prose and the database,
report the conflict and follow the database for execution order. Update `HANDOFF.md` once the live
queue has been inspected when writes are allowed; in read-only mode, propose the handoff update
instead. Update locked source-of-truth documents only when a stable planning contract changes.

## Commands

Read/orient:

```sh
uv run codex-supervisor story-loop-status
uv run codex-supervisor story-loop-status --json
uv run codex-supervisor task-current --json
uv run codex-supervisor task-show <task-id> --json
uv run codex-supervisor task-list --current-queue-plans-only --json
uv run codex-supervisor plan-summary --current-queue
uv run codex-supervisor plan-list
uv run codex-supervisor worker-run-list --json
uv run codex-supervisor worker-run-show <worker-run-id> --json
uv run codex-supervisor goal-contract-render --task-id <task-id>
```

Initialize/write:

Use these only when the turn allows repository writes. In read-only, review-only, audit, or "don't
edit yet" mode, report the exact command you would run instead of mutating `plans/planning.sqlite3`.

```sh
uv run codex-supervisor plan-init --seed-bootstrap-plan
uv run codex-supervisor plan-upsert ...
uv run codex-supervisor milestone-upsert ...
uv run codex-supervisor criterion-upsert ...
uv run codex-supervisor decision-add ...
uv run codex-supervisor progress-add ...
uv run codex-supervisor artifact-link-add ...
uv run codex-supervisor commit-link-add ...
uv run codex-supervisor task-upsert ...
uv run codex-supervisor task-claim --worker-run-id <worker-run-id> ...
uv run codex-supervisor worker-run-upsert ...
uv run codex-supervisor plan-status ...
uv run codex-supervisor milestone-status ...
uv run codex-supervisor criterion-status ...
uv run codex-supervisor task-status ...
uv run codex-supervisor worker-run-status ... --result-path <path>
uv run codex-supervisor story-loop-record ...
```

Use `story-loop-record` for one-story progress when artifact links belong to the same iteration; it
records the progress event and artifact links together.

## Result Contract

Report plan IDs, task IDs, rows changed or inspected, commands run, evidence, residual risks, and
the next AFK/HITL action. If using read-only SQL because a helper is missing, name the missing helper
and propose the smallest typed helper that would remove the SQL fallback.
