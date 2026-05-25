from __future__ import annotations

import json

import pytest

from codex_supervisor.planning import PlanRecord, SupervisorTaskRecord, initialize_planning_database
from codex_supervisor.review_loop import (
    ReviewFinding,
    ReviewLocation,
    ReviewResult,
    ReviewVerificationEvidence,
)
from codex_supervisor.review_persistence import (
    REVIEW_ARTIFACT_RELATIONSHIP,
    REVIEW_RESULT_ARTIFACT_RELATIONSHIP,
    REVIEW_RESULT_RECORDED_EVENT,
    LiveReviewRunResult,
    ReviewLaunchRequest,
    ReviewLaunchResult,
    record_review_result,
    run_live_review_for_task,
)


def test_record_review_result_persists_progress_details_and_artifact_links(tmp_path) -> None:
    store = _store(tmp_path)
    review_result = _review_result()

    record = record_review_result(
        store,
        plan_id="plan-review",
        progress_id="progress-review-result-001",
        review_result=review_result,
        review_result_artifact_id="insights/review-result.json",
        review_artifact_ids=("insights/review-report.md",),
    )

    progress = store.list_plan_progress(plan_id="plan-review")[0]
    details = json.loads(progress.details or "{}")
    links = store.list_plan_artifact_links(plan_id="plan-review")

    assert record.progress.progress_id == "progress-review-result-001"
    assert progress.event_type == REVIEW_RESULT_RECORDED_EVENT
    assert progress.summary == (
        "Recorded everything review review-stage8c-001 for diff:HEAD~1..HEAD: "
        "1 accepted, 1 waived, 1 needs HITL."
    )
    assert progress.linked_artifact_id == "insights/review-result.json"
    assert details["review_id"] == "review-stage8c-001"
    assert details["finding_counts"] == {
        "accepted": 1,
        "needs_hitl": 1,
        "total": 3,
        "waived": 1,
    }
    assert details["accepted_findings"][0]["finding_id"] == "finding-accepted"
    assert details["waived_findings"][0] == {
        "finding_id": "finding-waived",
        "mode": "architecture",
        "severity": "P3",
        "title": "Split later",
        "waiver_rationale": "No current ownership risk.",
    }
    assert details["needs_hitl_findings"][0]["finding_id"] == "finding-hitl"
    assert details["verification_evidence"] == [
        {
            "command": "uv run --no-sync python -B -m pytest tests/test_review_loop.py",
            "exit_code": 0,
            "summary": "passed",
        }
    ]
    assert {(link.artifact_id, link.relationship) for link in links} == {
        ("insights/review-result.json", REVIEW_RESULT_ARTIFACT_RELATIONSHIP),
        ("insights/review-report.md", REVIEW_ARTIFACT_RELATIONSHIP),
    }


def test_record_review_result_rolls_back_invalid_artifact_links(tmp_path) -> None:
    store = _store(tmp_path)

    with pytest.raises(ValueError, match="unsafe repo-relative artifact path"):
        record_review_result(
            store,
            plan_id="plan-review",
            progress_id="progress-review-result-unsafe",
            review_result=_review_result(),
            review_result_artifact_id="insights/review-result.json",
            review_artifact_ids=("C:unsafe/review.md",),
        )

    assert store.list_plan_progress(plan_id="plan-review") == ()
    assert store.list_plan_artifact_links(plan_id="plan-review") == ()


def test_record_review_result_does_not_create_repair_tasks(tmp_path) -> None:
    store = _store(tmp_path)

    record_review_result(
        store,
        plan_id="plan-review",
        progress_id="progress-review-result-no-tasks",
        review_result=_review_result(),
        review_result_artifact_id="insights/review-result.json",
    )

    assert store.list_supervisor_tasks() == ()


def test_run_live_review_for_task_persists_review_routes_repairs_and_completes_task(
    tmp_path,
) -> None:
    store = _store(tmp_path)
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-source-review",
            plan_id="plan-review",
            title="Source Review",
            goal="Provide completed review evidence.",
            task_type="AFK",
            status="reviewing",
            acceptance_criteria=("Review completed.",),
            verification_commands=("uv run --no-sync python -B scripts/verify.py",),
            allowed_paths=("src/codex_supervisor/review_persistence.py",),
            review_required=True,
        )
    )
    backend = StaticReviewBackend(
        _review_result(
            review_id="review-live-001",
            target="task-source-review",
            include_hitl=False,
        )
    )

    result = run_live_review_for_task(
        store,
        task_id="task-source-review",
        review_id="review-live-001",
        repo_root=tmp_path,
        backend=backend,
        review_result_artifact_id="insights/review-result.md",
        review_artifact_ids=("insights/review-report.md",),
        create_repair_tasks=True,
        repair_verification_commands=("uv run --no-sync python -B scripts/verify.py",),
    )

    tasks = store.list_supervisor_tasks()
    source_task = next(task for task in tasks if task.task_id == "task-source-review")
    repair_task = next(task for task in tasks if task.task_id != "task-source-review")
    progress = store.list_plan_progress(plan_id="plan-review")

    assert isinstance(result, LiveReviewRunResult)
    assert result.status == "completed"
    assert backend.requests[0].task_id == "task-source-review"
    assert backend.requests[0].review_id == "review-live-001"
    assert source_task.status == "completed"
    assert repair_task.status == "ready"
    assert repair_task.scope["source_review_id"] == "review-live-001"
    assert repair_task.scope["source_finding_id"] == "finding-accepted"
    assert progress[0].event_type == REVIEW_RESULT_RECORDED_EVENT
    assert result.created_repair_task_ids == (
        "task-review-repair-review-live-001-finding-accepted",
    )


