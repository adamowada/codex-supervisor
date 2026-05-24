---
name: story-loop-runner
description: Run Codex-supervisor one-story discipline manually in the current supervised thread or prepare self-contained worker prompts until the Stage 6 backend exists. Use when executing one AFK vertical slice, applying checks/review/progress records, or deciding whether another Story Loop iteration is allowed.
---

# Story Loop Runner

Run one vertical slice per iteration. Planning SQLite is the queue and Goal Contracts are the
execution contract.

If the current user turn is read-only, readonly, review-only, audit-only, no-edits, or no-mutation,
run orientation commands only. Report the selected queue state, current task ID, blockers, and
proposed next mutation commands; do not claim tasks, update SQLite, edit files, create worktrees, or
start a worker.

In strict read-only, readonly, review-only, audit-only, no-edits, no-mutation, or unsynced
environments, run `uv run` commands only when dependencies are already present. Otherwise use
existing command output, Git state, or read-only SQLite inspection and report that typed CLI
orientation needs dependency setup.

## Loop

1. Read the minimum stable orientation docs and current git state; do not use mutable handoff prose
   as queue authority.
2. Run `uv run codex-supervisor story-loop-status --json` and branch on top-level `queue_state`.
   The default view includes active and blocked current-queue plans; use `--all` only when
   historical completed, abandoned, or superseded plans are in scope.
3. After live queue state is known, read `HANDOFF.md` only as task-relevant mutable context.
4. If `queue_state` is `running`, run `uv run codex-supervisor task-show <current_task_id> --json`,
   report the claimed task, inspect worker-run state, and stop unless the task contract says to
   monitor or repair it.
5. If `queue_state` is `hitl`, run `uv run codex-supervisor task-show <current_task_id> --json`,
   report the human checkpoint, and stop.
6. If `queue_state` is `blocked`, report blockers and stop unless the active task is explicitly a
   repair task.
7. If `queue_state` is `completed` or `empty`, report that no executable AFK task remains.
8. If `queue_state` is `ready`, run `uv run codex-supervisor task-current --json` and execute only
   the returned task.
9. Claim the task with `uv run codex-supervisor task-claim --worker-run-id <id> --json` before
   handing it to a worker, unless you are intentionally executing it inline in this supervised
   thread.
10. Draft or load its Goal Contract with `goal-contract-drafter`; if using native Codex Goals, apply
   that skill's Goal Mode preflight and `${CODEX_HOME}/config.toml` fallback before relying on
   `/goal`.
11. Create an isolated worktree or fresh-context worker prompt.
12. Execute only that story.
13. Run the task verification commands.
14. Run review when required.
15. If checks pass, write or link a repo-local JSON worker result that satisfies
   `../worker-result-contract.md`: set the worker run `result_path` to that exact JSON file, include
   the same path in `artifacts`, link it through `plan_artifact_links` with relationship
   `worker-result`, and keep `changed_files` focused on implementation or durable-documentation
   paths covered by task `allowed_paths`.
16. Record progress, artifacts, changed files, and follow-up tasks.
17. If checks fail, classify with `failure-loop-triage` or `ci-repair-loop`.
18. Repeat only if another ready task exists and the user or official host automation tooling
    allows it. Otherwise draft or suggest the next run; do not claim automation was created.

Until the Stage 6 Codex Exec backend exists, do not imply that `codex-supervisor` can launch workers
itself. Execute the selected story in the current supervised thread, in a manually created worktree,
or by handing a self-contained worker prompt to Codex explicitly. Record any manual execution as a
worker run or progress event when the planning helper surface supports it.

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

## Result Contract

Report the selected task ID, worker/run ID, changed files, commands run, verification evidence,
planning rows updated, artifacts linked, residual risks, and the next ready AFK/HITL task.
