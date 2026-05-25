# HANDOFF.md

Last updated: 2026-05-25

This file is a compact handoff snapshot only. Canonical queue state, completion records, imported
legacy evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Current queue state: empty by `story-loop-status --json`.
- Latest planning checkpoint: `plan-v1-hardening-clarifications`, completed.
- Durable clarification insight: `insights/v1-hardening-clarifications.md`.
- Source-of-truth doctrine updated intentionally in `DECISIONS.md` D-0013 through D-0018.
- Resolved stale question file: `insights/open-questions.md` was removed after the answers were
  recorded in planning SQLite, decisions, and the new insight.
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

Begin the v1 operational hardening implementation from the recorded policy. Start with a fresh
whole-project review or task decomposition, then execute fixes as verified vertical slices with
planning progress, durable insights only when they capture reusable learning, focused verification,
and ACP.
