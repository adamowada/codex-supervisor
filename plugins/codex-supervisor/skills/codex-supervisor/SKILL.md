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
  use the supervisor-managed scaffold tier.
- Queue inspection: start with `story-loop-status --json`, then
  `task-current --after-story-loop-status --json`,
  `task-show <task-id> --json`, or `plan-summary --current-queue --json` as needed.
- Worker launch: route to `story-loop-runner`; render `goal-contract-render --task-id <task-id>`;
  claim with `task-claim` only when the queue still selects that task.
- Review: route to `fresh-thread-code-reviewer`; persist structured results with
  `review-result-ingest`.
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
- Native Codex Goals are allowed only when linked to a supervisor task and rendered Goal Contract.
- Memory database fallback cannot satisfy supervised full-AFK acceptance.
- Do not publish marketplace entries or install into a clean Desktop profile unless the current
  planning task explicitly includes that scope.
