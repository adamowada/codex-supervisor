---
name: codex-supervisor
description: Operate codex-supervisor from Codex Desktop by inspecting and mutating supervisor state through MCP, using the Python CLI as the reference workflow surface, and choosing existing repo-local workflows for project bootstrap, queue inspection, worker launch, review, ACP, and handoff.
---

# Codex Supervisor Desktop Workflow

Use this skill when Codex Desktop is operating the `codex-supervisor` plugin.

## Authority

- Treat `plans/planning.sqlite3` as the queue and worker-evidence authority.
- Use MCP tools for inspection and guarded mutation when available.
- Use `uv run --no-sync python -B -m codex_supervisor.cli ...` as the reference queue mutation and
  evidence workflow when MCP is unavailable or an operation needs CLI-only flags.
- Before full-AFK, project bootstrap, worker launch, or `task-current`, call
  `codex_supervisor.runtime_preflight` through MCP. Use canonical dotted MCP tool names in
  `mcp_tools`, for example `codex_supervisor.runtime_preflight`, not Desktop callable aliases such
  as `codex_supervisor_runtime_preflight`.
- Treat `tool_search` as discovery, not inventory. It may return only a subset of exposed MCP
  tools; do not block a plugin full-AFK run merely because `tool_search` omitted a required tool.
  The live MCP `runtime_preflight` handler inventories the actual server tool surface. When
  `tool_search` is needed to load the canary, search for `canary` or
  `Desktop full-AFK canary fail-closed execution-mode ledger`; name-only queries such as
  `runtime_preflight` are not reliable.
- Do not pass `tool_search` results as authoritative `mcp_tools`, and do not pass
  `mcp_startup_diagnostic` merely because the canary was discovered through `tool_search`. Use
  `mcp_startup_diagnostic` only when a diagnostic MCP fallback or launcher reports a real startup
  failure.
- Desktop plugin full-AFK readiness must be authorized by that live MCP canary in the current
  Desktop session. If MCP is unavailable, a CLI `runtime-preflight` run may be used only to diagnose
  package, cache, PATH, or launcher problems; it must not approve plugin full-AFK readiness and must
  not override a successful live MCP canary.
- If the live MCP canary is unavailable or blocked, stop, report the diagnostic, and record the
  setup repair needed. Do not continue as a supervisor run.
- Runtime canary: for plugin full-AFK requests, the first supervisor action must prove that
  `codex_supervisor.runtime_preflight` is callable. If `tools/list` does not expose that tool, or
  the tool returns `status=blocked`, refuse current-thread implementation and report the diagnostic
  or setup repair needed.
- Read `HANDOFF.md` only after `story-loop-status --json`; update it after planning SQLite changes.
- Use `.agents/skills/skill-router/SKILL.md` to choose the detailed repo-local skill for the next
  workflow.

## Workflow Map

- Project bootstrap: route to `spawned-project-bootstrap` for full factory scaffolds or
  `setup-agent-docs` for lightweight imported-skill prerequisites. Plugin full-AFK requests always
  use the supervisor-managed scaffold tier. After `spawned-project-apply`, treat the scaffold task
  as already completed by deterministic apply evidence; seed or compile the user's concrete
  implementation request as a new project-local task before calling `story-loop-run-once`.
- Queue inspection: start with `story-loop-status --json`, then
  `task-current --after-story-loop-status --json`,
  `task-show <task-id> --json`, or `plan-summary --current-queue --json` as needed.
- Worker launch: route to `story-loop-runner`; render `goal-contract-render --task-id <task-id>`;
  claim with `task-claim` only when the queue still selects that task.
- Review: for a separate review task with `worker_backend=codex_review`, run `review-run-live`
  against the source task target, then use `review-result-promote` when the structured result has
  no accepted or needs-HITL findings. Use `fresh-thread-code-reviewer` for ordinary manual reviews
  and persist imported structured results with `review-result-ingest`.
- ACP: route to `acp-publisher`; run `uv run --no-sync python -B scripts/verify.py
  --publication-ready` after staging and before committing.
- Handoff: route to `context-compaction-handoff` before context risk or `thread-resume-brief` when
  resuming; keep operational history in planning SQLite.

## Guardrails

- Do not write directly to Codex internal SQLite databases.
- Do not treat MCP as the state owner.
- Skill-only mode is not supervisor mode. For plugin full-AFK, missing live MCP is a blocker even if
  the CLI package is installed; ask for setup/repair or explicitly downgrade to plain Codex only
  after the user chooses that.
- Mutating MCP tools are enabled by default; use `--disable-mutations` only for an intentionally
  read-only Desktop session.
- Do not launch live workers unless the selected backend, Codex executable, `CODEX_HOME`, and Goal
  Mode preflight support it.
- Full-AFK work must not fall back to current-thread implementation. Record a blocker or HITL task
  instead.
- In full-AFK, `review_required=true` creates a separate AFK review task by default; escalate to
  HITL only when the review result needs human authority, product judgment, credentials, or risk
  acceptance.
- Native Codex Goals are allowed only when linked to a supervisor task and rendered Goal Contract.
- Memory database fallback cannot satisfy supervised full-AFK acceptance.
- Do not publish marketplace entries or install into a clean Desktop profile unless the current
  planning task explicitly includes that scope.
