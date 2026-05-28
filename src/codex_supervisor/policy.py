"""Assurance policy for task acceptance.

This module is intentionally independent from CLI, MCP, worker transport, and
SQLite. It models the policy decision that later layers apply to planning rows.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum


class AssuranceLevel(StrEnum):
    """Evidence strength required before a task can advance."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class TaskIntent:
    """Task data needed for assurance and acceptance evaluation."""

    intent: str
    assurance: AssuranceLevel | str
    acceptance_criteria: tuple[str, ...] = ()
    task_id: str = ""
    review_required: bool = False


@dataclass(frozen=True)
class AttemptRecord:
    """Attempt data needed for policy evaluation."""

    status: str
    attempt_id: str = ""
    task_id: str = ""


@dataclass(frozen=True)
class EvidenceBundle:
    """Evidence data used by assurance policy."""

    summary: str
    checks: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()
    acceptance_results: Mapping[str, bool] | None = None
    risks: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()
    next_actions: tuple[str, ...] = ()
    strict_checks: tuple[str, ...] = ()
    review_evidence: tuple[str, ...] = ()
    task_id: str = ""
    attempt_id: str = ""


@dataclass(frozen=True)
class AssurancePolicy:
    """Concrete evidence requirements for an assurance level."""

    level: AssuranceLevel
    require_focused_checks: bool
    require_strict_checks: bool
    require_artifacts: bool
    require_acceptance_results: bool
    require_acceptance_criteria: bool
    require_risk_or_gap_notes: bool
    require_risk_notes: bool
    require_next_action: bool
    require_succeeded_attempt: bool
    require_review_when_requested: bool


@dataclass(frozen=True)
class AcceptanceEvaluation:
    """Result of evaluating task evidence against assurance policy."""

    accepted: bool
    assurance: AssuranceLevel
    missing_requirements: tuple[str, ...] = ()
    failed_acceptance_criteria: tuple[str, ...] = ()


LOW_POLICY = AssurancePolicy(
    level=AssuranceLevel.LOW,
    require_focused_checks=False,
    require_strict_checks=False,
    require_artifacts=False,
    require_acceptance_results=False,
    require_acceptance_criteria=False,
    require_risk_or_gap_notes=True,
    require_risk_notes=False,
    require_next_action=True,
    require_succeeded_attempt=False,
    require_review_when_requested=False,
)

MEDIUM_POLICY = AssurancePolicy(
    level=AssuranceLevel.MEDIUM,
    require_focused_checks=True,
    require_strict_checks=False,
    require_artifacts=True,
    require_acceptance_results=True,
    require_acceptance_criteria=True,
    require_risk_or_gap_notes=False,
    require_risk_notes=False,
    require_next_action=False,
    require_succeeded_attempt=True,
    require_review_when_requested=True,
)

HIGH_POLICY = AssurancePolicy(
    level=AssuranceLevel.HIGH,
    require_focused_checks=False,
    require_strict_checks=True,
    require_artifacts=True,
    require_acceptance_results=True,
    require_acceptance_criteria=True,
    require_risk_or_gap_notes=False,
    require_risk_notes=True,
    require_next_action=False,
    require_succeeded_attempt=True,
    require_review_when_requested=True,
)

ASSURANCE_POLICIES = {
    AssuranceLevel.LOW: LOW_POLICY,
    AssuranceLevel.MEDIUM: MEDIUM_POLICY,
    AssuranceLevel.HIGH: HIGH_POLICY,
}

LOW_INTENT_MARKERS = (
    "explore",
    "diagnose",
    "sketch",
    "candidate",
    "proposal",
    "research",
)

HIGH_INTENT_MARKERS = (
    "full-auto",
    "source-of-truth",
    "source of truth",
    "controller",
    "release",
    "destructive",
    "trust-boundary",
    "trust boundary",
    "protected",
    "high-assurance",
    "high assurance",
)

TERMINAL_ATTEMPT_STATUSES = {"succeeded", "failed", "blocked"}


def normalize_assurance(value: str | AssuranceLevel) -> AssuranceLevel:
    """Return an assurance enum for stored or in-memory values."""

    if isinstance(value, AssuranceLevel):
        return value
    try:
        return AssuranceLevel(value.strip().casefold())
    except ValueError as exc:
        allowed = ", ".join(level.value for level in AssuranceLevel)
        raise ValueError(f"unknown assurance level {value!r}; expected one of {allowed}") from exc


