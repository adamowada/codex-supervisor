from __future__ import annotations

from codex_supervisor.planning import SupervisorTaskSummaryRecord, WorkerRunRecord
from codex_supervisor.queue_selection import (
    executable_afk_tasks,
    ready_task_nonclaimable_reason,
    select_next_executable_afk_task,
    story_loop_status_required_message,
)


def test_select_next_executable_afk_task_skips_hitl_and_blocked_tasks() -> None:
    blocked = _task("task-blocked", blocked_by=["task-gate"])
    hitl = _task("task-hitl", task_type="HITL")
    ready = _task("task-ready")
    tasks = (_task("task-gate", status="running"), blocked, hitl, ready)

    assert select_next_executable_afk_task(tasks, ()) == ready
    assert executable_afk_tasks(tasks, ()) == (ready,)


def test_select_next_executable_afk_task_skips_active_worker_runs() -> None:
    ready = _task("task-ready")
    worker_run = WorkerRunRecord(
        worker_run_id="run-ready",
        task_id=ready.task_id,
        backend="codex_exec",
        status="running",
    )

    assert select_next_executable_afk_task((ready,), (worker_run,)) is None
    assert ready_task_nonclaimable_reason(ready, (ready,), (worker_run,)) == "worker-run-active"


def test_ready_task_nonclaimable_reason_names_all_reasons() -> None:
    task = _task(
        "task-waiting",
        plan_status="blocked",
        task_type="HITL",
        blocked_by=["task-gate"],
    )

    assert ready_task_nonclaimable_reason(task, (_task("task-gate"), task), ()) == (
        "plan-blocked;hitl;blocked-by=task-gate"
    )


def test_story_loop_status_required_message_names_requested_selector() -> None:
    assert "task-next-afk requires prior story-loop-status" in (
        story_loop_status_required_message("task-next-afk")
    )


def _task(
    task_id: str,
    *,
    plan_status: str = "active",
    task_type: str = "AFK",
    status: str = "ready",
    blocked_by: list[str] | None = None,
) -> SupervisorTaskSummaryRecord:
    return SupervisorTaskSummaryRecord(
        task_id=task_id,
        plan_id="plan-test",
        plan_title="Plan",
        plan_status=plan_status,
        plan_priority=100,
        title=task_id,
        goal="Do the task.",
        task_type=task_type,
        status=status,
        scope={},
        out_of_scope={},
        acceptance_criteria=["Criterion."],
        verification_commands=["uv run --no-sync python -B scripts/verify.py"],
        allowed_paths=["src/**"],
        blocked_by=blocked_by or [],
        worker_backend="codex_exec",
        review_required=False,
        created_at="2026-05-27T00:00:00Z",
        updated_at="2026-05-27T00:00:00Z",
    )
