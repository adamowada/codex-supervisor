from __future__ import annotations

import sqlite3
from pathlib import Path

from planning_db_factory import insert_task, make_planning_db

from codex_supervisor.small_interface import attempt_transition, task_create
from codex_supervisor.work_graph import (
    LineageRelation,
    TaskGraphNode,
    final_proof_state,
    latest_recovery_node,
    lineage_to_dicts,
    plan_has_durable_completion,
    parse_lineage_json,
    suggested_lineage_targets,
    suggested_relations_for_task_status,
)


def test_work_graph_parses_lineage_and_projects_final_proof() -> None:
    lineage = parse_lineage_json(
        """
        [
          {"relation": "shipping_proof_of", "task_id": "task-1"},
          {"relation": "review_of", "task_id": "task-review-target"},
          {"ignored": true}
        ]
        """
    )
    task = TaskGraphNode(task_id="task-proof", status="done", lineage=lineage)

    assert lineage == (
        LineageRelation(relation="shipping_proof_of", task_id="task-1"),
        LineageRelation(relation="review_of", task_id="task-review-target"),
    )
    assert final_proof_state(task) == {
        "task_id": "task-proof",
        "proves_task_ids": ["task-1"],
        "status": "done",
    }
    assert lineage_to_dicts(lineage) == [
        {"relation": "shipping_proof_of", "task_id": "task-1"},
        {"relation": "review_of", "task_id": "task-review-target"},
    ]


def test_work_graph_projects_recovery_targets_from_task_status() -> None:
    tasks = (
        TaskGraphNode(task_id="task-dropped", status="dropped"),
        TaskGraphNode(task_id="task-done", status="done"),
        TaskGraphNode(task_id="task-blocked", status="blocked"),
        TaskGraphNode(task_id="task-ready", status="ready"),
    )

    assert latest_recovery_node(tasks) == tasks[1]
    assert suggested_relations_for_task_status("done") == (
        "review_of",
        "repair_of",
        "shipping_proof_of",
    )
    assert suggested_relations_for_task_status("blocked") == ("repair_of",)
    assert suggested_lineage_targets(tasks) == (
        {
            "task_id": "task-done",
            "status": "done",
            "suggested_relations": ["review_of", "repair_of", "shipping_proof_of"],
            "lineage": [],
        },
        {
            "task_id": "task-blocked",
            "status": "blocked",
            "suggested_relations": ["repair_of"],
            "lineage": [],
        },
    )


def test_work_graph_durable_completion_uses_projection_coverage(
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
    insert_task(db_path, task_id="task-after-proof", status="done")

    with sqlite3.connect(db_path) as connection:
        assert not plan_has_durable_completion(connection, "plan-1")
