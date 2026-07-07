from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from planning_db_factory import insert_task, make_planning_db

from codex_supervisor.small_interface import attempt_transition, queue_next, task_create


def test_queue_next_returns_ready_task_and_transition_hint(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)

    result = queue_next(db_path)

    assert result.task is not None
    assert result.task["task_id"] == "task-1"
    assert result.next_transition == "attempt-transition --status running"


def test_queue_next_surfaces_running_task_before_ready_work(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)
    insert_task(db_path, task_id="task-2", status="ready")
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-running",
        executor="manual",
        status="running",
        summary="Task 1 is already running.",
    )

    result = queue_next(db_path)

    assert result.task is not None
    assert result.task["task_id"] == "task-1"
    assert result.task["status"] == "running"
    assert result.active_attempt is not None
    assert result.active_attempt["attempt_id"] == "attempt-running"
    assert result.recovery_state["active_task_id"] == "task-1"
    assert result.recovery_state["active_attempt_id"] == "attempt-running"
    assert "running_attempt_liveness_missing" in result.recovery_state["warning_flags"]
    assert "git_summary" in result.recovery_state
    assert result.next_transition == "attempt-transition --status succeeded|failed|blocked"


def test_queue_next_surfaces_latest_acceptance_and_recovery_state(
    tmp_path: Path,
) -> None:
    db_path = make_planning_db(tmp_path)
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        executor="manual",
        status="running",
        summary="Running task.",
    )
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        status="failed",
        summary="Task failed.",
        checks=(
            "launch packet sha256: "
            "1111111111111111111111111111111111111111111111111111111111111111",
            "verifier intent sha256: "
            "2222222222222222222222222222222222222222222222222222222222222222",
        ),
        artifacts=("artifact",),
        acceptance_results={"Acceptance criterion": False},
    )
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-2",
        executor="manual",
        status="running",
        summary="Retry task.",
    )

    result = queue_next(db_path)

    assert result.latest_evidence is not None
    assert result.latest_evidence["attempt_id"] == "attempt-1"
    assert result.latest_evidence["digest"]["acceptance"]["accepted"] is False
    assert result.latest_acceptance is not None
    assert result.latest_acceptance["attempt_id"] == "attempt-1"
    assert result.latest_acceptance["result"] == "rejected"
    assert result.recovery_state["latest_evidence_bundle_id"] == result.latest_evidence[
        "bundle_id"
    ]
    assert result.recovery_state["latest_acceptance_decision_id"] == result.latest_acceptance[
        "decision_id"
    ]
    assert (
        result.recovery_state["launch_packet_sha256"]
        == "1111111111111111111111111111111111111111111111111111111111111111"
    )
    assert (
        result.recovery_state["verifier_intent_sha256"]
        == "2222222222222222222222222222222222222222222222222222222222222222"
    )
    assert result.recovery_state["latest_evidence_digest"] == result.latest_evidence["digest"]


def test_queue_next_surfaces_blocked_task_with_repair_hint(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        executor="manual",
        status="running",
        summary="Running task.",
    )
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        status="failed",
        summary="Task failed.",
        checks=("Failure recorded.",),
        artifacts=("artifact",),
        acceptance_results={"Acceptance criterion": False},
    )

    result = queue_next(db_path)

    assert result.plan is not None
    assert result.plan["status"] == "blocked"
    assert result.task is not None
    assert result.task["status"] == "blocked"
    assert result.latest_acceptance is not None
    assert result.latest_acceptance["result"] == "rejected"
    assert result.next_transition == "task-create --lineage repair_of=task-1"


def test_queue_next_warns_on_attempt_run_evidence_without_packet_or_metadata(
    tmp_path: Path,
) -> None:
    db_path = make_planning_db(tmp_path)
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        executor="worker-process",
        status="running",
        summary="Running worker.",
    )
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        status="failed",
        summary="Worker failed.",
        checks=("process exit code: 1",),
        artifacts=("README.md",),
        acceptance_results={"Acceptance criterion": False},
    )

    result = queue_next(db_path)

    assert "latest_evidence_launch_packet_missing" in result.recovery_state[
        "warning_flags"
    ]
    assert "latest_evidence_launch_metadata_missing" in result.recovery_state[
        "warning_flags"
    ]


def test_task_create_can_add_linked_repair_to_blocked_plan(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        executor="manual",
        status="running",
        summary="Running task.",
    )
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        status="failed",
        summary="Task failed.",
        checks=("Failure recorded.",),
        artifacts=("artifact",),
        acceptance_results={"Acceptance criterion": False},
    )

    created = task_create(
        db_path,
        plan_id="plan-1",
        plan_title="Plan",
        plan_goal="Goal",
        title="Repair task",
        intent="Repair the failed task.",
        assurance="medium",
        acceptance_criteria=("Repair evidence exists",),
        lineage=({"relation": "repair_of", "task_id": "task-1"},),
        task_id="task-repair",
    )
    queued = queue_next(db_path)

    assert created.plan["status"] == "active"
    assert created.task["lineage"] == [{"relation": "repair_of", "task_id": "task-1"}]
    assert queued.task is not None
    assert queued.task["task_id"] == "task-repair"


