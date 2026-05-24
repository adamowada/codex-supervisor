# PLANS.md

This file defines the planning system for `codex-supervisor`.

`PLANS.md` is immutable by default. Edit it only when the user specifically asks or when a clearly
approved plan changes the planning contract.

Operational execution plans, task progress, worker-run progress, and live queue state belong in
`plans/planning.sqlite3`, not in markdown files. This document may define status vocabulary as part
of the schema contract, but it must not mirror live stage or task progress.

## Planning Model

The planning database is tracked in git and acts as operational state for Codex. It answers:

- what are we trying to do;
- why are we doing it this way;
- what remains blocked or unverified;
- which tasks, worker runs, artifacts, reviews, and commits belong to the work;
- which lessons should be promoted into skills or `insights/`.

Markdown remains the source of truth for stable human-facing knowledge. Do not use planning tables
as a private replacement for `README.md`, `AGENTS.md`, contracts, architecture, SOP, or insights.
Likewise, do not use protected markdown as a private replacement for the planning database.

## Codex Local State Reconciliation

Local Codex databases under `~/.codex` are observational inputs, not the project queue. The
canonical queue remains `plans/planning.sqlite3`.

The supervisor may read local Codex state to propose updates:

- threads and spawn edges can become evidence for active, stale, or orphaned work;
- thread goals can become candidate plans or plan context;
- agent-job rows, if Codex begins using them, can map to candidate `supervisor_tasks` or
  `worker_runs`;
- automation and inbox rows can inform recurring work and follow-up triage;
- logs can reveal repeated failures, slow checks, or skill improvement candidates.

Imported observations must preserve provenance: source database, source table, source ID, observed
timestamp, and confidence. Imports may create proposed plans, tasks, links, or progress events, but
must not silently overwrite canonical planning rows.

## Required Database

Default path:

```text
plans/planning.sqlite3
```

The database is initialized by `codex_supervisor.planning.initialize_planning_database()`.

Inspection commands and helpers must open the existing database read-only. Do not initialize,
migrate, or create `plans/planning.sqlite3` just to answer orientation questions such as the current
task, current-queue plans, decisions, or recent progress.

Mutations must use typed helpers or CLI commands. `plan-upsert`, `milestone-upsert`, and
`criterion-upsert` create or replace planning structure; lifecycle/status commands only update
existing rows. `task-upsert` and `worker-run-upsert` preserve omitted optional contract/evidence
fields when updating existing rows; pass `--replace` only when intentionally resetting omitted
fields to empty/default values.

For current-work discovery, `story-loop-status` is the state machine. It distinguishes ready AFK,
running, HITL, blocked, completed, and empty queues across active and blocked current-queue plans by
default; `--all` adds completed, abandoned, and superseded history. `task-current` is only the
executable AFK selector. A null `task-current` result is not enough to say "there is no task" until
`story-loop-status` also reports `completed` or `empty`; in `running` or `hitl`, inspect the reported
`current_task_id` with `task-show`.

Use `plan-summary --current-queue` and `task-list --current-queue-plans-only` for fresh-thread
orientation. Use `--active-only` or `--active-plans-only` only when the task explicitly excludes
blocked successor plans.

## Required Tables

### `plans`

One row per active, completed, abandoned, or superseded plan.

| Column | Meaning |
| --- | --- |
| `plan_id` | Stable unique ID, for example `plan-supervisor-mvp`. |
| `slug` | Human-readable unique slug. |
| `title` | Short display title. |
| `goal` | Plain-language intended end state. |
| `non_goals_json` | JSON object of explicit non-goals. |
| `context_json` | JSON object with files, constraints, assumptions, and links. |
| `status` | `active`, `blocked`, `completed`, `abandoned`, or `superseded`. |
| `priority` | Integer sort key. Higher means more urgent. |
| `owner_agent` | Current coordinator. |
| `superseded_by_plan_id` | Replacement plan ID. |
| `created_at` / `updated_at` | UTC timestamps. |

Terminal plan states (`completed`, `abandoned`, and `superseded`) must not hide open work. Before a
plan enters a terminal state, child tasks must be terminal, milestones must be completed or
cancelled, and acceptance criteria must be completed, failed, or cancelled.

### `plan_milestones`

Major work slices inside a plan.

### `plan_acceptance_criteria`

Explicit completion conditions with optional verification commands.

### `plan_decisions`

Append-only decision log. Major architecture, source, safety, integration, workflow, and skill
choices belong here before or during implementation.

### `plan_progress_events`

Append-only event log for starts, completions, blockers, unblocks, verification, failures, and
handoffs.

### `plan_artifact_links`

