"""Read-only helpers for durable work-graph questions."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

VALID_TASK_LINEAGE_RELATIONS = frozenset(
    {"retry_of", "repair_of", "review_of", "shipping_proof_of"}
)

COMPLETION_EXCEPTION_DECISIONS = frozenset(
    {"unsupervised_completion_exception", "explicit_unsupervised_completion_exception"}
)

FOLLOW_UP_RELATIONS_FOR_DONE_TASK = ("review_of", "repair_of", "shipping_proof_of")
FOLLOW_UP_RELATIONS_FOR_BLOCKED_TASK = ("repair_of",)


@dataclass(frozen=True)
class LineageRelation:
    """Generic relation from one task intent to another."""

    relation: str
    task_id: str


@dataclass(frozen=True)
class TaskGraphNode:
    """Task fields needed for read-only work-graph projection."""

    task_id: str
    status: str
    lineage: tuple[LineageRelation, ...] = ()


def plan_has_durable_completion(
    connection: sqlite3.Connection,
    plan_id: str,
) -> bool:
    """Return whether a plan has accepted final proof or an explicit exception."""

    return plan_has_accepted_shipping_proof(
        connection,
        plan_id,
    ) or plan_has_unsupervised_completion_exception(connection, plan_id)


def plan_has_accepted_shipping_proof(
    connection: sqlite3.Connection,
    plan_id: str,
) -> bool:
    """Return whether a plan has accepted terminal evidence for final-proof lineage."""

    rows = connection.execute(
        """select task_id, lineage_json
           from tasks
           where plan_id = ?
             and status = 'done'""",
        (plan_id,),
    ).fetchall()
    for task_id, lineage_json in rows:
        if not _has_shipping_proof_lineage(str(lineage_json)):
            continue
        if task_has_accepted_terminal_evidence(connection, str(task_id)):
            return True
    return False


def task_has_accepted_terminal_evidence(
    connection: sqlite3.Connection,
    task_id: str,
) -> bool:
    """Return whether a task has a succeeded attempt with accepted evidence."""

    return (
        connection.execute(
            """select 1
               from attempts
               join evidence_bundles
                 on evidence_bundles.attempt_id = attempts.attempt_id
                and evidence_bundles.task_id = attempts.task_id
               join acceptance_decisions
                 on acceptance_decisions.attempt_id = attempts.attempt_id
                and acceptance_decisions.bundle_id = evidence_bundles.bundle_id
                and acceptance_decisions.result = 'accepted'
               where attempts.task_id = ?
                 and attempts.status = 'succeeded'
               limit 1""",
            (task_id,),
        ).fetchone()
        is not None
    )


def plan_has_unsupervised_completion_exception(
    connection: sqlite3.Connection,
    plan_id: str,
) -> bool:
    """Return whether a plan has an explicit durable completion exception."""

    placeholders = ", ".join("?" for _ in COMPLETION_EXCEPTION_DECISIONS)
    return (
        connection.execute(
            f"""select 1
                from decisions
                where plan_id = ?
                  and decision in ({placeholders})
                limit 1""",
            (plan_id, *sorted(COMPLETION_EXCEPTION_DECISIONS)),
        ).fetchone()
        is not None
    )


def _has_shipping_proof_lineage(raw_json: str) -> bool:
    return any(
        item.relation == "shipping_proof_of"
        for item in parse_lineage_json(raw_json)
    )


def parse_lineage_json(raw_json: str) -> tuple[LineageRelation, ...]:
    """Parse stored task lineage for read-only graph projection."""

    try:
        decoded = json.loads(raw_json)
    except json.JSONDecodeError:
        return ()
    if not isinstance(decoded, list):
        return ()
    lineage: list[LineageRelation] = []
    for item in decoded:
        if not isinstance(item, dict):
            continue
        relation = item.get("relation")
        task_id = item.get("task_id")
        if not isinstance(relation, str) or not isinstance(task_id, str):
            continue
        lineage.append(LineageRelation(relation=relation, task_id=task_id))
    return tuple(lineage)


def suggested_relations_for_task_status(status: str) -> tuple[str, ...]:
    """Return generic follow-up relation suggestions for a task status."""

    if status == "blocked":
        return FOLLOW_UP_RELATIONS_FOR_BLOCKED_TASK
    if status == "done":
        return FOLLOW_UP_RELATIONS_FOR_DONE_TASK
    return ()


def suggested_lineage_targets(
    tasks: Iterable[TaskGraphNode],
) -> tuple[dict[str, object], ...]:
    """Return follow-up targets for an active plan with no open task."""

    targets: list[dict[str, object]] = []
    for task in tasks:
        relations = suggested_relations_for_task_status(task.status)
        if not relations:
            continue
        targets.append(
            {
                "task_id": task.task_id,
                "status": task.status,
                "suggested_relations": list(relations),
                "lineage": lineage_to_dicts(task.lineage),
            }
        )
    return tuple(targets)


def latest_recovery_node(
    tasks: Iterable[TaskGraphNode],
) -> TaskGraphNode | None:
    """Return the latest non-dropped task node for recovery projection."""

    for task in tasks:
        if task.status != "dropped":
            return task
    return None


def final_proof_state(
    task: TaskGraphNode | None,
) -> dict[str, object]:
    """Return final-proof recovery state for a task node."""

    if task is None:
        return {"task_id": None, "proves_task_ids": [], "status": None}
    proves_task_ids = [
        item.task_id for item in task.lineage if item.relation == "shipping_proof_of"
    ]
    return {
        "task_id": task.task_id if proves_task_ids else None,
        "proves_task_ids": proves_task_ids,
        "status": task.status if proves_task_ids else None,
    }


def lineage_to_dicts(
    lineage: Iterable[object],
) -> list[dict[str, str]]:
    """Return JSON-ready lineage dictionaries."""

    encoded: list[dict[str, str]] = []
    for item in lineage:
        if isinstance(item, LineageRelation):
            encoded.append({"relation": item.relation, "task_id": item.task_id})
            continue
        if isinstance(item, Mapping):
            relation = item.get("relation")
            task_id = item.get("task_id")
        else:
            relation = getattr(item, "relation", None)
            task_id = getattr(item, "task_id", None)
        if isinstance(relation, str) and isinstance(task_id, str):
            encoded.append({"relation": relation, "task_id": task_id})
    return encoded
