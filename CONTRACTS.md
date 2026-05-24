# Contracts

This document defines durable contracts for the supervisor. Implementation should preserve these
contracts unless an approved plan changes them.

## Task Contract

A supervisor task is a vertical slice.

Required fields:

- `task_id`
- `plan_id`
- `title`
- `goal`
- `task_type`: `AFK` or `HITL`
- `status`: `pending`, `ready`, `running`, `blocked`, `reviewing`, `completed`, `failed`, or `cancelled`
- `scope_json`
- `out_of_scope_json`
- `acceptance_criteria_json`
- `verification_commands_json`
- `allowed_paths_json`
- `blocked_by_json`
- `worker_backend`
- `review_required`

AFK tasks must be implementable by a worker without new human input. HITL tasks require a human
decision, design review, credential, or product judgment.

## Goal Contract

A Goal Contract is an execution contract for one thread or worker, derived from a supervisor task.
It does not replace the task row.

Required fields:

- `objective`
- `context_to_read_first`
- `in_scope`
- `out_of_scope`
- `verification_surface`
- `stop_condition`
- `blocked_condition`
- `iteration_policy`
- `budget_or_status_limits`
- `record_updates`

Native Codex Goals can carry this contract into a Codex thread when available. Goal lifecycle state
is reconciled back into planning SQLite as observation, not authority.

## Story Loop Contract

A story loop executes one vertical slice per iteration.

Required loop rules:

- select the highest-priority ready `AFK` task with no blocked dependencies;
- execute exactly one story before broadening scope;
- verify with the task's commands or artifacts;
- run review when required;
- record progress, artifacts, learnings, and follow-up tasks;
- stop when no ready tasks remain, a task is HITL, sources conflict, verification is inconclusive,
  or policy requires human authorization.

Ralph's `prd.json` maps to planning SQLite tasks. Ralph's `passes: true` maps to verified task
completion. Ralph's `progress.txt` maps to plan progress events plus `insights/` updates.

## Worker Result Contract

Every worker must emit a structured result.

Required fields:

- `status`: `completed`, `blocked`, `failed`, or `needs_review`
- `summary`
- `changed_files`
- `tests_run`
- `acceptance_results`
- `risks`
- `follow_up_tasks`
- `artifacts`
- `handoff_notes`

Codex workers should use `codex exec --json --output-schema` once the backend is implemented.

## Codex Local State Import Contract

Local Codex state imports are observations, not authority.

Required fields for any imported observation:

- `source_kind`: `thread`, `thread_spawn_edge`, `thread_goal`, `agent_job`, `automation`,
  `automation_run`, `inbox_item`, or `log_summary`
- `source_database`
- `source_table`
- `source_id`
- `observed_at`
- `confidence`
- `summary`
- `linked_plan_id`
- `linked_task_id`
- `raw_snapshot_path` or `raw_snapshot_hash`

Importers may propose plans, tasks, worker runs, artifact links, or progress events. They must not
silently overwrite canonical planning rows. Conflicts between local Codex observations and planning
SQLite must be surfaced as reconciliation findings.

## Review Contract

Automated review is separate from deterministic checks.

Reviewers inspect:

- diff;
- task contract;
- source-of-truth docs;
- tests/check logs;
- worker result;
- generated artifacts.

Reviewers must prioritize bugs, regressions, missing tests, contract drift, source-of-truth drift,
security/safety risk, and unclear handoff state.

## Project Spawn Contract

Any project spawned by the supervisor should begin with:

- `README.md`
- `AGENTS.md`
- `PLANS.md`
- `ARCHITECTURE.md`
- `CONTRACTS.md`
- `TESTING.md`
- `DECISIONS.md`
- `SOP.md`
- `plans/planning.sqlite3`
- `scripts/check_protected_files.py`
- `insights/README.md`
- project-relevant `.agents/skills/`

This is the default SOP unless the user explicitly asks for a smaller project.
