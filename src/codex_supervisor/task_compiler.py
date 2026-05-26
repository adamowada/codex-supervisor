"""Deterministic compiler from plan criteria and milestones to supervisor tasks."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from codex_supervisor.planning import (
    OPEN_CRITERION_STATUSES,
    OPEN_MILESTONE_STATUSES,
    PlanningSQLiteStore,
    SupervisorTaskRecord,
)


@dataclass(frozen=True)
class TaskCompilationReport:
    """Dry-run or applied task compilation output."""

    plan_id: str
    status: str
    tasks: tuple[SupervisorTaskRecord, ...]


def compile_tasks_from_plan(
    store: PlanningSQLiteStore,
    *,
    plan_id: str,
    allowed_paths: tuple[str, ...],
    verification_commands: tuple[str, ...] = (),
    status: str = "pending",
    worker_backend: str = "codex_exec",
    review_required: bool = True,
) -> TaskCompilationReport:
    """Compile open plan criteria or milestones into stable AFK task drafts."""

    snapshot = store.read_summary_snapshot()
    plan = next((candidate for candidate in snapshot.plans if candidate.plan_id == plan_id), None)
    if plan is None:
        raise ValueError(f"plan_id does not exist: {plan_id}")
    criteria = tuple(
        criterion
        for criterion in snapshot.criteria
        if criterion.plan_id == plan_id and criterion.status in OPEN_CRITERION_STATUSES
    )
    milestones = tuple(
        milestone
        for milestone in snapshot.milestones
        if milestone.plan_id == plan_id and milestone.status in OPEN_MILESTONE_STATUSES
    )
    existing_ids = {task.task_id for task in snapshot.tasks}
    if criteria:
        tasks = tuple(
            _task_from_criterion(
                plan_id=plan_id,
                plan_goal=plan.goal,
                criterion_id=criterion.criterion_id,
                description=criterion.description,
                verification_command=criterion.verification_command,
                allowed_paths=allowed_paths,
                fallback_verification_commands=verification_commands,
                status=status,
                worker_backend=worker_backend,
                review_required=review_required,
                existing_ids=existing_ids,
            )
            for criterion in criteria
        )
    else:
        tasks = tuple(
            _task_from_milestone(
                plan_id=plan_id,
                plan_goal=plan.goal,
                milestone_id=milestone.milestone_id,
                title=milestone.title,
                allowed_paths=allowed_paths,
                verification_commands=verification_commands,
                status=status,
                worker_backend=worker_backend,
                review_required=review_required,
                existing_ids=existing_ids,
            )
            for milestone in milestones
        )
    return TaskCompilationReport(plan_id=plan_id, status="compiled", tasks=tasks)


def apply_compiled_tasks(
    store: PlanningSQLiteStore,
    report: TaskCompilationReport,
    *,
    validate_current_queue_contract: bool = True,
) -> TaskCompilationReport:
    """Persist compiled task drafts into planning SQLite."""

    for task in report.tasks:
        store.upsert_supervisor_task(
            task,
            validate_current_queue_contract=validate_current_queue_contract,
        )
    return TaskCompilationReport(plan_id=report.plan_id, status="applied", tasks=report.tasks)


def _task_from_criterion(
    *,
    plan_id: str,
    plan_goal: str,
    criterion_id: str,
    description: str,
    verification_command: str | None,
    allowed_paths: tuple[str, ...],
    fallback_verification_commands: tuple[str, ...],
    status: str,
    worker_backend: str,
    review_required: bool,
    existing_ids: set[str],
) -> SupervisorTaskRecord:
    task_id = _stable_task_id("criterion", criterion_id, existing_ids)
    verification = (
        (verification_command.strip(),)
        if verification_command is not None and verification_command.strip()
        else fallback_verification_commands
    )
    return SupervisorTaskRecord(
        task_id=task_id,
        plan_id=plan_id,
        title=f"Satisfy criterion: {_compact_title(description)}",
        goal=(
            f"Deliver one vertical slice for plan `{plan_id}` that satisfies acceptance "
            f"criterion `{criterion_id}`: {description}\n\nPlan goal: {plan_goal}"
        ),
        task_type="AFK",
        status=status,
        scope={"compiled_from": "plan_acceptance_criterion", "criterion_id": criterion_id},
        out_of_scope={
            "compiler_boundary": (
                "Do not broaden scope beyond the named criterion without a separate task."
            )
        },
        acceptance_criteria=[description],
        verification_commands=list(verification),
        allowed_paths=list(allowed_paths),
        blocked_by=[],
        worker_backend=worker_backend,
        review_required=review_required,
    )


def _task_from_milestone(
    *,
    plan_id: str,
    plan_goal: str,
    milestone_id: str,
    title: str,
    allowed_paths: tuple[str, ...],
    verification_commands: tuple[str, ...],
    status: str,
    worker_backend: str,
    review_required: bool,
    existing_ids: set[str],
) -> SupervisorTaskRecord:
    task_id = _stable_task_id("milestone", milestone_id, existing_ids)
    return SupervisorTaskRecord(
        task_id=task_id,
        plan_id=plan_id,
        title=f"Advance milestone: {_compact_title(title)}",
        goal=(
            f"Deliver the smallest vertical slice that advances milestone `{milestone_id}`: "
            f"{title}\n\nPlan goal: {plan_goal}"
        ),
        task_type="AFK",
        status=status,
        scope={"compiled_from": "plan_milestone", "milestone_id": milestone_id},
        out_of_scope={
            "compiler_boundary": ("Do not complete unrelated milestones or criteria in this task.")
        },
        acceptance_criteria=[f"Milestone `{milestone_id}` is materially advanced: {title}"],
        verification_commands=list(verification_commands),
        allowed_paths=list(allowed_paths),
        blocked_by=[],
        worker_backend=worker_backend,
        review_required=review_required,
    )


def _stable_task_id(source_kind: str, source_id: str, existing_ids: set[str]) -> str:
    slug = _slug(source_id)
    digest = hashlib.sha256(f"{source_kind}:{source_id}".encode()).hexdigest()[:8]
    task_id = f"task-{source_kind}-{slug}-{digest}"
    if task_id in existing_ids:
        return task_id
    return task_id


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-").lower()
    return cleaned[:40] or "item"


def _compact_title(value: str) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= 80:
        return normalized
    return normalized[:77].rstrip() + "..."
