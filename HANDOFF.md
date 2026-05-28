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

Continue with Stage 2 from `ROADMAP.md`: implement the policy core that maps task intent to
assurance requirements.

Planning task:

- `task-rebuild-policy-core-20260528`
