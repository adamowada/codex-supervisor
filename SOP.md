# Standard Operating Procedure

This SOP is the default structure for new projects spawned by `codex-supervisor`.

## New Project Bootstrap

Every non-trivial spawned project should start with:

```text
README.md
AGENTS.md
PLANS.md
ARCHITECTURE.md
CONTRACTS.md
TESTING.md
DECISIONS.md
SOP.md
plans/planning.sqlite3
scripts/check_protected_files.py
insights/
.agents/skills/
```

Small throwaway prototypes may use a lighter structure, but the supervisor should prefer this shape
for production-intended apps.

## Planning Session

Before implementation:

1. Lock goals.
2. Lock non-goals.
3. Define users and workflows.
4. Define contracts.
5. Define acceptance criteria.
6. Define verification commands.
7. Identify risks.
8. Split work into vertical slices.
9. Mark each slice `AFK` or `HITL`.
10. Persist all durable planning state to SQLite.

## Worker Execution

For every AFK task:

1. Create an isolated worktree.
2. Render a task prompt from source-of-truth docs and task row.
3. Launch a fresh-context Codex worker.
4. Capture raw logs and structured result.
5. Run deterministic checks.
6. Run automated review.
7. Repair or mark blocked.
8. Link artifacts and progress events.

## Learning Loop

When a task fails, stalls, or requires repeated human correction:

1. Classify the failure.
2. Record the lesson in `insights/`.
3. Decide whether a skill should change.
4. Propose a skill update.
5. Test the skill against a small golden task.
6. Promote or reject the skill update.

## Human Role

The human should focus on:

- goals;
- tradeoffs;
- taste;
- risk tolerance;
- production decisions;
- reviewing final diffs and releases.

The supervisor should absorb:

- task splitting;
- context resets;
- worker launch;
- retry loops;
- check execution;
- review loops;
- handoffs;
- routine project bootstrap.
