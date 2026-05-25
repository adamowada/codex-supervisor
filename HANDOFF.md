# HANDOFF.md

Last updated: 2026-05-25 03:37 PDT

This file is a compact handoff snapshot only. Canonical queue state, completion records, imported
legacy evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Active Goal posture: dangerous_full_auto/approved_afk Story Loop execution, one current AFK slice
  at a time from planning SQLite.
- Current queue state: `ready`.
- Active plan: `plan-stage12-codex-plugin-desktop-experience`
  (`Stage 12 Codex Plugin And Desktop Experience`, priority 78).
- Current AFK task: `task-stage12a-plugin-mcp-scaffold`.
- Worker backend: `codex_exec`, with inline supervised fallback expected until the local Codex CLI
  path and native Goal Mode worker launch are proven usable.
- Review requirement: fresh-thread-style review before completion because plugin metadata and
  Desktop docs are public operator surfaces.

## Stage 12A Contract

Goal: add the smallest repo-local Codex Desktop plugin scaffold that exposes the existing read-only
supervisor MCP stdio server, documents local operator responsibilities, and verifies the new plugin
surface with focused tests and hygiene checks.

Allowed paths:

```text
plugins/codex-supervisor/**
tests/test_codex_plugin.py
scripts/check_file_justification.py
plans/planning.sqlite3
HANDOFF.md
insights/**
.agents/skills/**
```

Acceptance criteria:

- Repo-local plugin metadata and `.mcp.json` define a Codex Supervisor Desktop plugin that launches
  the existing `codex_supervisor.mcp_stdio` module through `uv` without live worker launch.
- Desktop-facing plugin docs explain CLI, MCP, skill, planning SQLite, HANDOFF, and trust-posture
  responsibilities without editing locked source-of-truth documents.
- File-purpose, planning integrity, full verification, and publication-ready hygiene checks pass
  with the plugin scaffold included.

Verification commands:

```sh
uv run --no-sync python -B -m pytest tests/test_codex_plugin.py -q -p no:cacheprovider
uv run --no-sync python -B scripts/check_file_justification.py
uv run --no-sync python -B scripts/check_planning_integrity.py
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B scripts/verify.py
uv run --no-sync python -B scripts/verify.py --publication-ready
```

Stop conditions:

- A HITL task becomes current in planning SQLite.
- Plugin conventions conflict with local Codex plugin schema examples.
- Verification repeatedly fails without a known repo-local fix.
- The slice requires external credentials, marketplace publishing, or live Desktop installation.

Out of scope:

- Marketplace or personal plugin registry writes.
- Actual clean Desktop install validation.
- Copied skill packaging or app manifests.
- Mutating MCP tools, worker launches, GitHub/CI integration, or release packaging.

## Recent Evidence

Stage 12A shaping completed:

```sh
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B -m codex_supervisor.cli task-current --json
uv run --no-sync python -B scripts/check_planning_integrity.py
```

Planning integrity passed, and `story-loop-status` selected
`task-stage12a-plugin-mcp-scaffold` as the current ready AFK task.

Prior completed checkpoint:

- Completed plan: `plan-stage11-mcp-server`.
- Completed task: `task-stage11b-mcp-stdio-transport`.
- Added `src/codex_supervisor/mcp_stdio.py` and `tests/test_mcp_stdio.py`.
- Publication-ready verification passed before ACP.

## Next Action

Execute `task-stage12a-plugin-mcp-scaffold` through the Story Loop, using `plugin-creator`,
`story-loop-runner`, and `planning-sqlite-operator` guidance as needed. After implementation,
run the task verification commands, perform the required review, fix accepted findings, update
planning SQLite and this handoff, then ACP the step.
