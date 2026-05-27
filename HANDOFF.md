# HANDOFF.md

Last updated: 2026-05-27

This file is a compact resume snapshot only. Canonical queue state, completion records, worker
evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Current queue state: HITL. `story-loop-status --json` selects
  `task-review-review-required-hitl-gap-20260527`.
- Smoke-10 surgical repairs are implemented and focused tests pass. Planning SQLite records
  `task-smoke10-worker-result-evidence-repairs-20260527`,
  `progress-smoke10-repairs-start-20260527`, and
  `progress-smoke10-repairs-verified-20260527`.
- The smoke-10 repair makes worker-result schemas strict for `browser_smoke_results`, validates and
  copies support artifacts from the worker worktree before ingestion, strengthens full-AFK evidence
  and final-state commit integrity checks, tightens generated spawned-project guidance, and records
  the durable lesson in `insights/workflow-patterns.md`.
- Focused verification passed:
  `uv run --no-sync python -B -m pytest tests/test_worker_backends.py tests/test_worker_results.py tests/test_story_loop.py tests/test_planning_integrity.py tests/test_spawned_projects.py -q -p no:cacheprovider`
  and `uv run --no-sync python -B scripts/check_planning_integrity.py`.
- Full verification passed with `uv run --no-sync python -B scripts/verify.py`. ACP publication
  for the smoke-10 repair is in progress in the current turn.

## Next Action

ACP the smoke-10 repair, then resume from the HITL checkpoint
`task-review-review-required-hitl-gap-20260527` unless the user asks for a different next action.
Do not resolve that checkpoint unless the user explicitly asks for the review outcome.
