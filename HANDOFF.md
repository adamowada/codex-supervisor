# HANDOFF.md

Last updated: 2026-05-27

This file is a compact resume snapshot only. Canonical queue state, completion records, worker
evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Current queue state: empty. `story-loop-status --json` reports no current AFK, HITL, or running
  task.
- Latest completed checkpoint: `plan-worker-controller-boundary-hardening-20260527` implemented
  the worker/controller boundary hardening fixes requested after the todo-list smoke tests.
- Durable changes now keep normal `codex_exec` workers read-only against planning/controller state,
  reject unsafe product-worker contracts pre-launch, preserve rejected Worker Result JSON as
  evidence, enforce review-promotion gates, require browser smoke evidence when task scope demands
  it, normalize worker backend names, and require explicit strict evidence mode for full-AFK
  preflight.
- Earlier completed checkpoint: `plan-subagent-spawn-insight-20260527` recorded the durable lesson
  that full-history subagent forks cannot also override role; use explicit explorer agents with
  self-contained prompts instead. The insight lives in
  `insights/workflow-patterns.md#full-history-subagent-forks-cannot-override-role`.

## Next Action

No active local queue task.
