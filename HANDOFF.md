# HANDOFF.md

Last updated: 2026-05-25

This file is a compact handoff snapshot only. Canonical queue state, completion records, imported
legacy evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Current queue state: ready by `story-loop-status --json`.
- Active plan: `plan-v1-live-operational-hardening`.
- Current AFK task: `task-v1-live-story-loop-worker`.
- Latest planning checkpoint: six-lane v1 hardening review digested in
  `progress-v1-six-lane-review-digested-20260525`.
- Durable insights: `insights/v1-hardening-clarifications.md` and
  `insights/v1-hardening-review.md`.
- Codex CLI smoke: npm `codex-cli 0.133.0` resolves in the current shell, and `codex exec --help`
  is available. Previous Windows executable resolution drift is not a current blocker for this
  process.

## Active Policy For Next Work

- Continue on `main`.
- Do one verified vertical slice at a time, then ACP.
- Before pushing, confirm remote `main` still equals local pre-commit ancestry; if it moved, stop
  for HITL direction.
- Do not use parallel writer workers in the v1 hardening run.
- Default live Codex launches to the user's normal Codex home; expose `--codex-home` for explicit
  override.
- Mutating MCP tools are default-on with an explicit opt-out flag.
- Live review and live smoke tests must exercise real Codex/API behavior when the product promises
  live behavior.
- Keep local absolute project roots out of tracked docs and planning records.

## Next Action

Implement `task-v1-live-story-loop-worker`: production live Story Loop worker execution with an
isolated git worktree, enforced Codex launch options, Goal Contract/result prompt composition,
bounded subprocesses, minimal environment, JSONL/stdout/stderr/diff evidence, Worker Result
validation, and authoritative changed-path gating. Record progress, update durable insights only for
reusable learning, verify the slice, then ACP before moving to dependent MCP/review/release tasks.
