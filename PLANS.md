# PLANS.md

`PLANS.md` defines the fresh planning database. The old database shape was deleted because it encoded
the complexity we are removing.

## Design Goal

The planning database should answer five questions:

1. What are we trying to do?
2. What is the next task intent?
3. What attempts have run?
4. What evidence exists?
5. What decisions changed the plan?

It should not be a general-purpose audit warehouse, plugin ledger, release ledger, review ledger,
or compatibility store.

## Fresh Schema

### `meta`

Key-value repository planning metadata.

- `key text primary key`
- `value text not null`

Required keys:

- `schema_name`
- `schema_version`
- `reset_at`
- `reset_reason`

### `plans`

One active objective or coherent project phase.

- `plan_id text primary key`
- `title text not null`
- `status text not null`
- `priority integer not null`
- `goal text not null`
- `created_at text not null`
- `updated_at text not null`

Allowed statuses:

- `active`
- `blocked`
- `done`
- `dropped`

### `tasks`

One intent that can be attempted.

- `task_id text primary key`
- `plan_id text not null references plans(plan_id)`
- `title text not null`
- `status text not null`
- `assurance text not null`
- `intent text not null`
- `acceptance_json text not null`
- `created_at text not null`
- `updated_at text not null`

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

- `attempt_id text primary key`
- `task_id text not null references tasks(task_id)`
- `executor text not null`
- `status text not null`
- `summary text not null`
- `started_at text`
- `finished_at text`

Allowed statuses:

- `planned`
- `running`
- `succeeded`
- `failed`
- `blocked`

### `evidence_bundles`

Structured evidence produced by an attempt or accepted manually for a task.

- `bundle_id text primary key`
- `task_id text not null references tasks(task_id)`
- `attempt_id text references attempts(attempt_id)`
- `assurance text not null`
- `summary text not null`
- `checks_json text not null`
- `artifacts_json text not null`
- `created_at text not null`

### `decisions`

Durable product or architecture decisions.

- `decision_id text primary key`
- `plan_id text references plans(plan_id)`
- `decision text not null`
- `rationale text not null`
- `created_at text not null`

## Deleted Concepts

The fresh schema intentionally does not include:

- separate AFK/HITL task types;
- worker backend as a task identity field;
- review-specific database tables;
- historical progress event vocabularies;
- artifact-link relationship taxonomies;
- imported Codex local-state reconciliation rows;
- plugin install ledgers;
- release-readiness ledgers;
- compatibility aliases.

If one of those concepts returns, it must be expressed as task intent, attempt execution, evidence,
or acceptance policy first.
