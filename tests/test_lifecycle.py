from __future__ import annotations

from codex_supervisor.attempts import RunAttemptStatus
from codex_supervisor.lifecycle import (
    should_prepare_blocked_task_for_attempt,
    should_reactivate_plan_for_new_task,
    terminal_task_status,
)


def test_terminal_task_status_is_done_only_for_accepted_success() -> None:
    assert (
        terminal_task_status(
            attempt_status=RunAttemptStatus.SUCCEEDED,
            accepted=True,
        )
        == "done"
    )
    assert (
        terminal_task_status(
            attempt_status=RunAttemptStatus.SUCCEEDED,
            accepted=False,
        )
        == "blocked"
    )
    assert (
        terminal_task_status(
            attempt_status=RunAttemptStatus.FAILED,
            accepted=True,
        )
        == "blocked"
    )


def test_plan_reactivation_policy_has_one_path() -> None:
    assert should_reactivate_plan_for_new_task(
        plan_status="blocked",
        has_durable_completion=False,
    )
    assert should_reactivate_plan_for_new_task(
        plan_status="done",
        has_durable_completion=False,
    )
    assert not should_reactivate_plan_for_new_task(
        plan_status="done",
        has_durable_completion=True,
    )
    assert not should_reactivate_plan_for_new_task(
        plan_status="active",
        has_durable_completion=False,
    )


def test_only_blocked_task_on_blocked_plan_is_prepared_for_attempt() -> None:
    assert should_prepare_blocked_task_for_attempt(
        plan_status="blocked",
        task_status="blocked",
    )
    assert not should_prepare_blocked_task_for_attempt(
        plan_status="active",
        task_status="blocked",
    )
    assert not should_prepare_blocked_task_for_attempt(
        plan_status="blocked",
        task_status="ready",
    )
