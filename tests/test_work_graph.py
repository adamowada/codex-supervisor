from __future__ import annotations

from codex_supervisor.work_graph import (
    LineageRelation,
    TaskGraphNode,
    final_proof_state,
    latest_recovery_node,
    lineage_to_dicts,
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
