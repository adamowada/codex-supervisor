from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from planning_db_factory import make_planning_db

from codex_supervisor.attempt_store import AttemptStore
from codex_supervisor.attempts import RunAttemptStatus
from codex_supervisor.evidence import EvidenceEnvelope
from codex_supervisor.terminal_transition import terminalize_attempt


def test_evidence_envelope_preserves_structure_before_storage_encoding() -> None:
    envelope = EvidenceEnvelope(
        checks=("pytest passed",),
        acceptance_results={"Criterion B": False, "Criterion A": True},
        risks=("Risk noted",),
        gaps=("Gap noted",),
        next_actions=("Next action",),
        review_evidence=("Review note",),
    )

    assert envelope.storage_checks() == (
        "pytest passed",
        "acceptance: Criterion A = pass",
        "acceptance: Criterion B = fail",
        "risk: Risk noted",
        "gap: Gap noted",
        "next-action: Next action",
        "review: Review note",
    )
    bundle = envelope.policy_bundle(
        task_id="task-1",
        attempt_id="attempt-1",
        assurance="high",
        summary="Summary",
        artifacts=("README.md",),
    )
    assert bundle.strict_checks == ("pytest passed",)
    assert bundle.checks == ()
    assert bundle.acceptance_results == {
        "Criterion A": True,
        "Criterion B": False,
    }


def test_terminalize_attempt_owns_acceptance_and_persistence(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)
    store = AttemptStore(db_path)
    store.create_attempt(
        task_id="task-1",
        executor="worker-process",
        summary="Worker planned.",
        attempt_id="attempt-1",
    )
    store.start_attempt(
        "attempt-1",
        task_id="task-1",
        summary="Worker running.",
        started_at="2026-06-04T00:00:00Z",
    )

    result = terminalize_attempt(
        store,
        store.read_task("task-1"),
        attempt_id="attempt-1",
        status=RunAttemptStatus.SUCCEEDED,
        summary="Worker succeeded.",
        artifacts=("README.md",),
        evidence=EvidenceEnvelope(
            checks=("README.md exists",),
            acceptance_results={"Acceptance criterion": True},
            risks=("No known residual risk.",),
            review_evidence=("Reviewer inspected README.md.",),
        ),
    )

    assert result.task_status == "done"
    assert result.evaluation.accepted is True
    assert result.decision.result == "accepted"
    assert result.decision.actor == "codex-supervisor-policy"
    assert result.decision.task_id == "task-1"
    assert result.decision.attempt_id == "attempt-1"
    assert result.decision.bundle_id == result.evidence.bundle_id
    assert result.decision.evaluation["criteria_results"] == [
        {"criterion": "Acceptance criterion", "status": "pass"}
    ]
    assert result.attempt.status is RunAttemptStatus.SUCCEEDED
    assert result.evidence.checks == (
        "README.md exists",
        "acceptance: Acceptance criterion = pass",
        "risk: No known residual risk.",
        "review: Reviewer inspected README.md.",
    )
    assert store.read_task("task-1").status == "done"

    row = _acceptance_decision_row(db_path, "attempt-1")
    assert row["result"] == "accepted"
    assert row["bundle_id"] == result.evidence.bundle_id
    assert json.loads(row["evaluation_json"])["accepted"] is True


def test_terminalize_attempt_records_rejected_acceptance_decision(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)
    store = AttemptStore(db_path)
    store.create_attempt(
        task_id="task-1",
        executor="worker-process",
        summary="Worker planned.",
        attempt_id="attempt-1",
    )
    store.start_attempt(
        "attempt-1",
        task_id="task-1",
        summary="Worker running.",
        started_at="2026-06-04T00:00:00Z",
    )

    result = terminalize_attempt(
        store,
        store.read_task("task-1"),
        attempt_id="attempt-1",
        status=RunAttemptStatus.SUCCEEDED,
        summary="Worker missed acceptance.",
        artifacts=("README.md",),
        evidence=EvidenceEnvelope(
            checks=("README.md exists",),
            acceptance_results={"Acceptance criterion": False},
            risks=("No known residual risk.",),
            review_evidence=("Reviewer inspected README.md.",),
        ),
    )

    assert result.task_status == "blocked"
    assert result.evaluation.accepted is False
    assert result.decision.result == "rejected"
    assert result.decision.evaluation["criteria_results"] == [
        {"criterion": "Acceptance criterion", "status": "fail"}
    ]
    assert result.decision.evaluation["failed_acceptance_criteria"] == [
        "Acceptance criterion"
    ]
    assert "failed acceptance criteria" in result.decision.rationale
    assert store.read_task("task-1").status == "blocked"

    row = _acceptance_decision_row(db_path, "attempt-1")
    assert row["result"] == "rejected"
    assert json.loads(row["evaluation_json"])["accepted"] is False


def _acceptance_decision_row(db_path: Path, attempt_id: str) -> sqlite3.Row:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """select decision_id, task_id, attempt_id, bundle_id, actor,
                      result, rationale, evaluation_json, created_at
               from acceptance_decisions
               where attempt_id = ?""",
            (attempt_id,),
        ).fetchone()
    finally:
        connection.close()
    assert row is not None
    return row
