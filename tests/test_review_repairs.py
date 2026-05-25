from __future__ import annotations

import pytest

from codex_supervisor.planning import (
    PlanRecord,
    SupervisorTaskRecord,
    initialize_planning_database,
)
from codex_supervisor.review_loop import (
    ReviewFinding,
    ReviewLocation,
    ReviewResult,
    ReviewVerificationEvidence,
)
from codex_supervisor.review_repairs import (
    REPAIR_TASK_MODE,
    ReviewRepairRoutingError,
    create_repair_tasks_from_review_result,
    repair_task_id_for_finding,
)


def test_accepted_review_findings_create_ready_repair_tasks(tmp_path) -> None:
    store = _store(tmp_path)
    review_result = _review_result()

    result = create_repair_tasks_from_review_result(
        store,
        plan_id="plan-review",
        review_result=review_result,
        source_task_id="task-source-review",
        verification_commands=("uv run --no-sync python -B scripts/verify.py",),
    )

    tasks = store.list_supervisor_tasks()

    assert len(result.created_tasks) == 1
    assert result.existing_task_ids == ()
    assert [(finding.finding_id, finding.status) for finding in result.skipped_findings] == [
        ("finding-waived", "waived"),
        ("finding-hitl", "needs_hitl"),
    ]
    assert len(tasks) == 2
    repair_task = next(task for task in tasks if task.task_id != "task-source-review")
    assert repair_task.task_id == "task-review-repair-review-stage8d-001-finding-accepted"
    assert repair_task.status == "ready"
    assert repair_task.task_type == "AFK"
    assert repair_task.scope["mode"] == REPAIR_TASK_MODE
    assert repair_task.scope["source_review_id"] == "review-stage8d-001"
    assert repair_task.scope["source_finding_id"] == "finding-accepted"
    assert repair_task.blocked_by == ["task-source-review"]
    assert repair_task.allowed_paths == ["src/codex_supervisor/review_repairs.py"]
    assert repair_task.verification_commands == ["uv run --no-sync python -B scripts/verify.py"]
    assert repair_task.review_required is True


def test_review_repair_task_routing_is_idempotent(tmp_path) -> None:
    store = _store(tmp_path)
    review_result = _review_result()

    first = create_repair_tasks_from_review_result(
        store,
        plan_id="plan-review",
        review_result=review_result,
        source_task_id="task-source-review",
    )
    second = create_repair_tasks_from_review_result(
        store,
        plan_id="plan-review",
        review_result=review_result,
        source_task_id="task-source-review",
    )

    assert len(first.created_tasks) == 1
    assert second.created_tasks == ()
    assert second.existing_task_ids == ("task-review-repair-review-stage8d-001-finding-accepted",)
    assert len(store.list_supervisor_tasks()) == 2


def test_review_repair_routing_rejects_existing_id_with_different_contract(tmp_path) -> None:
    store = _store(tmp_path)
    review_result = _review_result()
    finding = review_result.accepted_findings[0]
    collision_id = repair_task_id_for_finding(review_result, finding)
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id=collision_id,
            plan_id="plan-review",
            title="Different repair",
            goal="This is not the deterministic review repair task.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=("Different.",),
            verification_commands=("uv run --no-sync python -B scripts/verify.py",),
            allowed_paths=("README.md",),
            review_required=True,
        )
    )

    with pytest.raises(ReviewRepairRoutingError, match="does not match review finding"):
        create_repair_tasks_from_review_result(
            store,
            plan_id="plan-review",
            review_result=review_result,
            source_task_id="task-source-review",
        )

    assert len(store.list_supervisor_tasks()) == 2


def test_review_repair_routing_rejects_accepted_findings_without_allowed_paths(tmp_path) -> None:
    store = _store(tmp_path)
    review_result = ReviewResult(
        review_id="review-stage8d-unsafe",
        mode="everything",
        target="diff:HEAD",
        findings=(
            ReviewFinding(
                finding_id="finding-scope-only",
                mode="architecture",
                severity="P2",
                status="accepted",
                title="Needs design work",
                evidence="The finding is not tied to a file.",
                location=ReviewLocation(scope="architecture"),
                recommendation="Add a file-scoped repair task.",
            ),
        ),
        verification_evidence=(
            ReviewVerificationEvidence(command="pytest", exit_code=0, summary="passed"),
        ),
    )

    with pytest.raises(ReviewRepairRoutingError, match="lacks allowed paths"):
        create_repair_tasks_from_review_result(
            store,
            plan_id="plan-review",
            review_result=review_result,
        )

    assert len(store.list_supervisor_tasks()) == 1


def test_repair_task_id_for_finding_is_deterministic_and_slug_safe() -> None:
    review_result = _review_result(review_id="Review Stage8D #1")
    finding = review_result.accepted_findings[0]

    assert (
        repair_task_id_for_finding(review_result, finding, task_id_prefix="Task Repair")
        == "task-repair-review-stage8d-1-finding-accepted"
    )


def _store(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-review",
            slug="review",
            title="Review Plan",
            goal="Route repair tasks.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-source-review",
            plan_id="plan-review",
            title="Source Review",
            goal="Provide completed review evidence.",
            task_type="AFK",
            status="completed",
            acceptance_criteria=("Review completed.",),
            verification_commands=("uv run --no-sync python -B scripts/verify.py",),
            allowed_paths=("src/codex_supervisor/review_repairs.py",),
        )
    )
    return store


def _review_result(review_id: str = "review-stage8d-001") -> ReviewResult:
    return ReviewResult(
        review_id=review_id,
        mode="everything",
        target="diff:HEAD~1..HEAD",
        findings=(
            ReviewFinding(
                finding_id="finding-accepted",
                mode="code_quality",
                severity="P2",
                status="accepted",
                title="Missing repair routing",
                evidence="Accepted findings should become repair tasks.",
                location=ReviewLocation(path="src/codex_supervisor/review_repairs.py"),
                recommendation="Create a focused repair task.",
            ),
            ReviewFinding(
                finding_id="finding-waived",
                mode="architecture",
                severity="P3",
                status="waived",
                title="Can defer split",
                evidence="The helper is still small.",
                location=ReviewLocation(scope="review repair routing"),
                recommendation="Keep the module together for now.",
                waiver_rationale="No current readability risk.",
            ),
            ReviewFinding(
                finding_id="finding-hitl",
                mode="source_of_truth_drift",
                severity="P1",
                status="needs_hitl",
                title="Needs policy call",
                evidence="A human should decide whether this is accepted.",
                location=ReviewLocation(scope="review policy"),
                recommendation="Ask for HITL confirmation.",
            ),
        ),
        verification_evidence=(
            ReviewVerificationEvidence(
                command="uv run --no-sync python -B scripts/verify.py",
                exit_code=0,
                summary="passed",
            ),
        ),
    )
