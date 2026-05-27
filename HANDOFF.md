# HANDOFF.md

Last updated: 2026-05-27

This file is a compact resume snapshot only. Canonical queue state, completion records, worker
evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Current queue state: HITL. `story-loop-status --json` selects
  `task-review-review-required-hitl-gap-20260527`.
- Smoke-7 hardening was implemented, verified, committed, and pushed as
  `fc07fb38dfb42ba308f137f78b2e4c39705df82f`.
- User audited `todo-list-test-8`, then selected four surgical repairs for implementation:
  manual promotion bookkeeping evidence, steering-only durable browser-smoke recording, bootstrap
  plan completion steering, and OS-agnostic guidance for generated build artifacts / command
  examples / promotion flow.
- Smoke-8 surgical repairs are implemented and verified. Planning SQLite records the start and
  verification as `progress-smoke8-surgical-repairs-start-20260527` and
  `progress-smoke8-surgical-repairs-verified-20260527`.
- Verification passed: `uv run --no-sync python -B scripts/verify.py`.
- ACP publication is in progress for this change set. Planning SQLite records the publication start
  and publication-ready verification as `progress-smoke8-surgical-repairs-acp-start-20260527` and
  `progress-smoke8-surgical-repairs-acp-verified-20260527`.

## Next Action

After publication, resume from the HITL checkpoint
`task-review-review-required-hitl-gap-20260527` unless the user asks for a different next action.
Do not resolve that checkpoint unless the user explicitly asks for the review outcome.
