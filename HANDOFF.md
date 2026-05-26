# HANDOFF.md

Last updated: 2026-05-26

This file is a compact handoff snapshot only. Canonical queue state, completion records, imported
legacy evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Current queue state: hitl. `story-loop-status --json` reports current HITL task
  `task-local-todo-webapp-desktop-smoke-rerun`; there is no current AFK or running task.
- Latest source-of-truth update: `AGENTS.md` now requires planning-first mutation discipline for
  non-read-only implementation, repair, ACP, scaffold, and workflow changes in this repository.
  Intent was recorded before edits as `progress-planning-first-rule-20260526`; verification was
  recorded as `progress-planning-first-rule-verified-20260526`.
- Latest implementation: hardened full-AFK supervisor execution after the `todo-list-test-4`
  diagnosis. MCP `story_loop_run_once` and `story_loop_advance` now accept explicit
  `planning_path` and `repo_root`; supervisor-managed full-AFK scaffolds initialize git and create a
  baseline commit; `codex_exec` maps supervisor reasoning effort through
  `model_reasoning_effort`; process evidence preserves raw bytes and decodes with UTF-8 replacement
  only at display boundaries; completed workers must have ignored `runs/` and `artifacts/`
  evidence plus an evidence manifest before planning ingestion; and `review_required=true` creates
  a separate HITL review task.
- Planning progress recorded:
  `progress-supervisor-full-afk-hardening-20260526` and
  `progress-planning-first-rule-20260526` /
  `progress-planning-first-rule-verified-20260526`.
- Planning integrity repair recorded a HITL rerun task for `plan-local-todo-webapp` so the pending
  smoke criteria have an explicit current-queue action instead of orphaned criteria.
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
  `todo-list-test-2` smoke. The Python package version remains `0.1.1`; the Desktop plugin
  manifest is now `0.1.2`; `.mcp.json` starts `plugins/codex-supervisor/scripts/mcp_launcher.py`
  from the plugin root; the launcher delegates from source or Desktop cache to the real MCP server
  and otherwise exposes a diagnostic `codex_supervisor.runtime_preflight` fallback.
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
- Latest CI repair: the Verify workflow failed during GitHub Actions setup before repo code ran
  while downloading `astral-sh/setup-uv`; rerunning reproduced the failure, and switching from the
  `v5` tag object to the peeled commit still failed. The workflow now avoids that extra action
  download and installs `uv==0.11.7` with `python -m pip install` after `actions/setup-python`, with
  a regression test and durable insight update.
- Latest Desktop smoke diagnosis and repair: `todo-list-test-4` exposed that `tool_search` is not
  an MCP inventory. The session could call `codex_supervisor.runtime_preflight`, but later
  `tool_search` returned other supervisor tools without returning the canary. The live MCP
  `runtime_preflight` handler now self-inventories `list_mcp_tools(context)` and uses
  client-provided `mcp_tools` only as supplemental diagnostics. The runtime preflight tool metadata
  now says `Desktop full-AFK canary`, and the Desktop plugin manifest version was bumped to
  `0.1.2` so Desktop had a refresh boundary for the packaged skill.
- Latest rerun diagnosis: after Desktop reloaded cache `0.1.2`, the user-entered skill mention still
  contained a stale `0.1.1` path, but the cache itself had only `0.1.2` and the agent read that
  version. The installed-cache verifier showed direct MCP `tools/list` includes
  `codex_supervisor.runtime_preflight`. The halted turn failed because `tool_search` returned
  queue/worker tools for a broad query, then returned no canary for name-only queries such as
  `runtime_preflight codex_supervisor` and `preflight`. The completed repair changed the packaged
  skill to discover the canary with semantic query terms such as `canary`, ignored false
  client-supplied startup diagnostics in the live MCP handler, and bumped the Desktop plugin
  manifest to `0.1.3`.
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

Rerun the Desktop smoke in a fresh folder and confirm the supervised path reaches a real
project-local Story Loop run rather than a CLI/current-thread fallback.
