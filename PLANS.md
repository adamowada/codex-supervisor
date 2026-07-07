# PLANS.md

`PLANS.md` defines the planning database for `codex-supervisor`.

## Design Goal

The planning database answers five questions:

1. What are we trying to do?
2. What task intent is next?
3. What attempts have run?
4. What evidence exists?
5. What acceptance decisions did policy make?
6. What product or architecture decisions shape the plan?

The planning database is the durable ledger. It **MUST** be current whenever `HANDOFF.md` is current.
Work that changes the repository's current state, completion evidence, or next action **MUST** update
`plans/planning.sqlite3` and `HANDOFF.md` together.

## Schema

### `meta`

Repository planning metadata.

- `key`: primary key.
- `value`: required text.

Required keys:

- `schema_name`
- `schema_version`
- `reset_at`
- `reset_reason`

### `plans`

One active objective or coherent project phase.

- `plan_id`: primary key.
- `title`: required text.
- `status`: required status.
- `priority`: required integer.
- `goal`: required text.
- `created_at`: required timestamp.
- `updated_at`: required timestamp.

Allowed statuses:

- `active`
- `blocked`
- `done`
- `dropped`

### `tasks`

One intent that can be attempted.

- `task_id`: primary key.
- `plan_id`: parent plan.
- `title`: required text.
- `status`: required status.
- `assurance`: required assurance level.
- `intent`: required text.
- `acceptance_json`: required JSON array.
- `created_at`: required timestamp.
- `updated_at`: required timestamp.

Allowed statuses:

- `ready`
- `running`
- `blocked`
- `done`
- `dropped`

Allowed assurance values:

- `low`
- `medium`
- `high`

### `attempts`

One execution attempt against one task.

- `attempt_id`: primary key.
- `task_id`: parent task.
- `executor`: required text.
- `status`: required status.
- `summary`: required text.
- `started_at`: optional timestamp.
- `finished_at`: optional timestamp.

Allowed statuses:

- `planned`
- `running`
- `succeeded`
- `failed`
- `blocked`

### `evidence_bundles`

Structured evidence produced by an attempt or accepted manually for a task.

- `bundle_id`: primary key.
- `task_id`: parent task.
- `attempt_id`: optional attempt.
- `assurance`: required assurance level.
- `summary`: required text.
- `checks_json`: required JSON array.
- `artifacts_json`: required JSON array.
- `created_at`: required timestamp.

### `acceptance_decisions`

One policy decision for one terminal attempt.

- `decision_id`: primary key.
- `task_id`: parent task.
- `attempt_id`: terminal attempt.
- `bundle_id`: evidence bundle judged by policy.
- `actor`: required policy actor.
- `result`: required result.
- `rationale`: required text.
- `evaluation_json`: required JSON object.
- `created_at`: required timestamp.

Allowed results:

- `accepted`
- `rejected`

### `decisions`

Durable product or architecture decisions.

- `decision_id`: primary key.
- `plan_id`: optional parent plan.
- `decision`: required text.
- `rationale`: required text.
- `created_at`: required timestamp.

## Extension Rule

Add a table when repeated queries need it. Until then, store evidence details and attempt metadata
in structured JSON fields attached to the core tables. Evidence may be structured in code before it
is encoded into the existing JSON fields. Acceptance decisions are first-class rows because they are
part of the durable work model.

## Currentness Rule

`HANDOFF.md` is the readable resume snapshot. `plans/planning.sqlite3` is the durable resume ledger.
They **MUST** move together: editing `HANDOFF.md` without updating the planning database is treated as
missing durable evidence unless the edit is purely typographic and does not change current state,
completed work, next action, verification evidence, or source-of-truth status.
