"""Read-only helpers for durable work-graph questions."""

from __future__ import annotations

import json
import sqlite3

COMPLETION_EXCEPTION_DECISIONS = frozenset(
    {"unsupervised_completion_exception", "explicit_unsupervised_completion_exception"}
)


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
    try:
        lineage = json.loads(raw_json)
    except json.JSONDecodeError:
        return False
    if not isinstance(lineage, list):
        return False
    return any(
        isinstance(item, dict) and item.get("relation") == "shipping_proof_of"
        for item in lineage
    )
