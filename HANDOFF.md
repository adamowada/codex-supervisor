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

## Next Action

Continue with Stage 2 from `ROADMAP.md`: implement the policy core that maps task intent to
assurance requirements.
