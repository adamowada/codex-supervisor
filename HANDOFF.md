# HANDOFF.md

Last updated: 2026-05-27

This file is a compact resume snapshot only. Canonical queue state, completion records, worker
evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Current queue state: HITL. `story-loop-status --json` selects
  `task-review-review-required-hitl-gap-20260527`.
- User asked to implement todo-list-test-7 smoke hardening fixes. Intent and completion are
  recorded as `progress-smoke7-hardening-start-20260527` and
  `progress-smoke7-hardening-verified-20260527`.
- Implemented repair scope: Codex Exec now probes requested model/reasoning before live worker
  spawn and fails closed for unknown probe failures; Story Loop links worker result and evidence
  manifest artifacts into planning SQLite; worktree state expands untracked directory summaries into
  concrete files; spawned-project scaffolds ignore local `.env`, steer post-worker repair into
  separate supervisor tasks, and require final commit links for full-AFK completion; planning
  integrity enforces commit links for completed final-commit-required AFK tasks.
- Verification passed: `uv run --no-sync python -B scripts/verify.py`.
- ACP requested for this change set. Publication intent is recorded as
  `progress-smoke7-hardening-acp-start-20260527`.

## Next Action

Publish the completed smoke-7 hardening change set. The current queue remains HITL on
`task-review-review-required-hitl-gap-20260527` unless the user explicitly resolves that review
checkpoint.