def policy_for_assurance(value: str | AssuranceLevel) -> AssurancePolicy:
    """Return evidence requirements for an assurance level."""

    return ASSURANCE_POLICIES[normalize_assurance(value)]


def infer_assurance_from_intent(intent: str) -> AssuranceLevel:
    """Infer the default assurance level from task intent text."""

    normalized = intent.casefold()
    if any(marker in normalized for marker in HIGH_INTENT_MARKERS):
        return AssuranceLevel.HIGH
    if any(marker in normalized for marker in LOW_INTENT_MARKERS):
        return AssuranceLevel.LOW
    return AssuranceLevel.MEDIUM


def task_intent_policy(
    *,
    intent: str,
    assurance: str | AssuranceLevel | None = None,
) -> AssurancePolicy:
    """Return the policy selected for a task intent."""

    level = (
        infer_assurance_from_intent(intent)
        if assurance is None
        else normalize_assurance(assurance)
    )
    return policy_for_assurance(level)


def evaluate_acceptance(task: TaskIntent, evidence: EvidenceBundle) -> AcceptanceEvaluation:
    """Evaluate whether evidence satisfies task assurance and acceptance criteria."""

    return evaluate_task_attempt_acceptance(task, None, evidence)


def evaluate_task_attempt_acceptance(
    task: TaskIntent,
    attempt: AttemptRecord | None,
    evidence: EvidenceBundle,
) -> AcceptanceEvaluation:
    """Evaluate task, attempt, and evidence records against assurance policy."""

    policy = policy_for_assurance(task.assurance)
    assurance = policy.level
    missing: list[str] = []

    if not evidence.summary.strip():
        missing.append("summary")
    if policy.require_risk_or_gap_notes and not evidence.risks and not evidence.gaps:
        missing.append("risk_or_gap_notes")
    if policy.require_next_action and not evidence.next_actions:
        missing.append("next_action")
    if policy.require_focused_checks and not evidence.checks:
        missing.append("focused_checks")
    if policy.require_strict_checks and not evidence.strict_checks:
        missing.append("strict_checks")
    if policy.require_artifacts and not evidence.artifacts:
        missing.append("artifacts")
    if policy.require_acceptance_criteria and not task.acceptance_criteria:
        missing.append("acceptance_criteria")
    if policy.require_risk_notes and not evidence.risks:
        missing.append("risk_notes")
    if (
        task.review_required
        and policy.require_review_when_requested
        and not evidence.review_evidence
    ):
        missing.append("review_evidence")
    if attempt is not None:
        _add_attempt_requirements(task, attempt, evidence, policy, missing)

    failed_criteria = _failed_acceptance_criteria(
        criteria=task.acceptance_criteria,
        results=evidence.acceptance_results,
        missing=missing,
        require_results=policy.require_acceptance_results,
    )

    return AcceptanceEvaluation(
        accepted=not missing and not failed_criteria,
        assurance=assurance,
        missing_requirements=tuple(missing),
        failed_acceptance_criteria=failed_criteria,
    )


def _add_attempt_requirements(
    task: TaskIntent,
    attempt: AttemptRecord,
    evidence: EvidenceBundle,
    policy: AssurancePolicy,
    missing: list[str],
) -> None:
    if attempt.status not in TERMINAL_ATTEMPT_STATUSES:
        missing.append("terminal_attempt")
    if policy.require_succeeded_attempt and attempt.status != "succeeded":
        missing.append("succeeded_attempt")
    if task.task_id and attempt.task_id and task.task_id != attempt.task_id:
        missing.append("task_attempt_match")
    if task.task_id and evidence.task_id and task.task_id != evidence.task_id:
        missing.append("task_evidence_match")
    if attempt.attempt_id and evidence.attempt_id and attempt.attempt_id != evidence.attempt_id:
        missing.append("attempt_evidence_match")


def _failed_acceptance_criteria(
    *,
    criteria: Sequence[str],
    results: Mapping[str, bool] | None,
    missing: list[str],
    require_results: bool,
) -> tuple[str, ...]:
    if not criteria:
        return ()
    if results is None:
        if require_results:
            missing.append("acceptance_results")
        return tuple(criteria)

    failed = tuple(criterion for criterion in criteria if results.get(criterion) is not True)
    if failed and require_results and "acceptance_results" not in missing:
        missing.append("acceptance_results")
    return failed
