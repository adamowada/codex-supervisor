# HANDOFF.md

Last updated: 2026-05-25 02:30 PDT

This file is a compact handoff snapshot only. Canonical queue state, completion records, imported
legacy evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Active thread objective: major repo hygiene cleanup for completion-record storage.
- Planning database is on schema version 5.
- Legacy JSON completion records have been imported into SQLite: 35 result records and 42 run links.
- Legacy HANDOFF section content has been imported into SQLite development-log entries.
- `worker-results/` has been removed from the working tree after import.
- Source-of-truth docs, protected hashes, code paths, tests, and hygiene checks have been updated
  for SQLite-only completion storage.
- Full pytest is passing: `424 passed`.
- Remaining cleanup work: stage deletions and edits, rerun publication-ready verification, then ACP.

## Queue State

- Current canonical queue state: ready.
- Active plan: `plan-stage11-mcp-server` (`Stage 11 MCP Server`, priority 79).
- Current AFK task: `task-stage11b-mcp-stdio-transport`.
- Stage 11B goal: add a stdlib-only MCP stdio JSON-RPC transport around the Stage 11A read-only
  dispatcher without mutating planning state or launching workers.
- Stage 11A is completed and linked to DB-backed result id
  `worker-result-stage11a-mcp-readonly-tools-worker-result`.

## Resume Commands

```sh
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B -m codex_supervisor.cli plan-summary --current-queue
uv run --no-sync python -B -m codex_supervisor.cli worker-result-list --json
uv run --no-sync python -B scripts/check_planning_integrity.py
```

## Hygiene Verification Targets

- No `worker-results/` directory or tracked JSON completion artifacts.
- No archive, dump, backup, or migration-output artifacts in the repo.
- `HANDOFF.md` stays below 180 lines and contains only current handoff context.
- `insights/` remains markdown-only durable learning.
- Completion records and imported legacy evidence live in `plans/planning.sqlite3`.
- Protected source-of-truth hashes are refreshed after intentional doc edits.

## Next Action

Stage all intended changes with `git add -A`, rerun the publication-ready checks against the staged
tree, then commit and push `Clean up completion record hygiene`.
