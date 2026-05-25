# HANDOFF.md

Last updated: 2026-05-25 04:01 PDT

This file is a compact handoff snapshot only. Canonical queue state, completion records, imported
legacy evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Active Goal posture: dangerous_full_auto/approved_afk Story Loop execution, one current AFK slice
  at a time from planning SQLite.
- Current queue state: `ready`.
- Active plan: `plan-stage12-codex-plugin-desktop-experience`
  (`Stage 12 Codex Plugin And Desktop Experience`, priority 78).
- Current AFK task: `task-stage12b-plugin-skill-workflows`.
- Worker backend: `codex_exec`, with inline supervised fallback expected until the local Codex CLI
  path and native Goal Mode worker launch are proven usable.
- Review requirement: fresh-thread-style review before completion because plugin skills and Desktop
  workflow docs are public operator surfaces.

## Stage 12B Contract

Goal: package a Desktop-discoverable Codex Supervisor workflow skill inside the plugin and document
the operator command map for bootstrap, queue inspection, worker launch, review, ACP, and handoff
while keeping planning SQLite and the Python core authoritative.

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

- Plugin manifest references a local skills directory, and the plugin includes a valid Codex
  Supervisor Desktop workflow skill with frontmatter and guardrails.
- Plugin docs or skill guidance map Desktop workflows for project bootstrap, queue inspection,
  worker launch, review, ACP, and handoff to the Python CLI, MCP read surface, planning SQLite, and
  existing repo-local skills.
- Focused tests, file-purpose, planning integrity, full verification, and publication-ready hygiene
  checks pass after the packaged workflow skill is added.

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
- Plugin skill schema conflicts with local plugin validator examples.
- The slice requires external credentials, marketplace publishing, or clean Desktop installation.
- Verification repeatedly fails without a known repo-local fix.

Out of scope:

- Actual clean Codex Desktop installation validation.
- Marketplace or personal plugin registry writes.
- Copying every repo-local skill verbatim into the plugin archive.
- Mutating MCP tools, GitHub/CI integration, release packaging, or live worker launch.

## Recent Evidence

Stage 12B shaping completed:

```sh
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B -m codex_supervisor.cli task-current --json
uv run --no-sync python -B scripts/check_planning_integrity.py
```

Planning integrity passed, and `story-loop-status` selected
`task-stage12b-plugin-skill-workflows` as the current ready AFK task.

Prior completed checkpoint:

- Completed task: `task-stage12a-plugin-mcp-scaffold`.
- Worker run: `worker-run-stage12a-plugin-mcp-scaffold-inline-20260525`, completed with DB result
  `worker-result-stage12a-plugin-mcp-scaffold-result`.
- Implementation commit: `02a4ae986f3ed7fed8506787b9f863fe35aac1bd`.
- Evidence link commit: `332d2e7f5f18775d765c757ea030b754008bff1e`.

## Next Action

Execute `task-stage12b-plugin-skill-workflows` through the Story Loop. After implementation, run the
task verification commands, perform the required review, fix accepted findings, update planning
SQLite and this handoff, then ACP the step.
