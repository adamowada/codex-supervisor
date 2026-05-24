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

## Agent Taxonomy

- `supervisor`: the coordinator that reads source of truth, selects work, routes skills, and records
  durable state.
- `worker`: a fresh-context implementation run responsible for one task contract.
- `explorer`: a read-only investigation lane that returns findings but does not mutate state.
- `reviewer`: a fresh-context review lane focused on bugs, regressions, contract drift, and risk.
- `handoff`: a compact artifact that lets a new thread resume without depending on chat memory.

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

- select the highest-priority executable `AFK` task on an active plan with no unresolved blockers
  and with nonempty acceptance criteria, verification commands, and safe repo-relative allowed
  paths;
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

- `worker_run_id` for a single-run result, or `worker_run_ids` for an intentionally shared
  synthesized result whose entries are completed worker runs with the same `result_path`
- `status`: `completed`, `blocked`, `failed`, or `needs_review`
- `summary`
- `changed_files`
- `tests_run`: objects with `command`, `exit_code`, and a short result summary
- `acceptance_results`: exact task acceptance criteria mapped to passing evidence
- `risks`
- `follow_up_tasks`
- `artifacts`
- `handoff_notes`

Codex workers should use `codex exec --json --output-schema` once the backend is implemented.
Completed worker-run rows must link `result_path` to an existing repo-local JSON artifact with the
`worker-result` relationship in `plan_artifact_links`. Local
integrity checks validate this required field set, field types, status vocabulary, artifact
existence, worker-run identity coverage, shared `worker_run_ids` membership against completed runs
with the same `result_path`, task verification coverage with zero exit codes, exact
acceptance-criterion coverage, implementation changed-file alignment with `allowed_paths_json`, and
the `plan_artifact_links` relationship.
Publication-ready durable evidence should live in tracked repo-local paths such as `insights/`;
ignored paths such as `artifacts/`, `runs/`, `worktrees/`, and `logs/` are ephemeral run output and
cannot satisfy the publication gate.

When `status` is `completed`, these evidence fields must be nonempty: `summary`, `changed_files`,
`tests_run`, `acceptance_results`, `artifacts`, and `handoff_notes`. A completed worker result that
only says "done" without changed files, verification evidence, artifacts, and acceptance mapping is
not durable enough to advance the Story Loop.

The `artifacts` list must include the JSON result file itself, exactly matching the worker-run
`result_path`. `changed_files` should list implementation or durable-documentation paths changed by
the worker, not evidence files that merely prove the run. Supporting reports, logs, and markdown
summaries can appear alongside the JSON result in `artifacts`, but they do not replace the result
artifact.

Each `tests_run` entry needs a nonblank summary that reports durable evidence without stale
phrasing such as "passed at the time." If a command no longer passes in the current bootstrap
checkpoint, do not preserve it as passing evidence; replace it with a current passing verifier or
record the residual risk separately.

Example `tests_run` entry:

```json
{"command":"uv run --no-sync python -B -m pytest -q -p no:cacheprovider","exit_code":0,"summary":"passed"}
```

Example `acceptance_results` entry:

```json
{
  "Default verification passes before handoff.": {
    "status": "passed",
    "evidence": "Cache-safe default verification and publication-ready verification passed after ACP."
  }
}
```

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

Any production-intended project spawned by the supervisor should begin with the base scaffold, then
grow by tier as the project earns the extra surface area.

### Base Tier

- `README.md`
- `AGENTS.md`
- `PLANS.md`
- `ARCHITECTURE.md`
- `CONTRACTS.md`
- `ROADMAP.md`
- `TESTING.md`
- `DECISIONS.md`
- `SOP.md`
- `HANDOFF.md`
- `.gitignore`
- `.gitattributes`
- `scripts/verify.py`
- `insights/README.md`

### Supervisor-Managed Tier

Add when the project needs unattended worker coordination, protected source-of-truth checks, or
tracked operational queue state:

- `plans/planning.sqlite3`
- `scripts/print_protected_hashes.py`
- `scripts/check_protected_files.py`
- `scripts/check_file_justification.py`
- `scripts/check_planning_integrity.py`

### Publication-Ready Tier

Add or tighten when the repo is intended to be public or shared outside the local machine:

- `LICENSE`
- `ATTRIBUTIONS.md`
- `scripts/check_public_repo_hygiene.py`

### Skills And Source-Study Tier

Add only when the project needs repo-local skills or OSS study sources:

- `scripts/check_skill_inventory.py`
- `scripts/check_source_inventory.py`
- project-relevant `.agents/skills/`
- `sources/README.md`

This tiering is the default SOP unless the user explicitly asks for a smaller project. Do not create
empty skill, source inventory, attribution, or lock surfaces just to satisfy the supervisor pattern.
