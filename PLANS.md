# PLANS.md

This file defines the planning system for `codex-supervisor`.

`PLANS.md` is immutable by default. Edit it only when the user specifically asks or when a clearly
approved plan changes the planning contract.

Active execution plans belong in `plans/planning.sqlite3`, not in markdown files.

## Planning Model

The planning database is tracked in git and acts as operational state for Codex. It answers:

- what are we trying to do;
- why are we doing it this way;
- what remains blocked or unverified;
- which tasks, worker runs, artifacts, reviews, and commits belong to the work;
- which lessons should be promoted into skills or `insights/`.

Markdown remains the source of truth for stable human-facing knowledge. Do not use planning tables
as a private replacement for `README.md`, `AGENTS.md`, contracts, architecture, SOP, or insights.

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

### `worker_runs`

One row per worker invocation, including backend, worktree, prompt, status, timing, result file, and
failure class.

## Correct Usage

Create or update a plan when work:

- spans multiple files or modules;
- changes a contract, source-of-truth document, queue behavior, adapter, skill, or worker backend;
- launches or coordinates multiple Codex workers;
- changes how future projects are spawned;
- touches source locks, planning DB schema, or the insights graph.

For each active plan:

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
- edit locked top-level documents without updating the source lock guard.

## Bootstrap Plan

The initial database should contain `plan-bootstrap-supervisor`, which covers the creation of this
repo, source-of-truth documents, source clones, Python skeleton, and handoff for implementation.
