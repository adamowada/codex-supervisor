"""Persist validated review results into planning evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass

from codex_supervisor.planning import (
    PlanArtifactLinkRecord,
    PlanningSQLiteStore,
    PlanProgressRecord,
)
from codex_supervisor.review_loop import ReviewFinding, ReviewResult, ReviewVerificationEvidence

REVIEW_RESULT_RECORDED_EVENT = "review_result_recorded"
REVIEW_RESULT_ARTIFACT_RELATIONSHIP = "review-result"
REVIEW_ARTIFACT_RELATIONSHIP = "review-artifact"


@dataclass(frozen=True)
class ReviewResultPersistenceRecord:
    """Planning records created for one persisted review result."""

    progress: PlanProgressRecord
    artifact_links: tuple[PlanArtifactLinkRecord, ...]


def record_review_result(
    store: PlanningSQLiteStore,
    *,
    plan_id: str,
    progress_id: str,
    review_result: ReviewResult,
    review_result_artifact_id: str,
    review_artifact_ids: tuple[str, ...] = (),
) -> ReviewResultPersistenceRecord:
    """Record one validated review result as planning progress and artifact links."""

    progress = PlanProgressRecord(
        progress_id=progress_id,
        plan_id=plan_id,
        event_type=REVIEW_RESULT_RECORDED_EVENT,
        summary=_summary(review_result),
        details=json.dumps(_details(review_result), sort_keys=True),
        linked_artifact_id=review_result_artifact_id,
    )
    artifact_links = (
        PlanArtifactLinkRecord(
            plan_id=plan_id,
            artifact_id=review_result_artifact_id,
            relationship=REVIEW_RESULT_ARTIFACT_RELATIONSHIP,
        ),
        *(
            PlanArtifactLinkRecord(
                plan_id=plan_id,
                artifact_id=artifact_id,
                relationship=REVIEW_ARTIFACT_RELATIONSHIP,
            )
            for artifact_id in review_artifact_ids
        ),
    )
    store.add_plan_progress_with_artifact_links(progress, artifact_links)
    return ReviewResultPersistenceRecord(progress=progress, artifact_links=artifact_links)


def _summary(review_result: ReviewResult) -> str:
    counts = _finding_counts(review_result)
    return (
        f"Recorded {review_result.mode} review {review_result.review_id} for "
        f"{review_result.target}: {counts['accepted']} accepted, {counts['waived']} waived, "
        f"{counts['needs_hitl']} needs HITL."
    )


def _details(review_result: ReviewResult) -> dict[str, object]:
    return {
        "review_id": review_result.review_id,
        "mode": review_result.mode,
        "target": review_result.target,
        "finding_counts": _finding_counts(review_result),
        "accepted_findings": tuple(
            _finding_summary(finding) for finding in _accepted(review_result)
        ),
        "waived_findings": tuple(
            _waived_finding_summary(finding) for finding in _waived(review_result)
        ),
        "needs_hitl_findings": tuple(
            _finding_summary(finding) for finding in _needs_hitl(review_result)
        ),
        "verification_evidence": tuple(
            _verification_summary(evidence) for evidence in review_result.verification_evidence
        ),
    }


def _finding_counts(review_result: ReviewResult) -> dict[str, int]:
    return {
        "total": len(review_result.findings),
        "accepted": len(_accepted(review_result)),
        "waived": len(_waived(review_result)),
        "needs_hitl": len(_needs_hitl(review_result)),
    }


def _accepted(review_result: ReviewResult) -> tuple[ReviewFinding, ...]:
    return tuple(finding for finding in review_result.findings if finding.status == "accepted")


def _waived(review_result: ReviewResult) -> tuple[ReviewFinding, ...]:
    return tuple(finding for finding in review_result.findings if finding.status == "waived")


def _needs_hitl(review_result: ReviewResult) -> tuple[ReviewFinding, ...]:
    return tuple(finding for finding in review_result.findings if finding.status == "needs_hitl")


def _finding_summary(finding: ReviewFinding) -> dict[str, str]:
    return {
        "finding_id": finding.finding_id,
        "severity": finding.severity,
        "mode": finding.mode,
        "title": finding.title,
    }


def _waived_finding_summary(finding: ReviewFinding) -> dict[str, str]:
    summary = _finding_summary(finding)
    summary["waiver_rationale"] = str(finding.waiver_rationale)
    return summary


def _verification_summary(evidence: ReviewVerificationEvidence) -> dict[str, object]:
    return {
        "command": evidence.command,
        "exit_code": evidence.exit_code,
        "summary": evidence.summary,
    }
