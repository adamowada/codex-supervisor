"""Tiny public interface over the compact control-plane model."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codex_supervisor.attempt_store import AttemptStore, TaskRecord
from codex_supervisor.attempts import (
    AttemptEvidence,
    RunAttempt,
    RunAttemptStatus,
    normalize_attempt_status,
)
from codex_supervisor.policy import (
    AcceptanceEvaluation,
    AttemptRecord,
    EvidenceBundle,
    TaskIntent,
    evaluate_task_attempt_acceptance,
)


@dataclass(frozen=True)
class QueueNextResult:
    """Result for the single queue inspection command."""

    plan: dict[str, object] | None
    task: dict[str, object] | None
    active_attempt: dict[str, object] | None
    latest_evidence: dict[str, object] | None
    next_transition: str


@dataclass(frozen=True)
class AttemptTransitionResult:
    """Result for the single attempt mutation command."""

    task: dict[str, object]
    attempt: dict[str, object]
    evidence: dict[str, object] | None
    acceptance: dict[str, object] | None
    task_status: str


def queue_next(database_path: Path) -> QueueNextResult:
    """Inspect the next task and its attempt/evidence state."""

    store = AttemptStore(database_path, read_only=True)
    queued = store.read_next_task()
    if queued is None:
        return QueueNextResult(
            plan=None,
            task=None,
            active_attempt=None,
            latest_evidence=None,
            next_transition="none",
        )

    task = queued.task
    active_attempt = store.read_active_attempt(task.task_id)
    latest_evidence = store.read_latest_evidence(task.task_id)
    return QueueNextResult(
        plan={
            "plan_id": queued.plan_id,
            "title": queued.plan_title,
            "status": queued.plan_status,
            "priority": queued.priority,
        },
        task=_task_to_dict(task),
        active_attempt=_attempt_to_dict(active_attempt) if active_attempt else None,
        latest_evidence=_evidence_to_dict(latest_evidence) if latest_evidence else None,
        next_transition=_next_transition(task, active_attempt),
    )


def attempt_transition(
    database_path: Path,
    *,
    task_id: str,
    status: str,
    summary: str,
    executor: str = "manual",
    attempt_id: str | None = None,
    checks: tuple[str, ...] = (),
    artifacts: tuple[str, ...] = (),
    acceptance_results: dict[str, bool] | None = None,
    risks: tuple[str, ...] = (),
    gaps: tuple[str, ...] = (),
    next_actions: tuple[str, ...] = (),
    review_evidence: tuple[str, ...] = (),
) -> AttemptTransitionResult:
    """Perform one attempt transition and optional evidence/acceptance evaluation."""

    store = AttemptStore(database_path)
    task = store.read_task(task_id)
    target_status = normalize_attempt_status(status)

    if target_status is RunAttemptStatus.PLANNED:
        attempt = store.create_attempt(
            task_id=task_id,
            executor=executor,
            summary=summary,
            attempt_id=attempt_id,
        )
        return _transition_result(store, task, attempt, None, None)

    if target_status is RunAttemptStatus.RUNNING:
        attempt = _start_or_create_running_attempt(store, task_id, executor, summary, attempt_id)
        return _transition_result(store, task, attempt, None, None)

    attempt = _terminal_attempt(store, task_id, target_status, summary, attempt_id)
    evidence = store.attach_evidence_bundle(
        task_id=task_id,
        attempt_id=attempt.attempt_id,
        assurance=task.assurance,
        summary=summary,
        checks=_evidence_check_strings(
            checks=checks,
            acceptance_results=acceptance_results,
            risks=risks,
            gaps=gaps,
            next_actions=next_actions,
            review_evidence=review_evidence,
        ),
        artifacts=artifacts,
    )
    evaluation = _evaluate_transition(
        task,
        attempt,
        evidence,
        checks=checks,
        acceptance_results=acceptance_results,
        risks=risks,
        gaps=gaps,
        next_actions=next_actions,
        review_evidence=review_evidence,
    )
    task_status = (
        "done"
        if attempt.status is RunAttemptStatus.SUCCEEDED and evaluation.accepted
        else "blocked"
    )
    store.update_task_status(task_id, task_status)
    return _transition_result(store, task, attempt, evidence, evaluation)


def _start_or_create_running_attempt(
    store: AttemptStore,
    task_id: str,
    executor: str,
    summary: str,
    attempt_id: str | None,
) -> RunAttempt:
    if attempt_id is None:
        active = store.list_active_attempts(task_id)
        if active:
            return store.start_attempt(active[0].attempt_id, task_id=task_id, summary=summary)
        created = store.create_attempt(task_id=task_id, executor=executor, summary=summary)
        return store.start_attempt(created.attempt_id, task_id=task_id, summary=summary)
    try:
        return store.start_attempt(attempt_id, task_id=task_id, summary=summary)
    except LookupError:
        created = store.create_attempt(
            task_id=task_id,
            executor=executor,
            summary=summary,
            attempt_id=attempt_id,
        )
        return store.start_attempt(created.attempt_id, task_id=task_id, summary=summary)


def _terminal_attempt(
    store: AttemptStore,
    task_id: str,
    target_status: RunAttemptStatus,
    summary: str,
    attempt_id: str | None,
) -> RunAttempt:
    if attempt_id is None:
        active = store.list_active_attempts(task_id)
        if len(active) != 1:
            raise ValueError("terminal transitions require exactly one active attempt")
        attempt_id = active[0].attempt_id
    return store.complete_attempt(
        attempt_id,
        task_id=task_id,
        status=target_status,
        summary=summary,
    )


def _evaluate_transition(
    task: TaskRecord,
    attempt: RunAttempt,
    evidence: AttemptEvidence,
    *,
    checks: tuple[str, ...],
    acceptance_results: dict[str, bool] | None,
    risks: tuple[str, ...],
    gaps: tuple[str, ...],
    next_actions: tuple[str, ...],
    review_evidence: tuple[str, ...],
) -> AcceptanceEvaluation:
    strict_checks = checks if task.assurance == "high" else ()
    focused_checks = checks if task.assurance != "high" else ()
    return evaluate_task_attempt_acceptance(
        TaskIntent(
            task_id=task.task_id,
            intent=task.intent,
            assurance=task.assurance,
            acceptance_criteria=task.acceptance_criteria,
            review_required=bool(review_evidence),
        ),
        AttemptRecord(
            attempt_id=attempt.attempt_id,
            task_id=attempt.task_id,
            status=attempt.status.value,
        ),
        EvidenceBundle(
            task_id=evidence.task_id,
            attempt_id=evidence.attempt_id or "",
            summary=evidence.summary,
            checks=focused_checks,
            strict_checks=strict_checks,
            artifacts=evidence.artifacts,
            acceptance_results=acceptance_results,
            risks=risks,
            gaps=gaps,
            next_actions=next_actions,
            review_evidence=review_evidence,
        ),
    )


def _evidence_check_strings(
    *,
    checks: tuple[str, ...],
    acceptance_results: dict[str, bool] | None,
    risks: tuple[str, ...],
    gaps: tuple[str, ...],
    next_actions: tuple[str, ...],
    review_evidence: tuple[str, ...],
) -> tuple[str, ...]:
    evidence_checks = list(checks)
    for criterion, passed in sorted((acceptance_results or {}).items()):
        evidence_checks.append(f"acceptance: {criterion} = {'pass' if passed else 'fail'}")
    evidence_checks.extend(f"risk: {risk}" for risk in risks)
    evidence_checks.extend(f"gap: {gap}" for gap in gaps)
    evidence_checks.extend(f"next-action: {action}" for action in next_actions)
    evidence_checks.extend(f"review: {review}" for review in review_evidence)
    return tuple(evidence_checks)


def _transition_result(
    store: AttemptStore,
    task: TaskRecord,
    attempt: RunAttempt,
    evidence: AttemptEvidence | None,
    evaluation: AcceptanceEvaluation | None,
) -> AttemptTransitionResult:
    current_task = store.read_task(task.task_id)
    return AttemptTransitionResult(
        task=_task_to_dict(current_task),
        attempt=_attempt_to_dict(attempt),
        evidence=_evidence_to_dict(evidence) if evidence else None,
        acceptance=_evaluation_to_dict(evaluation) if evaluation else None,
        task_status=current_task.status,
    )


def _task_to_dict(task: TaskRecord) -> dict[str, object]:
    return {
        "task_id": task.task_id,
        "plan_id": task.plan_id,
        "title": task.title,
        "status": task.status,
        "assurance": task.assurance,
        "intent": task.intent,
        "acceptance_criteria": list(task.acceptance_criteria),
    }


def _attempt_to_dict(attempt: RunAttempt) -> dict[str, object]:
    return {
        "attempt_id": attempt.attempt_id,
        "task_id": attempt.task_id,
        "executor": attempt.executor,
        "status": attempt.status.value,
        "summary": attempt.summary,
        "started_at": attempt.started_at,
        "finished_at": attempt.finished_at,
    }


def _evidence_to_dict(evidence: AttemptEvidence) -> dict[str, object]:
    return {
        "bundle_id": evidence.bundle_id,
        "task_id": evidence.task_id,
        "attempt_id": evidence.attempt_id,
        "assurance": evidence.assurance,
        "summary": evidence.summary,
        "checks": list(evidence.checks),
        "artifacts": list(evidence.artifacts),
        "created_at": evidence.created_at,
    }


def _evaluation_to_dict(evaluation: AcceptanceEvaluation) -> dict[str, object]:
    return {
        "accepted": evaluation.accepted,
        "assurance": evaluation.assurance.value,
        "missing_requirements": list(evaluation.missing_requirements),
        "failed_acceptance_criteria": list(evaluation.failed_acceptance_criteria),
    }


def _next_transition(
    task: TaskRecord,
    attempt: RunAttempt | None,
) -> str:
    if task.status == "ready":
        return "attempt-transition --status running"
    if attempt is not None:
        return "attempt-transition --status succeeded|failed|blocked"
    return "none"
