# Worker Result Contract

This support document is read-only doctrine for repo-local skills. It does not authorize edits,
database writes, tracker mutations, worker launches, or git actions by itself.

Completed worker runs must produce one repo-local JSON result file and pass it to
`worker-run-status ... --result-path <json>` or the equivalent typed ingestion helper. The raw JSON
path is a transient import source; after ingestion, durable completion evidence lives in
`worker_result_records`, `worker_result_run_links`, and the completed `worker_runs.result_id`.

Required JSON fields:

- `worker_run_id` for single-run evidence, or `worker_run_ids` for explicitly shared synthesized
  evidence.
- `status`: `completed`, `blocked`, `failed`, or `needs_review`.
- `summary`: nonblank current evidence summary.
- `changed_files`: implementation or durable-documentation paths changed by the worker and covered
  by task `allowed_paths`.
- `tests_run`: objects with `command`, integer `exit_code`, and nonblank current summary.
- `acceptance_results`: exact task acceptance criteria mapped to passing evidence.
- `risks`: residual risks, blockers, and test gaps.
- `follow_up_tasks`: follow-up work that should be shaped separately.
- `artifacts`: tracked supporting docs/reports, tracked insight or handoff anchors, or external URLs
  that help explain the result. It may be empty when the raw worker JSON was only a transient import
  source.
- `handoff_notes`: record updates made or still needed.

Rules:

- If a `worker_runs.status` row is marked `completed`, the JSON `status` for its `result_path`
  must also be `completed`. Blocked, failed, cancelled, or needs-review evidence must not be reused
  as the completed worker result.
- Do not link ignored raw worker JSON, run logs, review outputs, or worktree artifacts through
  `plan_artifact_links` for publication. Link only tracked durable support artifacts or external
  URLs; the DB-backed worker result is the durable completion authority.
- Link tracked markdown reports separately as supporting artifacts when they are intentionally part
  of the public checkpoint.
- For shared synthesized results, every `worker_run_ids` entry must be a completed worker run linked
  to the same DB-backed result record.
- `changed_files` should not include evidence files that merely prove the run unless that evidence
  file is itself the implementation or durable-documentation change under the task scope.
- `tests_run[].command` must pass the safe verification parser; use `uv run --no-sync ...` when
  recording `uv run` verification evidence.
- `tests_run[].summary` must be current and nonblank; avoid stale phrasing such as "previously
  passed" or "passed at the time".
