# Worker Result Contract

This support document is read-only doctrine for repo-local skills. It does not authorize edits,
database writes, tracker mutations, worker launches, or git actions by itself.

Completed worker runs must produce one repo-local JSON result file and set the worker run
`result_path` to that same file.

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
- `artifacts`: repo-local result and support artifacts; must include the `result_path` JSON file.
- `handoff_notes`: record updates made or still needed.

Rules:

- Link the JSON result through `plan_artifact_links` with relationship `worker-result`.
- Link markdown reports separately as supporting artifacts.
- For shared synthesized results, every `worker_run_ids` entry must be a completed worker run whose
  `result_path` is that same JSON file.
- `changed_files` should not include evidence files that merely prove the run unless that evidence
  file is itself the implementation or durable-documentation change under the task scope.
- `tests_run[].command` must pass the safe verification parser; use `uv run --no-sync ...` when
  recording `uv run` verification evidence.
- `tests_run[].summary` must be current and nonblank; avoid stale phrasing such as "previously
  passed" or "passed at the time".
