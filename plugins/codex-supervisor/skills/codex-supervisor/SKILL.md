---
name: codex-supervisor
description: Operate codex-supervisor from Codex Desktop by inspecting supervisor state through MCP, routing mutations through the Python CLI and planning SQLite, and choosing existing repo-local workflows for project bootstrap, queue inspection, worker launch, review, ACP, and handoff.
---

# Codex Supervisor Desktop Workflow

Use this skill when Codex Desktop is operating the `codex-supervisor` plugin.

## Authority

- Treat `plans/planning.sqlite3` as the queue and worker-evidence authority.
- Use MCP tools for read-only inspection when available.
- Use `uv run --no-sync python -B -m codex_supervisor.cli ...` for queue mutations and evidence.
- Read `HANDOFF.md` only after `story-loop-status --json`; update it after planning SQLite changes.
- Use `.agents/skills/skill-router/SKILL.md` to choose the detailed repo-local skill for the next
  workflow.

## Workflow Map

- Project bootstrap: route to `spawned-project-bootstrap` for full factory scaffolds or
  `setup-agent-docs` for lightweight imported-skill prerequisites.
- Queue inspection: start with `story-loop-status --json`, then `task-current --json`,
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
- Do not launch live workers unless the selected backend, Codex executable, `CODEX_HOME`, and Goal
  Mode preflight support it.
- Do not publish marketplace entries, install into a clean Desktop profile, or add mutating MCP
  tools unless the current planning task explicitly includes that scope.