def test_run_live_review_for_task_keeps_task_reviewing_when_hitl_is_needed(tmp_path) -> None:
    store = _store(tmp_path)
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-source-review",
            plan_id="plan-review",
            title="Source Review",
            goal="Provide completed review evidence.",
            task_type="AFK",
            status="reviewing",
            acceptance_criteria=("Review completed.",),
            verification_commands=("uv run --no-sync python -B scripts/verify.py",),
            allowed_paths=("src/codex_supervisor/review_persistence.py",),
            review_required=True,
        )
    )
    backend = StaticReviewBackend(_hitl_review_result())

    result = run_live_review_for_task(
        store,
        task_id="task-source-review",
        review_id="review-hitl-001",
        repo_root=tmp_path,
        backend=backend,
        review_result_artifact_id="insights/review-result.md",
    )

    source_task = store.list_supervisor_tasks()[0]

    assert result.status == "needs_hitl"
    assert source_task.status == "reviewing"
    assert result.created_repair_task_ids == ()


def _store(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-review",
            slug="review",
            title="Review Plan",
            goal="Persist review results.",
            status="active",
        )
    )
    return store


class StaticReviewBackend:
    def __init__(self, review_result: ReviewResult) -> None:
        self.review_result = review_result
        self.requests: list[ReviewLaunchRequest] = []

    def run(self, request: ReviewLaunchRequest) -> ReviewLaunchResult:
        self.requests.append(request)
        return ReviewLaunchResult(
            review_id=request.review_id,
            task_id=request.task_id,
            status="completed",
            review_result=self.review_result,
            result_path=request.result_path,
        )


def _review_result(
    review_id: str = "review-stage8c-001",
    target: str = "diff:HEAD~1..HEAD",
    include_hitl: bool = True,
) -> ReviewResult:
    findings: list[ReviewFinding] = [
        ReviewFinding(
            finding_id="finding-accepted",
            mode="code_quality",
            severity="P2",
            status="accepted",
            title="Missing persistence test",
            evidence="Accepted findings should become follow-up work later.",
            location=ReviewLocation(path="src/codex_supervisor/review_persistence.py"),
            recommendation="Persist the finding first.",
            allowed_paths=("src/codex_supervisor/review_persistence.py",),
        ),
        ReviewFinding(
            finding_id="finding-waived",
            mode="architecture",
            severity="P3",
            status="waived",
            title="Split later",
            evidence="The persistence helper is still small.",
            location=ReviewLocation(scope="review persistence helper"),
            recommendation="Defer extraction.",
            waiver_rationale="No current ownership risk.",
        ),
    ]
    if include_hitl:
        findings.append(
            ReviewFinding(
                finding_id="finding-hitl",
                mode="source_of_truth_drift",
                severity="P1",
                status="needs_hitl",
                title="Policy decision needed",
                evidence="The review result needs human interpretation.",
                location=ReviewLocation(scope="Stage 8 review policy"),
                recommendation="Ask for HITL confirmation.",
            )
        )
    return ReviewResult(
        review_id=review_id,
        mode="everything",
        target=target,
        findings=tuple(findings),
        verification_evidence=(
            ReviewVerificationEvidence(
                command="uv run --no-sync python -B -m pytest tests/test_review_loop.py",
                exit_code=0,
                summary="passed",
            ),
        ),
    )


def _hitl_review_result() -> ReviewResult:
    return ReviewResult(
        review_id="review-hitl-001",
        mode="everything",
        target="task-source-review",
        findings=(
            ReviewFinding(
                finding_id="finding-hitl",
                mode="source_of_truth_drift",
                severity="P1",
                status="needs_hitl",
                title="Needs policy decision",
                evidence="The reviewer needs human interpretation.",
                location=ReviewLocation(scope="review policy"),
                recommendation="Ask for HITL confirmation.",
            ),
        ),
        verification_evidence=(
            ReviewVerificationEvidence(
                command="uv run --no-sync python -B -m pytest tests/test_review_persistence.py",
                exit_code=0,
                summary="passed",
            ),
        ),
    )
