# HANDOFF.md

Last updated: 2026-05-27

This file is a compact resume snapshot only. Canonical queue state, completion records, worker
evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Current queue state: HITL. `story-loop-status --json` selects
  `task-review-review-required-hitl-gap-20260527`.
- User asked to implement the todo-list-test-6 launch-hardening recommendations and ACP the result.
  Intent is recorded as `decision-todo-test-6-launch-hardening-20260527` and
  `progress-todo-test-6-launch-hardening-start-20260527`.
- Target repair scope: Windows Codex executable resolution, CLI model/reasoning capability mapping,
  honest/degraded worker execution labeling, evidence parity for completed worker runs,
  deterministic spawned-project bootstrap-to-implementation flow, and worker process cancellation
  diagnostics.
- Implementation completed. The worker backend now prefers launchable Windows `codex.cmd`/`.exe`
  over `.ps1` shims, records interruption cleanup, retries once with CLI defaults when model or
  reasoning transport is rejected before work starts, and preserves that capability decision in
  metadata. Spawned project apply now completes the scaffold task with deterministic evidence and
  generated steering says to seed the real implementation task before Story Loop.
- Verification passed. `uv run --no-sync python -B scripts/verify.py` completed successfully with
  582 tests plus Ruff, formatting, mypy, CLI help, planning integrity, public hygiene, source/skill
  inventory, protected-file checks, and `uv lock --check`.
- Planning progress `progress-todo-test-6-launch-hardening-verified-20260527` records the
  verification result.

## Next Action

ACP all unstaged changes as requested. The current queue remains HITL on
`task-review-review-required-hitl-gap-20260527`.
