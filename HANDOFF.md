# HANDOFF.md

Last updated: 2026-05-27

This file is a compact resume snapshot only. Canonical queue state, completion records, worker
evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Current queue state: completed for the latest slice. `story-loop-status --json` reports no open
  work on `plan-operation-naming-surface-deepening-20260527`.
- The user asked to fix all architecture deepening candidates one by one with ACP after each, then
  fix all actionable naming inconsistencies one by one with ACP after each.
- `task-operation-registry-deepening-20260527` completed the first slice: a central operation
  registry now owns CLI/MCP naming and required supervisor tool surfaces for runtime/plugin checks.
- Planning SQLite records `progress-operation-registry-deepening-start-20260527` for this work.
- Planning SQLite also records `progress-operation-registry-deepening-verified-20260527`; focused
  registry/MCP/plugin/preflight tests and full `scripts/verify.py` passed.
- `task-worker-result-ingestion-deepening-20260527` completed the second slice: the
  `worker_result_ingestion` module now backs CLI/MCP/Story Loop ingestion, and
  `worker-result-ingest` is a real CLI command.
- Planning SQLite records `progress-worker-result-ingestion-deepening-start-20260527` for the
  second slice.
- Planning SQLite also records `progress-worker-result-ingestion-deepening-verified-20260527`;
  focused ingestion/registry/planning/MCP tests and full `scripts/verify.py` passed.
- `task-execution-surface-deepening-20260527` completed the third slice: `execution_surface`
  now owns codex_exec status, native-goal fallback posture, and capability mapping vocabulary used
  by Goal Contracts and worker backends.
- Planning SQLite records `progress-execution-surface-deepening-start-20260527` for the third
  slice.
- Planning SQLite also records `progress-execution-surface-deepening-verified-20260527`; focused
  execution-surface/goal-contract/worker-backend/runtime-preflight tests and full
  `scripts/verify.py` passed.
- `task-queue-selection-surface-deepening-20260527` completed the fourth slice: `queue_selection`
  now owns next-executable-AFK selection, `task-next-afk`/`codex_supervisor.task_next_afk` are the
  explicit caller surfaces, and `task-current` remains a legacy compatibility alias.
- Planning SQLite records `progress-queue-selection-surface-start-20260527` for the fourth slice.
- Planning SQLite also records `progress-queue-selection-surface-verified-20260527`; focused
  queue-selection/planning/story-loop/MCP/runtime/registry tests and full `scripts/verify.py`
  passed.
- `task-evidence-vocabulary-deepening-20260527` completed the fifth slice:
  `evidence_vocabulary` now owns final-state commit relationships, worker-result artifact links,
  review/promotion/browser-smoke events, Codex-state reconciliation labels, and
  publication/CI/PR/issue evidence names.
- Planning SQLite records `progress-evidence-vocabulary-start-20260527` for the fifth slice.
- Planning SQLite also records `progress-evidence-vocabulary-verified-20260527`; focused
  evidence/planning/integrity tests and full `scripts/verify.py` passed.
- `task-worker-run-event-cli-20260527` completed the first actionable naming fix:
  `worker-run-event-list` now mirrors `codex_supervisor.worker_run_event_list` as a DB-backed CLI
  read surface.
- Planning SQLite records `progress-worker-run-event-cli-start-20260527` for this slice.
- Planning SQLite also records `progress-worker-run-event-cli-verified-20260527`; focused
  registry/planning/MCP tests and full `scripts/verify.py` passed.
- `task-codex-executable-alias-20260527` completed the second actionable naming fix: prefer
  `codex_executable`/`--codex-executable` on live worker launch surfaces while preserving
  `codex_bin`/`--codex-bin` compatibility.
- Planning SQLite records `progress-codex-executable-alias-start-20260527` for this slice.
- Planning SQLite also records `progress-codex-executable-alias-verified-20260527`; focused
  launch-surface tests and full `scripts/verify.py` passed.
- `task-selector-ingestion-doc-names-20260527` completed the third actionable naming fix: steer
  repo-local skills and source-of-truth docs to `task-next-afk` and `worker-result-ingest` as
  canonical surfaces.
- Planning SQLite records `progress-selector-ingestion-doc-names-start-20260527` for this slice.
- Planning SQLite also records `progress-selector-ingestion-doc-names-verified-20260527`; full
  `scripts/verify.py` passed.
- `task-execution-mode-name-20260527` completed the fourth actionable naming fix: make Codex Exec
  execution-surface `execution_mode` match the runtime preflight `worker_execution=codex_exec`
  value.
- Planning SQLite records `progress-execution-mode-name-start-20260527` for this slice.
- Planning SQLite also records `progress-execution-mode-name-verified-20260527`; focused
  execution-surface tests and full `scripts/verify.py` passed.
- The previously cleared queue remains historical: `plan-v1-live-operational-hardening` was
  abandoned after the user requested clearing that checkpoint.

## Next Action

ACP `task-execution-mode-name-20260527`; then seed and handle the next actionable naming
inconsistency one slice at a time.
