# HANDOFF.md

Last updated: 2026-05-26

This file is a compact handoff snapshot only. Canonical queue state, completion records, imported
legacy evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Current queue state: completed. `story-loop-status --json` reports no current AFK, HITL, or
  running task.
- Completed repair plan: `plan-desktop-plugin-live-mcp-authority-20260526`
  (`Desktop Plugin Live MCP Authority`).
- Completed task: `task-desktop-plugin-live-mcp-authority`, with DB-backed worker result
  `worker-result-artifacts-worker-run-desktop-plugin-live-mcp-authority-20260526-fda9a201e7e3-0f5df64ab77d`.
- Completed fix: repaired the `todo-list-test-3` false canary failure. Desktop plugin full-AFK
  readiness must be authorized only by the live MCP `codex_supervisor.runtime_preflight` canary in
  the current Desktop session. CLI/package checks remain useful diagnostics after MCP failure, but
  they must not approve plugin full-AFK readiness or override a successful live MCP canary.
- Implementation result: runtime preflight normalizes Desktop callable tool-name aliases such as
  `codex_supervisor_runtime_preflight` to canonical dotted MCP names before required-tool
  comparison, records `entrypoint`, `required_surface`, and `decision_source`, blocks CLI
  diagnostics from authorizing plugin full-AFK, updates packaged Desktop skill wording, and adds
  focused regression tests.
- Durable lesson recorded in `insights/workflow-patterns.md`: Desktop plugin full-AFK requires live
  MCP authority; CLI preflight is diagnostics-only for that entrypoint.
- Previous completed fix: repaired the Desktop plugin cache/runtime boundary exposed by the second
  `todo-list-test-2` smoke. Plugin/package version is now `0.1.1`; `.mcp.json` starts
  `plugins/codex-supervisor/scripts/mcp_launcher.py` from the plugin root; the launcher delegates
  from source or Desktop cache to the real MCP server and otherwise exposes a diagnostic
  `codex_supervisor.runtime_preflight` fallback.
- Previous completed plan: `plan-plugin-runtime-guardrails-20260526`
  (`Desktop Plugin Runtime Guardrails`).
- Previous completed AFK task: `task-plugin-runtime-preflight-guardrails`.
- User-selected implementation posture: real Desktop/profile smoke that inspects exposed tools;
  visible Desktop/plugin MCP startup diagnostics; callable preflight tool instead of prose-only
  behavior; block current-thread fallback for full-AFK; allow native Goals only when linked to a
  supervisor task/contract; always scaffold supervisor-managed for plugin full-AFK requests; forbid
  memory database fallback for supervised full-AFK acceptance; require `story-loop-status` before
  `task-current`.
- Verification for the completed repair: focused runtime/MCP/plugin tests passed, and
  `uv run --no-sync python -B scripts/verify.py` passed.
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

ACP the completed live-MCP authority repair, then rerun the Desktop smoke in a fresh folder after
the updated plugin cache is available to Desktop.
