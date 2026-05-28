# HANDOFF.md

Last updated: 2026-05-28

This is the current resume snapshot only.

## Current State

The repository is on `feature/simplification-refactor`.

The active direction is ruthless simplification:

- old source-of-truth doctrine has been rewritten;
- old repo-local skills have been deleted and replaced by one small supervisor skill;
- packaged Desktop plugin files have been deleted from the active surface;
- historical insight files have been deleted and replaced by current simplification lessons;
- old tests have been deleted as acceptance authority;
- CI now targets the simplified contract;
- `plans/planning.sqlite3` has been reset to the fresh schema from `PLANS.md`.

The fresh planning model is:

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

Assurance levels are `low`, `medium`, and `high`.

## Next Action

Continue with Stage 2 from `ROADMAP.md`: rebuild core policy in code so task intent maps to
assurance requirements without reintroducing mode-specific branches.

Do not resurrect old tests, plugin packaging, MCP tools, historical planning tables, or skill-router
workflows unless the simplified core explicitly earns them back.
