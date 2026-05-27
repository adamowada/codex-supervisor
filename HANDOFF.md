# HANDOFF.md

Last updated: 2026-05-27

This file is a compact resume snapshot only. Canonical queue state, completion records, worker
evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Current queue state: HITL. `story-loop-status --json` selects
  `task-review-review-required-hitl-gap-20260527`.
- Smoke-10 surgical repairs are implemented, verified, committed, and pushed as `fa472b6`. Planning
  SQLite records
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
- CI for `fa472b6` failed only in Linux mypy:
  `src/codex_supervisor/worker_backends.py:1312: Module has no attribute
  "CREATE_NEW_PROCESS_GROUP"`. The current turn repaired that cross-platform typecheck gap with a
  lazy `subprocess` constant lookup and recorded
  `progress-ci-linux-mypy-process-group-repair-start-20260527` plus
  `progress-ci-linux-mypy-process-group-repair-verified-20260527` in planning SQLite.
- Local verification for the CI repair passed with
  `uv run --no-sync python -B -m mypy --no-incremental --platform linux src scripts` and
  `uv run --no-sync python -B -m mypy --no-incremental src scripts`.
- Staged publication-ready verification for the CI repair passed with
  `uv run python -B scripts/verify.py --publication-ready`.
- Replacement GitHub Actions run `26504128492` confirmed the Linux mypy repair, then failed planning
  integrity because ignored historical worker evidence paths under `runs/`, `artifacts/`, and
  `worktrees/` are absent in a clean CI checkout. The current turn repaired that by making path
  existence strict when an ignored runtime root exists locally and non-fatal when the whole ignored
  root is absent, with the durable lesson recorded in `insights/workflow-patterns.md`.
- Focused verification for the clean-checkout repair passed:
  `uv run --no-sync python -B -m pytest tests/test_planning_integrity.py -q -p no:cacheprovider`,
  `uv run --no-sync python -B scripts/check_planning_integrity.py`, and
  `uv run --no-sync python -B -m mypy --no-incremental --platform linux src scripts`.

## Next Action

Verify and publish the clean-checkout evidence-path CI repair, then resume from the HITL checkpoint
`task-review-review-required-hitl-gap-20260527` unless the user asks for a different next action. Do
not resolve that checkpoint unless the user explicitly asks for the review outcome.
