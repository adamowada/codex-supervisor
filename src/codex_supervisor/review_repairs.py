"""Create planning repair tasks from accepted review findings."""

from __future__ import annotations

import re
from dataclasses import dataclass

from codex_supervisor.planning import (
    PlanningSQLiteStore,
    SupervisorTaskRecord,
    SupervisorTaskSummaryRecord,
)
from codex_supervisor.review_loop import ReviewFinding, ReviewResult, repair_task_draft_from_finding

DEFAULT_REPAIR_VERIFICATION_COMMANDS = ("uv run --no-sync python -B scripts/verify.py",)
REPAIR_TASK_MODE = "review_repair"


class ReviewRepairRoutingError(ValueError):
    """Raised when accepted findings cannot become AFK-ready repair tasks."""


@dataclass(frozen=True)
class SkippedReviewFinding:
    """Review finding intentionally not routed into repair work."""

    finding_id: str
    status: str
    reason: str


@dataclass(frozen=True)
class ReviewRepairRoutingResult:
    """Outcome of routing accepted review findings into planning tasks."""

    created_tasks: tuple[SupervisorTaskRecord, ...]
    existing_task_ids: tuple[str, ...]
    skipped_findings: tuple[SkippedReviewFinding, ...]


def create_repair_tasks_from_review_result(
    store: PlanningSQLiteStore,
    *,
    plan_id: str,
    review_result: ReviewResult,
    source_task_id: str | None = None,
    task_id_prefix: str = "task-review-repair",
    verification_commands: tuple[str, ...] = DEFAULT_REPAIR_VERIFICATION_COMMANDS,
) -> ReviewRepairRoutingResult:
    """Create ready AFK repair tasks for accepted findings in a review result."""

    plan = plan_repair_tasks_from_review_result(
        store,
        plan_id=plan_id,
        review_result=review_result,
        source_task_id=source_task_id,
        task_id_prefix=task_id_prefix,
        verification_commands=verification_commands,
    )
    return apply_repair_task_plan(store, plan)


def plan_repair_tasks_from_review_result(
    store: PlanningSQLiteStore,
    *,
    plan_id: str,
    review_result: ReviewResult,
    source_task_id: str | None = None,
    task_id_prefix: str = "task-review-repair",
    verification_commands: tuple[str, ...] = DEFAULT_REPAIR_VERIFICATION_COMMANDS,
) -> ReviewRepairRoutingResult:
    """Prevalidate accepted review findings and return the repair tasks to create."""

    existing_tasks = {task.task_id: task for task in store.list_supervisor_tasks()}
    created_tasks: list[SupervisorTaskRecord] = []
    existing_routed_ids: list[str] = []
    skipped_findings: list[SkippedReviewFinding] = []

    for finding in review_result.findings:
        if finding.status != "accepted":
            skipped_findings.append(
                SkippedReviewFinding(
                    finding_id=finding.finding_id,
                    status=finding.status,
                    reason=f"{finding.status} findings are retained as review evidence",
                )
            )
            continue
        task = _repair_task_record(
            plan_id=plan_id,
            review_result=review_result,
            finding=finding,
            source_task_id=source_task_id,
            task_id_prefix=task_id_prefix,
            verification_commands=verification_commands,
        )
        existing_task = existing_tasks.get(task.task_id)
        if existing_task is not None:
            _validate_existing_repair_task(existing_task, task, finding=finding)
            existing_routed_ids.append(task.task_id)
            continue
        created_tasks.append(task)

    return ReviewRepairRoutingResult(
        created_tasks=tuple(created_tasks),
        existing_task_ids=tuple(existing_routed_ids),
        skipped_findings=tuple(skipped_findings),
    )


def apply_repair_task_plan(
    store: PlanningSQLiteStore,
    plan: ReviewRepairRoutingResult,
) -> ReviewRepairRoutingResult:
    """Persist a prevalidated repair-task routing plan."""

    for task in plan.created_tasks:
        store.upsert_supervisor_task(task, validate_current_queue_contract=True)
    return plan


def repair_task_id_for_finding(
    review_result: ReviewResult,
    finding: ReviewFinding,
    *,
    task_id_prefix: str = "task-review-repair",
) -> str:
    """Build a deterministic repair task ID for a review finding."""

    return "-".join(
        (
            _slug(task_id_prefix, "task_id_prefix"),
            _slug(review_result.review_id, "review_id"),
            _slug(finding.finding_id, "finding_id"),
        )
    )


def _repair_task_record(
    *,
    plan_id: str,
    review_result: ReviewResult,
    finding: ReviewFinding,
    source_task_id: str | None,
    task_id_prefix: str,
    verification_commands: tuple[str, ...],
) -> SupervisorTaskRecord:
    draft = repair_task_draft_from_finding(finding)
    if not draft.allowed_paths:
        msg = f"accepted finding lacks allowed paths for AFK repair task: {finding.finding_id}"
        raise ReviewRepairRoutingError(msg)
    return SupervisorTaskRecord(
        task_id=repair_task_id_for_finding(
            review_result,
            finding,
            task_id_prefix=task_id_prefix,
        ),
        plan_id=plan_id,
        title=draft.title,
        goal=draft.goal,
        task_type="AFK",
        status="ready",
        scope={
            "mode": REPAIR_TASK_MODE,
            "source_review_id": review_result.review_id,
            "source_review_target": review_result.target,
            "source_finding_id": finding.finding_id,
            "review_mode": draft.review_mode,
            "severity": draft.severity,
        },
        out_of_scope={
            "forbidden": [
                "change files outside allowed_paths",
                "reinterpret waived findings",
                "auto-resolve needs-HITL findings",
            ]
        },
        acceptance_criteria=[
            f"Accepted review finding {finding.finding_id} is fixed with evidence.",
            "Focused verification commands pass after the repair.",
        ],
        verification_commands=list(verification_commands),
        allowed_paths=list(draft.allowed_paths),
        blocked_by=[source_task_id] if source_task_id is not None else [],
        worker_backend="codex_exec",
        review_required=True,
    )


def _validate_existing_repair_task(
    existing: SupervisorTaskSummaryRecord,
    expected: SupervisorTaskRecord,
    *,
    finding: ReviewFinding,
) -> None:
    if _repair_task_contract(existing) == _repair_task_contract(expected):
        return
    msg = (
        f"existing repair task {existing.task_id} does not match review finding "
        f"{finding.finding_id}"
    )
    raise ReviewRepairRoutingError(msg)


def _repair_task_contract(
    task: SupervisorTaskRecord | SupervisorTaskSummaryRecord,
) -> dict[str, object]:
    return {
        "plan_id": task.plan_id,
        "title": task.title,
        "goal": task.goal,
        "task_type": task.task_type,
        "scope": task.scope,
        "out_of_scope": task.out_of_scope,
        "acceptance_criteria": tuple(task.acceptance_criteria),
        "verification_commands": tuple(task.verification_commands),
        "allowed_paths": tuple(task.allowed_paths),
        "blocked_by": tuple(task.blocked_by),
        "worker_backend": task.worker_backend,
        "review_required": task.review_required,
    }


def _slug(value: str, field_name: str) -> str:
    slug = re.sub(r"[^a-z0-9_.:-]+", "-", value.strip().lower()).strip("-")
    if not slug:
        msg = f"{field_name} must contain a slug-safe value"
        raise ReviewRepairRoutingError(msg)
    return slug
