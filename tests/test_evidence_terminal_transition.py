from __future__ import annotations

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
    assert result.attempt.status is RunAttemptStatus.SUCCEEDED
    assert result.evidence.checks == (
        "README.md exists",
        "acceptance: Acceptance criterion = pass",
        "risk: No known residual risk.",
        "review: Reviewer inspected README.md.",
    )
    assert store.read_task("task-1").status == "done"
