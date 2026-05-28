# HANDOFF.md

Last updated: 2026-05-28

This file is a compact resume snapshot only. Canonical queue state, completion records, worker
evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Current queue state: empty. `story-loop-status --json` reports no current AFK, HITL, or running
  task after `plan-ci-linux-mypy-windll-20260528` was completed.
- Latest completed checkpoint: `plan-ci-linux-mypy-windll-20260528` repaired GitHub Actions Verify
  run `26552849566`, where Linux mypy rejected direct `ctypes.windll` access in
  `src/codex_supervisor/story_loop.py`. Implementation commit:
  `9aed4a031b04634fdcb5711403cac24113176ca0`.
- Previous completed checkpoint: `plan-supervisor-worker-boundary-cleanup-20260528` recorded the
  todo-list-test-14 RCA, implemented project-aware optional attribution context, shared
  product-worker/controller-owned path policy, planned-vs-actual evidence metadata, and
  product-worker prompt/runtime boundary guidance. Implementation commit:
  `7a11f9f6bde52f5e0c86764eb35e036e4987f766`.
- Small live Story Loop smoke used temporary real git/planning/worktree state with a deterministic
  tiny backend. It proved private product workers do not receive absent `ATTRIBUTIONS.md`, preclaim
  worker metadata uses `planned_evidence_paths` instead of actual raw evidence claims, and
  controller-owned product paths fail closed before worktree creation.
- Earlier completed checkpoint: `plan-worker-controller-boundary-hardening-20260527` implemented
  the worker/controller boundary hardening fixes requested after the earlier todo-list smoke tests.
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
