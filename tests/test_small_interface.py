from __future__ import annotations

from pathlib import Path

from planning_db_factory import make_planning_db

from codex_supervisor.small_interface import attempt_transition, queue_next


def test_queue_next_returns_ready_task_and_transition_hint(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)

    result = queue_next(db_path)

    assert result.task is not None
    assert result.task["task_id"] == "task-1"
    assert result.next_transition == "attempt-transition --status running"


def test_attempt_transition_runs_and_accepts_medium_task(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)

    running = attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        executor="manual",
        status="running",
        summary="Running task.",
    )
    completed = attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        status="succeeded",
        summary="Task satisfied.",
        checks=("pytest tests/test_small_interface.py",),
        artifacts=("src/codex_supervisor/small_interface.py",),
        acceptance_results={"Acceptance criterion": True},
    )

    assert running.task_status == "running"
    assert completed.task_status == "done"
    assert completed.acceptance is not None
    assert completed.acceptance["accepted"] is True
    assert completed.evidence is not None
    assert completed.evidence["attempt_id"] == "attempt-1"


def test_attempt_transition_blocks_when_acceptance_is_missing(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        executor="manual",
        status="running",
        summary="Running task.",
    )

    completed = attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        status="succeeded",
        summary="Task lacks evidence.",
    )

    assert completed.task_status == "blocked"
    assert completed.acceptance is not None
    assert completed.acceptance["accepted"] is False
