"""Small lifecycle policy helpers for the durable work model."""

from __future__ import annotations

from codex_supervisor.attempts import RunAttemptStatus


def terminal_task_status(
    *,
    attempt_status: RunAttemptStatus,
    accepted: bool,
) -> str:
    """Return the task state after terminal evidence is evaluated."""

    if attempt_status is RunAttemptStatus.SUCCEEDED and accepted:
        return "done"
    return "blocked"


def should_reactivate_plan_for_new_task(
    *,
    plan_status: str,
    has_durable_completion: bool,
) -> bool:
    """Return whether task creation should reopen an existing plan."""

    return plan_status == "blocked" or (
        plan_status == "done" and not has_durable_completion
    )


def should_prepare_blocked_task_for_attempt(
    *,
    plan_status: str,
    task_status: str,
) -> bool:
    """Return whether attempt start may move blocked plan/task back to open work."""

    return plan_status == "blocked" and task_status == "blocked"