Links plans to artifacts such as prompts, JSONL logs, worker result files, review outputs, reports,
and insight updates.

### `plan_commit_links`

Links plans to implementation, verification, or documentation commits.

### `supervisor_tasks`

Machine-readable work queue compiled from plans. Tasks are vertical slices and must be classified as
`AFK` or `HITL`.

Until dedicated Goal Contract tables exist, task-level goal/story-loop metadata belongs in:

- `scope_json` for Goal Contract context, in-scope boundaries, story-loop policy, and source links;
- `out_of_scope_json` for non-goals and blocked conditions;
- `acceptance_criteria_json` for evidence-based stop conditions;
- `verification_commands_json` for validation surfaces;
- `plan_progress_events.details` for story-loop iteration metadata such as task/run IDs;
- `worker_runs.metadata_json` for observed native Codex Goal state and worker execution metadata.

Open AFK tasks on active or blocked plans must already carry executable contracts: nonempty
acceptance criteria, cache-safe verification commands, and repo-relative allowed paths. A blocked
task is not a parking lot for an unsafe future contract; it should be ready to execute once the
blocker is resolved.

### `worker_runs`

One row per worker invocation, including backend, worktree, prompt, status, timing, result file, and
failure class.

Use `task-claim` or the typed claim helper when a worker is taking ownership of the next ready AFK
task. A claim must update the task to `running` and create the worker run in one transaction so two
fresh threads cannot claim the same task.

Completed worker runs must point `result_path` at an existing repo-local JSON result artifact and
link that artifact through `plan_artifact_links` with relationship `worker-result`. The artifact
must satisfy the Worker Result Contract in `CONTRACTS.md`, including worker-run identity coverage,
shared `worker_run_ids` entries that are completed runs with the same `result_path`, nonempty
completed-run evidence fields, zero-exit structured test records, exact acceptance-criterion
evidence, an `artifacts` entry for the JSON result file itself, and `changed_files` entries limited
to implementation or durable-documentation paths covered by task `allowed_paths_json`; markdown
reports can be linked separately as supporting evidence. Use tracked paths for durable result
evidence that must survive publication, and keep ignored `artifacts/`, `runs/`, `worktrees/`, and
`logs/` for ephemeral local output.

Use `worker-run-status ... --status completed --result-path <json>` or `worker-run-upsert` for normal
completion writes; the typed helper auto-links the result artifact as `worker-result`. Manual
`artifact-link-add` is still useful for supporting reports, prompts, or non-result evidence.

For `backend = "codex_exec"`, `metadata_json` stores launch preflight and evidence pointers that do
not deserve first-class columns yet:

- resolved Codex executable and `codex --version` output or failure class;
- intended `CODEX_HOME`, config path, sandbox mode, approval policy, and Goal Mode feature state;
- native-goal decision or prompt-rendered fallback decision;
- argv list used for `codex exec`;
- stdout, stderr, final-message, JSONL, diff-summary, and raw-result paths;
- host platform and launch working directory.

The backend may create or update a running row before all evidence paths exist, but a completed row
must still satisfy the Worker Result Contract and link the result artifact. A failed or blocked row
should preserve whatever evidence was captured and use `failure_class` plus progress events for
retry guidance.

## Correct Usage

Create or update a plan when work:

- spans multiple files or modules;
- changes a contract, source-of-truth document, queue behavior, adapter, skill, or worker backend;
- launches or coordinates multiple Codex workers;
- changes how future projects are spawned;
- touches source locks, planning DB schema, or the insights graph.

For each active or blocked current-queue plan:

- create a `plans` row before implementation;
- add milestones and acceptance criteria;
- append decisions as tradeoffs are resolved;
- append progress events when work starts, completes, blocks, unblocks, verifies, or hands off;
- link relevant Codex thread IDs, goal IDs, automation IDs, worker artifacts, and issue IDs as
  evidence when available;
- link artifacts and commits;
- update markdown source-of-truth only when stable behavior changes;
- update `insights/` when a reusable workflow lesson is learned.

Do not:

- use chat as the only memory for a multi-stage plan;
- hide durable decisions only in worker logs;
- create loose markdown plans in the repo root;
- mark a plan completed until acceptance criteria are verified or waived;
- mark a plan abandoned, completed, or superseded while it still has open child work;
- edit locked top-level documents without updating the source lock guard.

## Bootstrap Seed Contract

The initial database seed should contain `plan-bootstrap-supervisor`, which covers the creation of
this repo, source-of-truth documents, source clones, Python skeleton, and handoff for implementation.
This is historical seed doctrine, not the live-work selector. Live work selection must always come
from `story-loop-status`, then `task-show <current_task_id>` or `task-current` according to queue
state.
