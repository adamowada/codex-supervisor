"""Terminal attempt transition ownership."""

from __future__ import annotations

from dataclasses import dataclass

from codex_supervisor.attempt_store import AttemptStore, TaskRecord
from codex_supervisor.attempts import AttemptEvidence, RunAttempt, RunAttemptStatus
from codex_supervisor.evidence import EvidenceEnvelope
from codex_supervisor.policy import (
    AcceptanceEvaluation,
    AttemptRecord,
    TaskIntent,
    evaluate_task_attempt_acceptance,
)


@dataclass(frozen=True)
class TerminalTransitionResult:
    """Durable result of terminalizing one attempt."""

    attempt: RunAttempt
    evidence: AttemptEvidence
    evaluation: AcceptanceEvaluation
    task_status: str


def terminalize_attempt(
    store: AttemptStore,
    task: TaskRecord,
    *,
    attempt_id: str,
    status: RunAttemptStatus,
    summary: str,
    artifacts: tuple[str, ...],
    evidence: EvidenceEnvelope,
) -> TerminalTransitionResult:
    """Evaluate acceptance, persist evidence, and move an attempt terminal."""

    policy_evidence = evidence.policy_bundle(
        task_id=task.task_id,
        attempt_id=attempt_id,
        assurance=task.assurance,
        summary=summary,
        artifacts=artifacts,
    )
    evaluation = evaluate_task_attempt_acceptance(
        TaskIntent(
            task_id=task.task_id,
            intent=task.intent,
            assurance=task.assurance,
            acceptance_criteria=task.acceptance_criteria,
            review_required=bool(evidence.review_evidence),
        ),
        AttemptRecord(
            attempt_id=attempt_id,
            task_id=task.task_id,
            status=status.value,
        ),
        policy_evidence,
    )
    task_status = (
        "done"
        if status is RunAttemptStatus.SUCCEEDED and evaluation.accepted
        else "blocked"
    )
    attempt, persisted_evidence = store.finalize_attempt(
        attempt_id,
        task_id=task.task_id,
        status=status,
        summary=summary,
        task_status=task_status,
        assurance=task.assurance,
        checks=evidence.storage_checks(),
        artifacts=artifacts,
    )
    return TerminalTransitionResult(
        attempt=attempt,
        evidence=persisted_evidence,
        evaluation=evaluation,
        task_status=task_status,
    )
