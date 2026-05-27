"""Story Loop queue selection helpers with explicit next-AFK vocabulary."""

from __future__ import annotations

from collections.abc import Iterable

from codex_supervisor.planning import (
    SupervisorTaskSummaryRecord,
    WorkerRunRecord,
    has_nonterminal_worker_run,
    is_executable_afk_task,
    missing_execution_contract_fields,
    unresolved_task_blockers,
)

NEXT_AFK_SELECTOR_COMMAND = "task-next-afk"
LEGACY_CURRENT_TASK_SELECTOR_COMMAND = "task-current"


def story_loop_status_required_message(command_name: str = NEXT_AFK_SELECTOR_COMMAND) -> str:
    """Return the guardrail message for next-AFK selector calls."""

    return (
        f"{command_name} requires prior story-loop-status inspection; run "
        "`uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json` "
        f"first, then rerun {command_name} with --after-story-loop-status."
    )


def select_next_executable_afk_task(
    tasks: Iterable[SupervisorTaskSummaryRecord],
    worker_runs: Iterable[WorkerRunRecord],
    *,
    all_tasks: Iterable[SupervisorTaskSummaryRecord] | None = None,
) -> SupervisorTaskSummaryRecord | None:
    """Return the next task that is actually claimable for AFK execution."""

    task_tuple = tuple(tasks)
    all_task_tuple = task_tuple if all_tasks is None else tuple(all_tasks)
    worker_run_tuple = tuple(worker_runs)
    return next(
        (
            task
            for task in task_tuple
            if is_executable_afk_task(task, all_task_tuple, worker_run_tuple)
        ),
        None,
    )


def executable_afk_tasks(
    tasks: Iterable[SupervisorTaskSummaryRecord],
    worker_runs: Iterable[WorkerRunRecord],
    *,
    all_tasks: Iterable[SupervisorTaskSummaryRecord] | None = None,
) -> tuple[SupervisorTaskSummaryRecord, ...]:
    """Return all tasks that are currently claimable for AFK execution."""

    task_tuple = tuple(tasks)
    all_task_tuple = task_tuple if all_tasks is None else tuple(all_tasks)
    worker_run_tuple = tuple(worker_runs)
    return tuple(
        task
        for task in task_tuple
        if is_executable_afk_task(task, all_task_tuple, worker_run_tuple)
    )


def ready_task_nonclaimable_reason(
    task: SupervisorTaskSummaryRecord,
    all_tasks: Iterable[SupervisorTaskSummaryRecord],
    worker_runs: Iterable[WorkerRunRecord],
) -> str:
    """Explain why a ready task is not the next executable AFK task."""

    all_task_tuple = tuple(all_tasks)
    worker_run_tuple = tuple(worker_runs)
    reasons: list[str] = []
    if task.plan_status != "active":
        reasons.append(f"plan-{task.plan_status}")
    if task.task_type != "AFK":
        reasons.append("hitl")
    blockers = unresolved_task_blockers(task, all_task_tuple)
    if blockers:
        reasons.append("blocked-by=" + ",".join(blockers))
    if task.task_type == "AFK":
        missing_fields = missing_execution_contract_fields(task)
        if missing_fields:
            reasons.append("missing=" + ",".join(missing_fields))
    if has_nonterminal_worker_run(task.task_id, worker_run_tuple):
        reasons.append("worker-run-active")
    return ";".join(reasons) if reasons else "unblocked"
