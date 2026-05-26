# HANDOFF.md

Last updated: 2026-05-26

This file is a compact handoff snapshot only. Canonical queue state, completion records, imported
legacy evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Current queue state: completed after `plan-plugin-cache-launcher-20260526`
  (`Desktop Plugin Cache Launcher And Runtime Canary`).
- Completed AFK task: `task-plugin-cache-launcher-runtime-canary`, with DB-backed worker result
  `worker-run-plugin-cache-launcher-runtime-canary-20260526`.
- Completed fix: repaired the Desktop plugin cache/runtime boundary exposed by the second
  `todo-list-test-2` smoke. The source guardrails existed, but Desktop loaded stale cached plugin
  version `0.1.0`, and the cached `.mcp.json` resolved `../..` inside `$CODEX_HOME/plugins/cache`
  instead of to the `codex-supervisor` source package.
- Implementation result: plugin/package version is now `0.1.1`; `.mcp.json` starts
  `plugins/codex-supervisor/scripts/mcp_launcher.py` from the plugin root; the launcher delegates
  from source or Desktop cache to the real MCP server and otherwise exposes a diagnostic
  `codex_supervisor.runtime_preflight` fallback; the packaged skill now requires that runtime
  canary before plugin full-AFK work.
- Local Desktop cache refresh: copied the updated plugin into
  `$CODEX_HOME/plugins/cache/codex-supervisor-local/codex-supervisor/0.1.1`. Source and real
  Desktop-profile plugin verification both pass and expose `codex_supervisor.runtime_preflight`.
- Previous completed plan: `plan-plugin-runtime-guardrails-20260526`
  (`Desktop Plugin Runtime Guardrails`).
- Previous completed AFK task: `task-plugin-runtime-preflight-guardrails`.
- User-selected implementation posture: real Desktop/profile smoke that inspects exposed tools;
  visible Desktop/plugin MCP startup diagnostics; callable preflight tool instead of prose-only
  behavior; block current-thread fallback for full-AFK; allow native Goals only when linked to a
  supervisor task/contract; always scaffold supervisor-managed for plugin full-AFK requests; forbid
  memory database fallback for supervised full-AFK acceptance; require `story-loop-status` before
  `task-current`.
- Verification for the completed slice: focused runtime/MCP/plugin/planning tests passed, and
  `uv run --no-sync python -B scripts/verify.py` passed.
- Durable lesson recorded in `insights/workflow-patterns.md`: source plugin fixes are not live
  Desktop fixes until the installed cache proves it has refreshed, and MCP launchers need a
  diagnostic fallback.
- Previous v1 hardening plan: `plan-v1-live-operational-hardening` remains active but has no open
  work; `story-loop-status --json` reports it as completed within the current queue.
- Latest release-readiness target checked during architecture-fix work: code commit
  `d88ddf4c277dc7625bd89b7fbf641b0639f49df8`.
- Latest release-readiness result: `ready: false`, 10/16 checks passing. Real bootstrap smoke
  evidence now passes via `progress-real-bootstrap-arch-fixes-d88ddf4c` with embedded
  `spawned-project-apply` evidence in `plans/planning.sqlite3`; the remaining gaps are current
  CI, publication-ready verification, Windows validation, live worker smoke, live review smoke, and
  mutating MCP smoke for the checked target. After the architecture-fix ACP, refresh release
  readiness for the new commit before any release action.
- Durable insights: `insights/v1-hardening-clarifications.md`,
  `insights/v1-hardening-review.md`, `insights/release-readiness-evidence.md`,
  `insights/workflow-patterns.md`, and `insights/graph.md`.
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

ACP the completed plugin cache launcher slice, then rerun the Desktop smoke in a fresh folder.
