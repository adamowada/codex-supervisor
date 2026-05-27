# HANDOFF.md

Last updated: 2026-05-27

This file is a compact resume snapshot only. Canonical queue state, completion records, worker
evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Current queue state: HITL. `story-loop-status --json` selects
  `task-review-review-required-hitl-gap-20260527`.
- User accepted the todo-list-test-5 smoke recommendations and selected full spawned-project
  integrity checker parity. Decision recorded as
  `decision-todo-test-5-smoke-repairs-20260527`; implementation start recorded as
  `progress-todo-test-5-smoke-repairs-start-20260527`.
- Local todo smoke app listeners were stopped before implementation. Ports 4000, 4001, 5173, 5174,
  and 27017 were clear after stopping Node/Vite, Docker MongoDB, and the local MongoDB listener.
- Current implementation expands the review-gating repair: directory allowed paths canonicalize to
  `path/**`; common Node verification commands are safe; clean review-required work gets a
  separate AFK `codex_review` task; `review-result-promote` provides typed promotion for reviewed
  `needs_review` output; completed worker runs with raw evidence metadata must preserve indexed
  evidence paths; completed queues fail stale review handoffs; supervisor-managed spawned projects
  copy the full main planning integrity checker and generated `AGENTS.md`/`PLANS.md` steer those
  rules.
- Verification passed. `uv run --no-sync python -B scripts/verify.py` completed successfully with
  578 tests plus Ruff, formatting, mypy, CLI help, planning integrity, public hygiene, source/skill
  inventory, protected-file checks, and `uv lock --check`.
- Durable lessons added to `insights/workflow-patterns.md`: spawned project smoke gates need
  main-checker parity, and review promotion must be typed.
- Planning progress `progress-todo-test-5-smoke-repairs-verified-20260527` records the verification
  result.

## Next Action

ACP all unstaged changes as requested. Keep the source task under review until the final review
checkpoint is accepted.
