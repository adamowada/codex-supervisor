from __future__ import annotations

import pytest

from codex_supervisor.review_loop import (
    FINDING_SEVERITIES,
    FINDING_STATUSES,
    REVIEW_MODES,
    RepairTaskDraft,
    ReviewContractError,
    ReviewFinding,
    ReviewLocation,
    repair_task_draft_from_finding,
)


def test_review_finding_contract_accepts_explicit_vocabularies() -> None:
    finding = ReviewFinding(
        finding_id="finding-stage8a-001",
        mode="everything",
        severity="P1",
        status="accepted",
        title="Completion path skips worker result validation",
        evidence="worker-run-status can complete without loading the result artifact.",
        location=ReviewLocation(path="src/codex_supervisor/cli.py", line=1025),
        recommendation="Route completion through validate_worker_result_file.",
    )

    assert REVIEW_MODES == (
        "everything",
        "code_quality",
        "architecture",
        "source_of_truth_drift",
    )
    assert FINDING_SEVERITIES == ("P0", "P1", "P2", "P3")
    assert FINDING_STATUSES == ("accepted", "waived", "needs_hitl")
    assert finding.location.path == "src/codex_supervisor/cli.py"
    assert finding.location.line == 1025


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mode", "security"),
        ("severity", "critical"),
        ("status", "ignored"),
    ],
)
def test_review_finding_rejects_invalid_vocabularies(field: str, value: str) -> None:
    values = {
        "finding_id": "finding-stage8a-001",
        "mode": "everything",
        "severity": "P2",
        "status": "accepted",
        "title": "Bad value",
        "evidence": "Evidence exists.",
        "location": ReviewLocation(scope="whole repo"),
        "recommendation": "Fix it.",
    }
    values[field] = value

    with pytest.raises(ReviewContractError, match=field):
        ReviewFinding(**values)


def test_review_finding_requires_location_or_scope() -> None:
    with pytest.raises(ReviewContractError, match="path or scope"):
        ReviewLocation()


def test_waived_review_finding_requires_rationale() -> None:
    with pytest.raises(ReviewContractError, match="waiver_rationale"):
        ReviewFinding(
            finding_id="finding-stage8a-002",
            mode="architecture",
            severity="P3",
            status="waived",
            title="Low-risk layering preference",
            evidence="The module could be split later.",
            location=ReviewLocation(scope="review_loop contract"),
            recommendation="Leave as is for now.",
        )

    finding = ReviewFinding(
        finding_id="finding-stage8a-003",
        mode="architecture",
        severity="P3",
        status="waived",
        title="Low-risk layering preference",
        evidence="The module could be split later.",
        location=ReviewLocation(scope="review_loop contract"),
        recommendation="Leave as is for now.",
        waiver_rationale="No user-facing behavior or testability risk in this slice.",
    )
    assert finding.waiver_rationale == "No user-facing behavior or testability risk in this slice."


def test_accepted_review_finding_becomes_repair_task_draft() -> None:
    finding = ReviewFinding(
        finding_id="finding-stage8a-004",
        mode="code_quality",
        severity="P2",
        status="accepted",
        title="Duplicate parsing logic",
        evidence="Two modules parse the same JSON payload shape.",
        location=ReviewLocation(path="src/codex_supervisor/review_loop.py"),
        recommendation="Extract a shared parser and add focused tests.",
        allowed_paths=("src/codex_supervisor/review_loop.py", "tests/test_review_loop.py"),
    )

    draft = repair_task_draft_from_finding(finding)

    assert draft == RepairTaskDraft(
        source_finding_id="finding-stage8a-004",
        review_mode="code_quality",
        severity="P2",
        title="Fix P2 review finding: Duplicate parsing logic",
        goal=(
            "Fix accepted P2 review finding finding-stage8a-004: Duplicate parsing logic. "
            "Evidence: Two modules parse the same JSON payload shape. "
            "Recommendation: Extract a shared parser and add focused tests."
        ),
        allowed_paths=("src/codex_supervisor/review_loop.py", "tests/test_review_loop.py"),
    )


def test_non_accepted_finding_cannot_become_repair_task_draft() -> None:
    finding = ReviewFinding(
        finding_id="finding-stage8a-005",
        mode="source_of_truth_drift",
        severity="P2",
        status="needs_hitl",
        title="Potential doctrine mismatch",
        evidence="The finding needs human confirmation.",
        location=ReviewLocation(scope="ROADMAP.md Stage 8"),
        recommendation="Ask for HITL confirmation.",
    )

    with pytest.raises(ReviewContractError, match="only accepted findings"):
        repair_task_draft_from_finding(finding)
