# PLANS.md

`PLANS.md` defines the planning database for `codex-supervisor`.

## Design Goal

The planning database answers five questions:

1. What are we trying to do?
2. What task intent is next?
3. What attempts have run?
4. What evidence exists?
5. What decisions shape the plan?

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

### `decisions`

Durable product or architecture decisions.

- `decision_id`: primary key.
- `plan_id`: optional parent plan.
- `decision`: required text.
- `rationale`: required text.
- `created_at`: required timestamp.

## Extension Rule

Add a table when repeated queries need it. Until then, store task acceptance, evidence details, and
attempt metadata in structured JSON fields attached to the core tables.
