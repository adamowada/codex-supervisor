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

Continue with Stage 4 from `ROADMAP.md`: add one inspection command and one mutation command over
the compact task, attempt, evidence, and acceptance model.

Planning task:

- `task-rebuild-small-interface-20260528`
