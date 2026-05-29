# HANDOFF.md

Last updated: 2026-05-29

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
it uses explicit `low`, `medium`, or `high` task assurance, defines evidence requirements, and
evaluates task, attempt, and evidence records without importing CLI, MCP, plugin, worker, or SQLite
layers. Assurance is not inferred from prose.

Stage 3 is implemented in `src/codex_supervisor/attempts.py` and
`src/codex_supervisor/attempt_store.py`. Run attempts now have a pure status model, compact SQLite
helpers, evidence attachment, and planning integrity checks for attempt/evidence relationships.

Stage 4 is implemented in `src/codex_supervisor/small_interface.py` and exposed through two active
operational CLI commands: `queue-next` for inspection and `attempt-transition` for mutation.
`plan-init` exists only to create the compact schema. `queue-next` has one meaning: the next ready
task in the active queue. `attempt-transition` is the write path for attempts, evidence, and
acceptance.

Stage 5 is a boundary, not an active worker implementation. Future Codex workers are represented as
attempt executors, but worker prompt builders, fake workers, and live launchers stay out of active
product code until a worker adapter operation is selected.

Stage 6 is implemented in `src/codex_supervisor/adapter_contracts.py` and the read-only MCP
`codex_supervisor.queue_next` operation. Adapter growth is declaration-first: an operation must name
task intent, attempt behavior, evidence behavior, assurance levels, acceptance behavior, state flow,
and operator value before activation.

The live surface now matches the compact contract. `src/codex_supervisor/cli.py` exposes three
commands: `plan-init`, `queue-next`, and `attempt-transition`. `src/codex_supervisor/mcp_server.py`
exposes one in-process tool: `codex_supervisor.queue_next`. The old operation registry, stdio MCP
transport, broad planning inspection commands, and fake worker scaffold have been removed.

The package has been cut down to the compact implementation modules. Attempt transitions validate
task ownership, planning integrity checks open work per active plan, and the attempt store prevents
multiple non-terminal attempts for a task. Surviving queue read SQL lives in `AttemptStore`.

Repo-local skills now include:

- `codex-supervisor`
- `improve-codebase-architecture`
- `reduce-codebase-complexity`

`reduce-codebase-complexity` includes a front-door ruthlessness calibration step. It asks for
deletion tolerance, mutation scope, and sacred constraints only when those are unclear, then treats
the answer as run posture rather than another persistent mode axis.

## Roadmap

1. Stage 1, Foundation Contract: align docs, planning SQLite, skill guidance, CI, insights, handoff,
   and protected hashes around the compact model.
2. Stage 2, Policy Core: implement assurance and acceptance policy in code.
3. Stage 3, Execution Attempts: represent manual, shell, review, and future Codex work as one
   attempt shape.
4. Stage 4, Small Interface: add one inspection command and one mutation command.
5. Stage 5, Worker Boundary: keep future workers inside the attempt model without active scaffold.
6. Stage 6, Interface Growth: add larger adapters one operation at a time.

## Next Action

All roadmap stages, compact contract repair, live-surface simplification, and repo-local
complexity-reduction skill work, including calibration, are complete. The related plans are marked
`done` in `plans/planning.sqlite3`.

Planning task:

- none
