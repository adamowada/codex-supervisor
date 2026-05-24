# Standard Operating Procedure

This SOP is the default structure for new projects spawned by `codex-supervisor`.

## New Project Bootstrap

Every non-trivial production-intended spawned project should start with this base scaffold:

```text
README.md
AGENTS.md
PLANS.md
ARCHITECTURE.md
CONTRACTS.md
ROADMAP.md
TESTING.md
DECISIONS.md
SOP.md
HANDOFF.md
.gitignore
.gitattributes
scripts/verify.py
insights/README.md
```

Add supervisor-managed surfaces when the project needs unattended workers, protected source-of-truth
checks, or a tracked operational queue:

```text
plans/planning.sqlite3
scripts/print_protected_hashes.py
scripts/check_protected_files.py
scripts/check_file_justification.py
scripts/check_planning_integrity.py
```

Add publication-ready surfaces when the project will be public or shared beyond the local machine:

```text
LICENSE
ATTRIBUTIONS.md
scripts/check_public_repo_hygiene.py
```

Add optional skill/source modules only when the project actually needs repo-local skills or OSS
study sources:

```text
scripts/check_skill_inventory.py
scripts/check_source_inventory.py
.agents/skills/
sources/README.md
```

Small throwaway prototypes may use a lighter structure, but the supervisor should prefer the base
shape for production-intended apps and avoid creating empty optional surfaces.

## Planning Session

Before code changes:

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
3. Run the worker-launch preflight: `codex --version`, intended `CODEX_HOME`, `/goal` visibility, and
   feature enablement when needed. Treat `${CODEX_HOME}/config.toml` edits and
   `codex features enable goals` as setup mutations; use them only when Goal Mode setup is
   explicitly in scope and writes to the intended Codex home are allowed. Record resolved Codex
   executable, version output, config path, feature state, native-goal support for the selected
   backend, and fallback decision in worker metadata.
4. Launch a fresh-context Codex worker through the configured backend. If the environment cannot
   launch the selected backend, record the blocker or create a HITL/manual-run task instead of
   treating supervised-thread work as unattended worker execution.
5. If native Goals are unavailable, include the Goal Contract in the worker prompt and do not write
   Codex internal goal databases.
6. Execute one vertical slice/story only.
7. Capture raw logs and structured result.
8. Run deterministic checks.
9. Run automated review.
10. Repair or mark blocked.
11. Link artifacts, learnings, and progress events.

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
