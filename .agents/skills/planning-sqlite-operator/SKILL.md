---
name: planning-sqlite-operator
description: Operate codex-supervisor planning SQLite safely through typed helpers. Use when creating, updating, inspecting, or verifying plans, milestones, decisions, progress events, tasks, or worker-run records.
---

# Planning SQLite Operator

Use `plans/planning.sqlite3` for operational planning state.

## Rules

- Use `codex_supervisor.planning` helpers.
- Do not write ad hoc SQL unless adding a typed helper in the same change.
- Record decisions before or during meaningful tradeoffs.
- Record progress when work starts, completes, blocks, unblocks, verifies, or hands off.
- Keep markdown source-of-truth docs human-facing; do not hide stable doctrine only in SQLite.

## Commands

```sh
uv run codex-supervisor plan-init
uv run codex-supervisor plan-list
```