def test_queue_next_exposes_shipping_proof_lineage_as_final_proof(
    tmp_path: Path,
) -> None:
    db_path = make_planning_db(tmp_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("update tasks set status = 'blocked' where task_id = 'task-1'")
    task_create(
        db_path,
        plan_id="plan-1",
        plan_title="Plan",
        plan_goal="Goal",
        title="Shipping proof",
        intent="Prove task-1 is ready to ship.",
        assurance="high",
        acceptance_criteria=("Final proof exists",),
        lineage=({"relation": "shipping_proof_of", "task_id": "task-1"},),
        task_id="task-proof",
    )

    result = queue_next(db_path)

    assert result.task is not None
    assert result.task["task_id"] == "task-proof"
    assert result.recovery_state["final_proof"] == {
        "task_id": "task-proof",
        "proves_task_ids": ["task-1"],
        "status": "ready",
    }


def test_task_create_reports_stored_plan(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)

    result = task_create(
        db_path,
        plan_id="plan-1",
        plan_title="Different title",
        plan_goal="Different goal",
        title="New task",
        intent="Create durable task intent.",
        assurance="medium",
        acceptance_criteria=("Acceptance criterion",),
        task_id="task-new",
    )

    assert result.plan["title"] == "Plan"
    assert result.task["task_id"] == "task-new"
    assert result.task["lineage"] == []


def test_task_create_records_lineage_and_queue_next_surfaces_it(
    tmp_path: Path,
) -> None:
    db_path = make_planning_db(tmp_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("update tasks set status = 'blocked' where task_id = 'task-1'")

    created = task_create(
        db_path,
        plan_id="plan-1",
        plan_title="Plan",
        plan_goal="Goal",
        title="Review task",
        intent="Review the completed source task.",
        assurance="medium",
        acceptance_criteria=("Review evidence exists",),
        lineage=({"relation": "review_of", "task_id": "task-1"},),
        task_id="task-review",
    )
    queued = queue_next(db_path)

    assert created.task["lineage"] == [{"relation": "review_of", "task_id": "task-1"}]
    assert queued.task is not None
    assert queued.task["task_id"] == "task-review"
    assert queued.task["lineage"] == [{"relation": "review_of", "task_id": "task-1"}]


def test_task_create_rejects_unknown_lineage_relation(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)

    with pytest.raises(ValueError, match="lineage relation"):
        task_create(
            db_path,
            plan_id="plan-1",
            plan_title="Plan",
            plan_goal="Goal",
            title="Bad lineage",
            intent="Record unsupported lineage.",
            assurance="medium",
            acceptance_criteria=("Criterion",),
            lineage=({"relation": "cleanup_of", "task_id": "task-1"},),
            task_id="task-bad-lineage",
        )


def test_task_create_rejects_second_active_plan(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)

    with pytest.raises(ValueError, match="second active plan"):
        task_create(
            db_path,
            plan_id="plan-2",
            plan_title="Second plan",
            plan_goal="This would widen the active objective set.",
            title="New task",
            intent="Create another active objective.",
            assurance="medium",
            acceptance_criteria=("Acceptance criterion",),
            task_id="task-new",
        )


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

    with sqlite3.connect(db_path) as connection:
        plan_status = connection.execute(
            "select status from plans where plan_id = 'plan-1'"
        ).fetchone()[0]
    assert plan_status == "active"


def test_accepted_non_final_task_keeps_plan_open_for_linked_follow_up(
    tmp_path: Path,
) -> None:
    db_path = make_planning_db(tmp_path)
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        executor="manual",
        status="running",
        summary="Running task.",
    )
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        status="succeeded",
        summary="Task satisfied.",
        checks=("Focused check passed.",),
        artifacts=("artifact",),
        acceptance_results={"Acceptance criterion": True},
    )

    queued = queue_next(db_path)
    created = task_create(
        db_path,
        plan_id="plan-1",
        plan_title="Plan",
        plan_goal="Goal",
        title="Review task",
        intent="Review accepted work before final proof.",
        assurance="medium",
        acceptance_criteria=("Review evidence exists",),
        lineage=({"relation": "review_of", "task_id": "task-1"},),
        task_id="task-review",
    )
    review = queue_next(db_path)

    assert queued.plan is not None
    assert queued.plan["status"] == "active"
    assert queued.task is None
    assert queued.next_transition == (
        "active plan has no open task; suggested next: "
        "task-create --lineage review_of=task-1 | "
        "task-create --lineage repair_of=task-1 | "
        "task-create --lineage shipping_proof_of=task-1"
    )
    assert queued.recovery_state["active_plan_id"] == "plan-1"
    assert queued.recovery_state["active_task_id"] is None
    assert queued.recovery_state["suggested_lineage_targets"] == [
        {
            "task_id": "task-1",
            "status": "done",
            "suggested_relations": ["review_of", "repair_of", "shipping_proof_of"],
            "lineage": [],
        }
    ]
    assert created.plan["status"] == "active"
    assert review.task is not None
    assert review.task["task_id"] == "task-review"


