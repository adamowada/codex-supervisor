---
name: story-loop-runner
description: Run Codex-supervisor one-story discipline for one AFK vertical slice. Use when claiming or executing a queued story, preparing a worker prompt, applying checks/review/progress records, or deciding whether another Story Loop iteration is allowed.
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
2. Run `uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json` and branch on
   top-level `queue_state`. The default view includes active and blocked current-queue plans; use
   `--all` only when historical completed, abandoned, or superseded plans are in scope.
3. After live queue state is known, read `HANDOFF.md` only as task-relevant mutable context.
4. If `queue_state` is `running`, run
   `uv run --no-sync python -B -m codex_supervisor.cli task-show <current_task_id> --json`, report
   the claimed task, inspect worker-run state, and stop unless the task contract says to monitor or
   repair it.
5. If `queue_state` is `hitl`, run
   `uv run --no-sync python -B -m codex_supervisor.cli task-show <current_task_id> --json`, report
   the human checkpoint, and stop.
6. If `queue_state` is `blocked`, report blockers and stop unless the active task is explicitly a
   repair task.
7. If `queue_state` is `completed` or `empty`, report that no executable AFK task remains.
8. If `queue_state` is `ready`, run
   `uv run --no-sync python -B -m codex_supervisor.cli task-current --json` and execute only the
   returned task.
9. Claim the task with
   `uv run --no-sync python -B -m codex_supervisor.cli task-claim --task-id <task_id> --worker-run-id <id> --json`
   before handing it to a worker, unless you are intentionally executing it inline in this
   supervised thread. If the claim returns `null`, stop and refresh `story-loop-status`; another
   worker or thread changed the queue. If the returned `task.task_id` differs from the selected
   `<task_id>`, stop and treat that as queue drift.
10. Draft or load its Goal Contract with `goal-contract-drafter`; if using native Codex Goals, apply
   that skill's Goal Mode preflight and `${CODEX_HOME}/config.toml` fallback before relying on
   `/goal`.
11. Create an isolated worktree or fresh-context worker prompt.
12. Execute only that story.
13. Run the task verification commands.
14. Run review when required.
15. If checks pass, write a repo-local JSON worker result that satisfies
    `../worker-result-contract.md` and ingest it with `worker-run-status ... --result-path <json>`.
    The JSON path is a transient import source; after ingestion the durable completion authority is
    the DB-backed worker result record and the worker run `result_id`. Do not link ignored
    `runs/`, `artifacts/`, `worktrees/`, or `worker-results/` paths as publication artifacts. Link
    only tracked supporting docs, tracked durable reports, tracked insight/handoff anchors, or
    external URLs through `plan_artifact_links`.
16. Record progress, artifacts, changed files, and follow-up tasks.
17. If checks fail, classify with `failure-loop-triage` or `ci-repair-loop`.
18. Repeat only if another ready task exists and the user or official host automation tooling
    allows it. Otherwise draft or suggest the next run; do not claim automation was created.

Do not infer worker-launch capability from `ROADMAP.md` or stage order. Launch through the selected
backend only when the task contract, backend configuration, environment preflight, and planning
SQLite state support that path. If no launchable backend is available, execute the selected story in
the current supervised thread only when explicitly appropriate, create a manual worker prompt, or
record a blocker/HITL task. Record manual execution as a worker run or progress event when the
planning helper surface supports it, and never describe manual execution as automatic worker launch.

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
