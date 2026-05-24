# Handoff

## Current State

Repository: `codex-supervisor`

This file is a mutable fresh-thread snapshot. Treat `plans/planning.sqlite3` as canonical for active
plans, current task, task status, worker runs, progress, and execution order. Run these before using
this handoff:

```sh
git status --short --branch
git rev-parse --short HEAD
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B -m codex_supervisor.cli task-current --json
uv run --no-sync python -B -m codex_supervisor.cli plan-summary --current-queue
```

As of this snapshot, the expected queue state is `ready` with current task
`task-stage6-codex-exec-backend-design` under active plan `plan-stage6-codex-exec-backend`. If the
database reports anything else, trust the database and call this handoff stale. The expected
allowed-path contract for that design task is documentation-only: `ARCHITECTURE.md`, `CONTRACTS.md`,
`ROADMAP.md`, and `PLANS.md`.

Recent completed ACP checkpoints:

- `3e6d1d3`: aligned fresh-thread planning bootstrap commands and handoff guidance.
- `200d027`: hardened exact task claiming, Story Loop queue snapshots, completed-plan criteria, and
  worker-result/attribution skill contracts.

The latest full local gate passed after this handoff and SQLite cleanup with:

```sh
uv run --no-sync python -B scripts/verify.py
```

That run covered 229 tests, Ruff, format check, mypy, CLI smoke checks, file justification, public
hygiene, planning integrity, skill inventory, source inventory, protected locks, and
`uv lock --check`.

## Next Session Prompt

```text
Use the codex-supervisor skill. If it is not listed in the active Codex session, read
.agents/skills/codex-supervisor/SKILL.md directly and follow it as the repo-local fallback.

Read README.md, AGENTS.md, PLANS.md, and insights/README.md. Do not read mutable HANDOFF.md or
historical audit files before inspecting the live queue.

Inspect plans/planning.sqlite3 through typed helpers:

uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B -m codex_supervisor.cli task-current --json
uv run --no-sync python -B -m codex_supervisor.cli plan-summary --current-queue

Use story-loop-status as the queue state machine. Use task-current only as the executable AFK
selector. If queue_state is hitl or running, inspect current_task_id with task-show.

If queue_state is ready, render the Goal Contract for the selected task before editing. Until the
Stage 6 Codex Exec backend exists, worker_backend=codex_exec is a planned backend label; execute in
the supervised thread, an explicit worktree, or a hand-authored fresh-context worker prompt.
```

## Active Caveats

- Do not vendor ignored `sources/` clones.
- Keep the project cross-platform.
- Treat local `~/.codex` databases as read-only observational inputs.
- Treat native Codex Goals as execution contracts, not as the canonical queue. If `/goal` is not
  visible on a Goals-capable build, official Codex docs say to enable `[features] goals = true` in
  `${CODEX_HOME}/config.toml` or run `codex features enable goals`; do this only when Goal Mode setup
  and writes to that Codex home are in scope.
- Update protected source-of-truth hashes after intentional edits to locked files.
