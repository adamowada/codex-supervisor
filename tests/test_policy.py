from __future__ import annotations

import pytest

from codex_supervisor.policy import (
    AssuranceLevel,
    AttemptRecord,
    EvidenceBundle,
    TaskIntent,
    evaluate_acceptance,
    evaluate_task_attempt_acceptance,
    normalize_assurance,
    policy_for_assurance,
    task_intent_policy,
)


def test_policy_defines_evidence_requirements_for_each_assurance_level() -> None:
    low = policy_for_assurance(AssuranceLevel.LOW)
    medium = policy_for_assurance("medium")
    high = policy_for_assurance(AssuranceLevel.HIGH)

    assert low.require_risk_or_gap_notes is True
    assert low.require_next_action is True
    assert low.require_focused_checks is False
    assert medium.require_focused_checks is True
    assert medium.require_artifacts is True
    assert medium.require_acceptance_criteria is True
    assert high.require_strict_checks is True
    assert high.require_risk_notes is True
    assert high.require_review_when_requested is True


def test_task_intent_policy_uses_explicit_assurance() -> None:
    assert task_intent_policy(assurance="medium").level == AssuranceLevel.MEDIUM


def test_low_assurance_accepts_summary_with_next_action() -> None:
    evaluation = evaluate_acceptance(
        TaskIntent(
            intent="Explore policy shape",
            assurance=AssuranceLevel.LOW,
        ),
        EvidenceBundle(
            summary="Found a small policy surface.",
            gaps=("The acceptance gate does not exist yet.",),
            next_actions=("Implement medium and high evidence checks.",),
        ),
    )

    assert evaluation.accepted is True
    assert evaluation.missing_requirements == ()


def test_medium_assurance_requires_checks_artifacts_and_acceptance_results() -> None:
    task = TaskIntent(
        intent="Implement policy core",
        assurance=AssuranceLevel.MEDIUM,
        acceptance_criteria=("Policy exists", "Tests cover policy"),
    )

    evaluation = evaluate_acceptance(
        task,
        EvidenceBundle(
            summary="Policy module added.",
            checks=("pytest tests/test_policy.py",),
            artifacts=("src/codex_supervisor/policy.py",),
            acceptance_results={"Policy exists": True, "Tests cover policy": True},
        ),
    )

    assert evaluation.accepted is True


def test_high_assurance_requires_risk_notes_and_review_when_requested() -> None:
    task = TaskIntent(
        intent="Update source-of-truth policy",
        assurance=AssuranceLevel.HIGH,
        acceptance_criteria=("Hashes refreshed",),
        review_required=True,
    )

    evaluation = evaluate_acceptance(
        task,
        EvidenceBundle(
            summary="Updated policy.",
            strict_checks=("scripts/verify.py",),
            artifacts=("ROADMAP.md",),
            acceptance_results={"Hashes refreshed": True},
        ),
    )

    assert evaluation.accepted is False
    assert "risk_notes" in evaluation.missing_requirements
    assert "review_evidence" in evaluation.missing_requirements
    assert "strict_checks" not in evaluation.missing_requirements


def test_high_assurance_accepts_task_attempt_and_evidence_records() -> None:
    task = TaskIntent(
        task_id="task-1",
        intent="Update source-of-truth policy",
        assurance="high",
        acceptance_criteria=("Policy exists",),
        review_required=True,
    )
    attempt = AttemptRecord(
        attempt_id="attempt-1",
        task_id="task-1",
        status="succeeded",
    )
    evidence = EvidenceBundle(
        task_id="task-1",
        attempt_id="attempt-1",
        summary="Policy module added.",
        strict_checks=("uv run --no-sync python -B scripts/verify.py",),
        artifacts=("src/codex_supervisor/policy.py", "tests/test_policy.py"),
        acceptance_results={"Policy exists": True},
        risks=("Policy must stay independent from transport layers.",),
        review_evidence=("Proposal-only subagent review agreed on pure policy core.",),
    )

    evaluation = evaluate_task_attempt_acceptance(task, attempt, evidence)

    assert evaluation.accepted is True


def test_medium_and_high_require_a_succeeded_attempt_when_attempt_is_supplied() -> None:
    evaluation = evaluate_task_attempt_acceptance(
        TaskIntent(
            task_id="task-1",
            intent="Implement policy core",
            assurance=AssuranceLevel.MEDIUM,
            acceptance_criteria=("Policy exists",),
        ),
        AttemptRecord(
            attempt_id="attempt-1",
            task_id="task-1",
            status="blocked",
        ),
        EvidenceBundle(
            task_id="task-1",
            attempt_id="attempt-1",
            summary="Policy module added.",
            checks=("pytest tests/test_policy.py",),
            artifacts=("src/codex_supervisor/policy.py",),
            acceptance_results={"Policy exists": True},
        ),
    )

    assert evaluation.accepted is False
    assert "succeeded_attempt" in evaluation.missing_requirements


def test_failed_acceptance_criteria_block_acceptance() -> None:
    evaluation = evaluate_acceptance(
        TaskIntent(
            intent="Implement policy core",
            assurance=AssuranceLevel.MEDIUM,
            acceptance_criteria=("Policy exists", "Tests cover policy"),
        ),
        EvidenceBundle(
            summary="Policy module added.",
            checks=("pytest tests/test_policy.py",),
            artifacts=("src/codex_supervisor/policy.py",),
            acceptance_results={"Policy exists": True, "Tests cover policy": False},
        ),
    )

    assert evaluation.accepted is False
    assert evaluation.failed_acceptance_criteria == ("Tests cover policy",)


def test_unknown_assurance_fails_with_clear_message() -> None:
    with pytest.raises(ValueError, match="unknown assurance level"):
        normalize_assurance("urgent")
