---
name: fresh-context-worker
description: Prepare prompts and handoffs for fresh-context Codex workers. Use when designing or reviewing worker prompts, result schemas, or context handoffs; until the Stage 6 backend exists, do not imply the supervisor can launch workers automatically.
---

# Fresh Context Worker

Every worker prompt should be self-contained and small.

Until ROADMAP Stage 6 is implemented, prepare a manual worker handoff or current-thread execution
prompt. Do not claim `codex-supervisor` can launch Codex Exec workers automatically.

If the current user turn is read-only, review-only, audit-only, no-edits, or no-mutation mode, do
not start workers, create worktrees, write prompt artifacts, update planning state, or mutate git or
trackers. Return the proposed worker prompt, context bundle, result schema, and next commands only.

If using native Codex Goals, route through `goal-contract-drafter` and apply its Goal Mode preflight,
including the `${CODEX_HOME}/config.toml` `[features] goals = true` fallback.

## Include

- task contract;
- Goal Contract from `goal-contract-drafter`;
- relevant source-of-truth file pointers;
- acceptance criteria;
- allowed paths;
- verification commands;
- output schema;
- explicit stop conditions.
- where to record progress, artifacts, and reusable learnings.

## Standard Result Schema

Require workers to return:

- `worker_run_id` for a single-run result, or `worker_run_ids` for an explicitly shared synthesized
  result whose entries are completed worker runs with the same `result_path`.
- `status`: `completed`, `blocked`, `failed`, or `needs_review`.
- `summary`.
- `changed_files`.
- `tests_run`: objects with `command`, integer `exit_code`, and important output summary.
- `acceptance_results`: exact task acceptance criteria mapped to passing evidence.
- `risks`: residual risks, blockers, and test gaps.
- `follow_up_tasks`.
- `artifacts`.
- `handoff_notes`: record updates made or still needed.

Use these field names because they mirror `CONTRACTS.md`. Do not invent a parallel worker result
schema inside prompts. When a worker run is marked `completed`, `summary`, `changed_files`,
`tests_run`, `acceptance_results`, `artifacts`, and `handoff_notes` must be nonempty evidence fields.
Each `tests_run[].summary` must be nonblank and must not use stale phrasing such as "passed at the
time"; use current passing verifier evidence or record the gap in `risks`.
The worker run `result_path` must point at that existing repo-local JSON artifact so
`scripts/check_planning_integrity.py` can validate worker-run identity, zero-exit verification
commands, exact acceptance coverage, changed files inside `allowed_paths`, and artifact links. For
shared synthesized results, every `worker_run_ids` entry must be a completed worker run whose
`result_path` is that same JSON file. Link the JSON result through `plan_artifact_links` with
relationship `worker-result`, and include that same `result_path` in the JSON result's
`changed_files` and `artifacts` lists. Link markdown reports separately as supporting artifacts.

## Exclude

- unrelated chat history;
- full source dumps when file paths are enough;
- broad refactor permission;
- hidden tests or private fixtures.
- multiple unrelated stories in one worker prompt.
