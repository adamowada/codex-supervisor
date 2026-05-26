# HANDOFF.md

Last updated: 2026-05-26

This file is a compact handoff snapshot only. Canonical queue state, completion records, imported
legacy evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Current queue state: completed. `story-loop-status --json` reports no open AFK, HITL, running,
  blocked, or pending tasks for `plan-v1-live-operational-hardening`.
- Active plan: `plan-v1-live-operational-hardening`.
- Current AFK task: none.
- Latest release-readiness target checked during architecture-fix work: code commit
  `d88ddf4c277dc7625bd89b7fbf641b0639f49df8`.
- Latest release-readiness result: `ready: false`, 10/16 checks passing. Real bootstrap smoke
  evidence now passes via `progress-real-bootstrap-arch-fixes-d88ddf4c` with embedded
  `spawned-project-apply` evidence in `plans/planning.sqlite3`; the remaining gaps are current
  CI, publication-ready verification, Windows validation, live worker smoke, live review smoke, and
  mutating MCP smoke for the checked target. After the architecture-fix ACP, refresh release
  readiness for the new commit before any release action.
- Durable insights: `insights/v1-hardening-clarifications.md`,
  `insights/v1-hardening-review.md`, and `insights/release-readiness-evidence.md`.
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

Wait for the user's explicit release instruction. Until then, do not create a release tag or publish
release artifacts. A fresh session should run
`uv run --no-sync python -B -m codex_supervisor.cli release-readiness --json` before release action
and refresh any stale evidence until it reports `ready: true`.
