from __future__ import annotations

import sqlite3
from pathlib import Path

from planning_db_factory import make_planning_db

from codex_supervisor.projections import project_plan, read_current_terminal
from codex_supervisor.small_interface import attempt_transition, queue_next, task_create


def test_projection_recovers_blocked_task_through_repair_and_final_proof(
    tmp_path: Path,
) -> None:
    db_path = make_planning_db(tmp_path)
    _block_source_task(db_path)
    with sqlite3.connect(db_path) as connection:
        blocked_projection = project_plan(connection, "plan-1")

    assert blocked_projection.projected_status == "blocked"
    assert blocked_projection.unresolved_blocker_ids == ("task-1",)
    assert queue_next(db_path).next_transition == "task-create --lineage repair_of=task-1"

    _accept_repair_task(db_path)
    with sqlite3.connect(db_path) as connection:
        repaired_projection = project_plan(connection, "plan-1")
        stored_status_after_repair = connection.execute(
            "select status from plans where plan_id = 'plan-1'"
        ).fetchone()[0]

    assert stored_status_after_repair == "active"
    assert repaired_projection.projected_status == "active"
    assert repaired_projection.unresolved_blocker_ids == ()
    assert repaired_projection.recovered_blocker_ids == ("task-1",)
    assert repaired_projection.final_proof.state == "missing"
    repaired_queue = queue_next(db_path)
    assert repaired_queue.next_transition == (
        "active plan has no open task; suggested next: "
        "task-create --lineage review_of=task-repair | "
        "task-create --lineage repair_of=task-repair | "
        "task-create --lineage shipping_proof_of=task-repair"
    )
    assert repaired_queue.recovery_state["suggested_lineage_targets"] == [
        {
            "task_id": "task-repair",
            "status": "done",
            "suggested_relations": ["review_of", "repair_of", "shipping_proof_of"],
            "lineage": [{"relation": "repair_of", "task_id": "task-1"}],
        }
    ]

    _accept_final_proof(db_path)

    with sqlite3.connect(db_path) as connection:
        final_projection = project_plan(connection, "plan-1")
        stored_status = connection.execute(
            "select status from plans where plan_id = 'plan-1'"
        ).fetchone()[0]
    queued = queue_next(db_path)

    assert stored_status == "done"
    assert final_projection.projected_status == "done"
    assert final_projection.durable_completion is True
    assert final_projection.final_proof.state == "current"
    assert final_projection.final_proof.covered_task_ids == (
        "task-1",
        "task-proof",
        "task-repair",
    )
    assert queued.plan is None
    assert queued.task is None
    assert queued.next_transition == "none"