def test_done_task_cannot_receive_another_normal_attempt(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        executor="manual",
        status="running",
        summary="Running task.",
    )
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        status="succeeded",
        summary="Task satisfied.",
        checks=("Focused check passed.",),
        artifacts=("artifact",),
        acceptance_results={"Acceptance criterion": True},
    )

    with pytest.raises(ValueError, match="cannot start attempt"):
        attempt_transition(
            db_path,
            task_id="task-1",
            attempt_id="attempt-2",
            executor="manual",
            status="running",
            summary="Second normal attempt.",
        )


def test_accepted_shipping_proof_closes_plan(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        executor="manual",
        status="running",
        summary="Running task.",
    )
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        status="succeeded",
        summary="Task satisfied.",
        checks=("Focused check passed.",),
        artifacts=("artifact",),
        acceptance_results={"Acceptance criterion": True},
    )
    task_create(
        db_path,
        plan_id="plan-1",
        plan_title="Plan",
        plan_goal="Goal",
        title="Shipping proof",
        intent="Prove task-1 is ready to ship.",
        assurance="high",
        acceptance_criteria=("Final proof exists",),
        lineage=({"relation": "shipping_proof_of", "task_id": "task-1"},),
        task_id="task-proof",
    )
    attempt_transition(
        db_path,
        task_id="task-proof",
        attempt_id="attempt-proof",
        executor="manual",
        status="running",
        summary="Running proof.",
    )
    attempt_transition(
        db_path,
        task_id="task-proof",
        attempt_id="attempt-proof",
        status="succeeded",
        summary="Proof accepted.",
        checks=("Final proof checked.",),
        artifacts=("proof",),
        acceptance_results={"Final proof exists": True},
        risks=("No known residual risk.",),
    )

    with sqlite3.connect(db_path) as connection:
        plan_status = connection.execute(
            "select status from plans where plan_id = 'plan-1'"
        ).fetchone()[0]
    queued = queue_next(db_path)

    assert plan_status == "done"
    assert queued.plan is None
    assert queued.task is None
    assert queued.next_transition == "none"


def test_task_create_reopens_legacy_done_plan_without_completion_proof(
    tmp_path: Path,
) -> None:
    db_path = make_planning_db(tmp_path)
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        executor="manual",
        status="running",
        summary="Running task.",
    )
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        status="succeeded",
        summary="Task satisfied.",
        checks=("Focused check passed.",),
        artifacts=("artifact",),
        acceptance_results={"Acceptance criterion": True},
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute("update plans set status = 'done' where plan_id = 'plan-1'")

    created = task_create(
        db_path,
        plan_id="plan-1",
        plan_title="Plan",
        plan_goal="Goal",
        title="Repair task",
        intent="Repair legacy accepted work without creating a separate plan.",
        assurance="medium",
        acceptance_criteria=("Repair evidence exists",),
        lineage=({"relation": "repair_of", "task_id": "task-1"},),
        task_id="task-repair",
    )

    assert created.plan["status"] == "active"
    assert created.task["lineage"] == [{"relation": "repair_of", "task_id": "task-1"}]


def test_attempt_transition_can_retry_blocked_task_to_done(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        executor="manual",
        status="running",
        summary="Running task.",
    )
    first = attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        status="failed",
        summary="Task failed.",
        checks=("failure recorded",),
        artifacts=("artifact",),
        acceptance_results={"Acceptance criterion": False},
    )

    retry = attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-2",
        executor="manual",
        status="running",
        summary="Retry task.",
    )
    completed = attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-2",
        status="succeeded",
        summary="Retry satisfied task.",
        checks=("pytest tests/test_small_interface.py",),
        artifacts=("src/codex_supervisor/small_interface.py",),
        acceptance_results={"Acceptance criterion": True},
    )

    assert first.task_status == "blocked"
    assert retry.task_status == "running"
    assert completed.task_status == "done"
    assert completed.acceptance is not None
    assert completed.acceptance["accepted"] is True


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


def test_attempt_transition_rejects_cross_task_start(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)
    insert_task(db_path, task_id="task-2", status="ready")
    attempt_transition(
        db_path,
        task_id="task-2",
        attempt_id="attempt-task-2",
        status="planned",
        summary="Task 2 attempt.",
    )

    with pytest.raises(ValueError, match="belongs to task"):
        attempt_transition(
            db_path,
            task_id="task-1",
            attempt_id="attempt-task-2",
            status="running",
            summary="Wrong task.",
        )


def test_attempt_transition_rejects_cross_task_terminal_transition(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)
    insert_task(db_path, task_id="task-2", status="ready")
    attempt_transition(
        db_path,
        task_id="task-2",
        attempt_id="attempt-task-2",
        status="running",
        summary="Task 2 running.",
    )

    with pytest.raises(ValueError, match="belongs to task"):
        attempt_transition(
            db_path,
            task_id="task-1",
            attempt_id="attempt-task-2",
            status="succeeded",
            summary="Wrong task.",
            checks=("pytest",),
            artifacts=("artifact",),
            acceptance_results={"Acceptance criterion": True},
        )
