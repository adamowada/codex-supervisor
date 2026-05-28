# HANDOFF.md

Last updated: 2026-05-28

This is the current resume snapshot.

## Current State

Branch: `feature/simplification-refactor`

Current model:

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

Current assurance levels:

- `low`
- `medium`
- `high`

Active planning database:

- `meta`
- `plans`
- `tasks`
- `attempts`
- `evidence_bundles`
- `decisions`

Ignored local cleanup is complete. `.venv/` remains for local development.

Stage 2 is implemented in `src/codex_supervisor/policy.py`. Assurance policy is pure core code:
it maps task intent to `low`, `medium`, or `high`, defines evidence requirements, and evaluates task,
attempt, and evidence records without importing CLI, MCP, plugin, worker, or SQLite layers.

Stage 3 is implemented in `src/codex_supervisor/attempts.py` and
`src/codex_supervisor/attempt_store.py`. Run attempts now have a pure status model, compact SQLite
helpers, evidence attachment, and planning integrity checks for attempt/evidence relationships.

Stage 4 is implemented in `src/codex_supervisor/small_interface.py` and exposed through two CLI
commands: `queue-next` for inspection and `attempt-transition` for mutation. The commands use the
compact task, attempt, evidence, and acceptance path.

Stage 5 is implemented in `src/codex_supervisor/worker_attempts.py`. Worker prompts are generated
from task intent plus assurance policy, fake Codex worker execution records ordinary attempts and
evidence bundles, high-assurance worker results are policy-gated, and live execution has a bounded
verification plan.

Stage 6 is implemented in `src/codex_supervisor/adapter_contracts.py` and the read-only MCP
`codex_supervisor.queue_next` operation. Adapter growth is now declaration-first: an operation must
name task intent, attempt behavior, evidence behavior, assurance levels, acceptance behavior, state
flow, and operator value before activation.

The compact contract repair is complete. `plan-init`, `plan-list`, `plan-summary`, `task-list`, and
`task-show` now use the compact planning schema. Attempt transitions validate task ownership,
workers fail closed with blocker evidence, planning integrity checks open work per active plan, and
the attempt store prevents multiple non-terminal attempts for a task.

## Roadmap

1. Stage 1, Foundation Contract: align docs, planning SQLite, skill guidance, CI, insights, handoff,
   and protected hashes around the compact model.
2. Stage 2, Policy Core: implement assurance and acceptance policy in code.
3. Stage 3, Execution Attempts: represent manual, shell, review, and future Codex work as one
   attempt shape.
4. Stage 4, Small Interface: add one inspection command and one mutation command.
5. Stage 5, Worker Integration: connect fresh-context Codex workers as attempt executors.
6. Stage 6, Interface Growth: add larger adapters one operation at a time.

## Next Action

All roadmap stages and the compact contract repair are complete. The simplification and repair plans
are marked `done` in `plans/planning.sqlite3`.

Planning task:

- none