def test_queue_next_suppresses_stale_blocked_plan_after_projected_completion(
    tmp_path: Path,
) -> None:
    db_path = make_planning_db(tmp_path)
    _complete_repaired_plan(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("update plans set status = 'blocked' where plan_id = 'plan-1'")
        projection = project_plan(connection, "plan-1")

    queued = queue_next(db_path)

    assert projection.stored_status == "blocked"
    assert projection.projected_status == "done"
    assert projection.durable_completion is True
    assert queued.plan is None
    assert queued.task is None
    assert queued.next_transition == "none"


def test_queue_next_suppresses_stale_active_plan_after_projected_completion(
    tmp_path: Path,
) -> None:
    db_path = make_planning_db(tmp_path)
    _complete_repaired_plan(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("update plans set status = 'active' where plan_id = 'plan-1'")
        projection = project_plan(connection, "plan-1")

    queued = queue_next(db_path)

    assert projection.stored_status == "active"
    assert projection.projected_status == "done"
    assert projection.durable_completion is True
    assert queued.plan is None
    assert queued.task is None
    assert queued.next_transition == "none"


def test_queue_next_uses_projected_recovery_for_stale_blocked_plan(
    tmp_path: Path,
) -> None:
    db_path = make_planning_db(tmp_path)
    _block_source_task(db_path)
    _accept_repair_task(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("update plans set status = 'blocked' where plan_id = 'plan-1'")
        projection = project_plan(connection, "plan-1")

    queued = queue_next(db_path)

    assert projection.stored_status == "blocked"
    assert projection.projected_status == "active"
    assert projection.recovered_blocker_ids == ("task-1",)
    assert queued.plan is not None
    assert queued.plan["status"] == "active"
    assert queued.task is None
    assert queued.next_transition == (
        "active plan has no open task; suggested next: "
        "task-create --lineage review_of=task-repair | "
        "task-create --lineage repair_of=task-repair | "
        "task-create --lineage shipping_proof_of=task-repair"
    )


def test_current_terminal_is_joined_to_its_evidence_and_acceptance(
    tmp_path: Path,
) -> None:
    db_path = make_planning_db(tmp_path)
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        executor="manual",
        status="running",
        summary="Task started.",
    )
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        status="failed",
        summary="Task failed.",
        checks=("failure recorded",),
        artifacts=("artifact",),
        acceptance_results={"Acceptance criterion": False},
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """insert into evidence_bundles(
                   bundle_id, task_id, attempt_id, assurance, summary,
                   checks_json, artifacts_json, created_at
               ) values (
                   'later-evidence', 'task-1', null, 'medium', 'Unattached evidence.',
                   '["later check"]', '["later artifact"]', '2099-01-01T00:00:00Z'
               )"""
        )
        terminal = read_current_terminal(connection, "task-1")

    queued = queue_next(db_path)

    assert terminal is not None
    assert terminal.attempt_id == "attempt-1"
    assert terminal.bundle_id != "later-evidence"
    assert queued.latest_evidence is not None
    assert queued.latest_evidence["bundle_id"] == "later-evidence"
    assert queued.latest_acceptance is not None
    assert queued.latest_acceptance["attempt_id"] == "attempt-1"
    assert queued.latest_acceptance["bundle_id"] == terminal.bundle_id
    assert "latest_acceptance_not_latest_evidence" in queued.recovery_state["warning_flags"]


def _complete_repaired_plan(db_path: Path) -> None:
    _block_source_task(db_path)
    _accept_repair_task(db_path)
    _accept_final_proof(db_path)


def _block_source_task(db_path: Path) -> None:
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        executor="manual",
        status="running",
        summary="Original work started.",
    )
    attempt_transition(
        db_path,
        task_id="task-1",
        attempt_id="attempt-1",
        status="failed",
        summary="Original work failed.",
        checks=("failure recorded",),
        artifacts=("artifact",),
        acceptance_results={"Acceptance criterion": False},
    )


def _accept_repair_task(db_path: Path) -> None:
    task_create(
        db_path,
        plan_id="plan-1",
        plan_title="Plan",
        plan_goal="Goal",
        title="Repair task",
        intent="Repair task-1.",
        assurance="medium",
        acceptance_criteria=("Repair accepted",),
        lineage=({"relation": "repair_of", "task_id": "task-1"},),
        task_id="task-repair",
    )
    attempt_transition(
        db_path,
        task_id="task-repair",
        attempt_id="attempt-repair",
        executor="manual",
        status="running",
        summary="Repair started.",
    )
    attempt_transition(
        db_path,
        task_id="task-repair",
        attempt_id="attempt-repair",
        status="succeeded",
        summary="Repair accepted.",
        checks=("repair verified",),
        artifacts=("repair-artifact",),
        acceptance_results={"Repair accepted": True},
    )


def _accept_final_proof(db_path: Path) -> None:
    task_create(
        db_path,
        plan_id="plan-1",
        plan_title="Plan",
        plan_goal="Goal",
        title="Shipping proof",
        intent="Prove repaired work is ready to ship.",
        assurance="high",
        acceptance_criteria=("Final proof accepted",),
        lineage=({"relation": "shipping_proof_of", "task_id": "task-repair"},),
        task_id="task-proof",
    )
    attempt_transition(
        db_path,
        task_id="task-proof",
        attempt_id="attempt-proof",
        executor="manual",
        status="running",
        summary="Proof started.",
    )
    attempt_transition(
        db_path,
        task_id="task-proof",
        attempt_id="attempt-proof",
        status="succeeded",
        summary="Proof accepted.",
        checks=("final proof verified",),
        artifacts=("proof-artifact",),
        acceptance_results={"Final proof accepted": True},
        risks=("No known residual risk.",),
    )
