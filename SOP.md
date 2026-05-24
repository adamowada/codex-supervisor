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
10. Draft Goal Contract fields for each `AFK` slice.
11. Persist all durable planning state to SQLite.

## Worker Execution

For every AFK task:

1. Create an isolated worktree.
2. Render a Goal Contract and task prompt from source-of-truth docs and task row.
3. Launch a fresh-context Codex worker.
4. Execute one vertical slice/story only.
5. Capture raw logs and structured result.
6. Run deterministic checks.
7. Run automated review.
8. Repair or mark blocked.
9. Link artifacts, learnings, and progress events.

The loop may continue to the next ready task only after the current story has evidence for completion
or a recorded blocked state.

## Control Tower Reconciliation

On a recurring schedule or before a major supervision session:

1. Read local Codex state databases in read-only mode.
2. Summarize active and stale threads by project.
3. Identify orphaned handoffs, abandoned worktrees, repeated failures, and high-fanout thread trees.
4. Compare local Codex observations with `plans/planning.sqlite3`.
5. Create proposed plan links, progress events, AFK tasks, or HITL tasks.
6. Suggest Codex automations through official automation tooling when recurring checks would help.
7. Record durable lessons in `insights/` when repeated patterns appear.

Do not write directly to Codex internal SQLite databases. Use planning SQLite as the canonical queue
and official Codex automation tooling as the scheduling surface.

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
