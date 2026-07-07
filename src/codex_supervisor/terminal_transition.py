"""Terminal attempt transition ownership."""

from __future__ import annotations

from dataclasses import dataclass

from codex_supervisor.attempt_store import AttemptStore, TaskRecord
from codex_supervisor.attempts import (
    AcceptanceDecision,
    AttemptEvidence,
    RunAttempt,
    RunAttemptStatus,
)
from codex_supervisor.evidence import EvidenceEnvelope
from codex_supervisor.evidence_digest import build_evidence_digest, encode_evidence_digest
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
    decision: AcceptanceDecision
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
    acceptance_result = "accepted" if task_status == "done" else "rejected"
    acceptance_rationale = _acceptance_rationale(evaluation)
    acceptance_evaluation = _acceptance_evaluation_payload(
        task=task,
        attempt_status=status,
        evidence=evidence,
        evaluation=evaluation,
    )
    storage_checks = evidence.storage_checks()
    evidence_digest = build_evidence_digest(
        summary=summary,
        checks=storage_checks,
        artifacts=artifacts,
        risks=evidence.risks,
        gaps=evidence.gaps,
        next_actions=evidence.next_actions,
        review_evidence=evidence.review_evidence,
        acceptance_rationale=acceptance_rationale,
        acceptance_evaluation=acceptance_evaluation,
    )
    attempt, persisted_evidence, decision = store.finalize_attempt(
        attempt_id,
        task_id=task.task_id,
        status=status,
        summary=summary,
        task_status=task_status,
        assurance=task.assurance,
        checks=(*storage_checks, encode_evidence_digest(evidence_digest)),
        artifacts=artifacts,
        acceptance_actor="codex-supervisor-policy",
        acceptance_result=acceptance_result,
        acceptance_rationale=acceptance_rationale,
        acceptance_evaluation=acceptance_evaluation,
    )
    return TerminalTransitionResult(
        attempt=attempt,
        evidence=persisted_evidence,
        decision=decision,
        evaluation=evaluation,
        task_status=task_status,
    )


def _acceptance_evaluation_payload(
    *,
    task: TaskRecord,
    attempt_status: RunAttemptStatus,
    evidence: EvidenceEnvelope,
    evaluation: AcceptanceEvaluation,
) -> dict[str, object]:
    results = dict(evidence.acceptance_results or {})
    return {
        "accepted": evaluation.accepted,
        "assurance": evaluation.assurance.value,
        "attempt_status": attempt_status.value,
        "criteria_results": [
            {
                "criterion": criterion,
                "status": "pass" if results.get(criterion) is True else "fail",
            }
            for criterion in task.acceptance_criteria
        ],
        "missing_requirements": list(evaluation.missing_requirements),
        "failed_acceptance_criteria": list(evaluation.failed_acceptance_criteria),
    }


def _acceptance_rationale(evaluation: AcceptanceEvaluation) -> str:
    if evaluation.accepted:
        return "Policy accepted terminal evidence."
    reasons: list[str] = []
    if evaluation.missing_requirements:
        reasons.append(
            "missing requirements: " + ", ".join(evaluation.missing_requirements)
        )
    if evaluation.failed_acceptance_criteria:
        reasons.append(
            "failed acceptance criteria: "
            + ", ".join(evaluation.failed_acceptance_criteria)
        )
    if not reasons:
        reasons.append("policy rejected terminal evidence")
    return "Policy rejected terminal evidence: " + "; ".join(reasons) + "."
