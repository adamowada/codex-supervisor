---
name: story-loop-runner
description: Run a Ralph-inspired one-story fresh-context execution loop for Codex-supervisor. Use when executing a queue of AFK vertical slices, continuing until ready tasks pass, coordinating repeated Codex workers, or applying one-story-per-iteration discipline with checks, review, commits, progress records, and stop conditions.
---

# Story Loop Runner

Run one vertical slice per iteration. The loop is inspired by Ralph, but planning SQLite is the queue and Goal Contracts are the execution contract.

## Loop

1. Read locked docs, planning SQLite, handoff, and relevant insights.
2. Pick the highest-priority ready `AFK` task with unblocked dependencies.
3. Draft or load its Goal Contract with `goal-contract-drafter`.
4. Create an isolated worktree or fresh-context worker prompt.
5. Execute only that story.
6. Run the task verification commands.
7. Run review when required.
8. If checks pass, record progress, artifacts, changed files, and follow-up tasks.
9. If checks fail, classify with `failure-loop-triage` or `ci-repair-loop`.
10. Repeat only if another ready task exists and the user or automation policy allows it.

## Completion Rules

- Mark a story complete only when acceptance criteria pass with evidence.
- Do not widen scope to adjacent stories.
- Do not run two writers on the same files without an explicit coordination plan.
- Keep learnings durable: planning SQLite for state, `insights/` for reusable knowledge, source docs for stable doctrine.
- Use commits, worker results, and artifact links as memory; do not rely on chat continuity.

## Stop Conditions

Stop and report when:

- no ready `AFK` task remains;
- the next task is `HITL`;
- durable sources conflict;
- verification repeatedly fails and the failure class is unknown;
- work would exceed scope, budget, or allowed paths;
- publishing or production action needs explicit authorization.

## Ralph Mapping

- Ralph `prd.json` maps to planning SQLite tasks.
- Ralph `passes: true` maps to verified task completion.
- Ralph `progress.txt` maps to plan progress events plus `insights/` updates.
- Ralph one fresh agent per iteration maps to fresh-context Codex workers.
- Ralph quality checks map to verification commands plus review gates.
