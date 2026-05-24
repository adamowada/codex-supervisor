"""Story Loop status and progress helpers."""

from __future__ import annotations

from dataclasses import dataclass

from codex_supervisor.planning import (
    CURRENT_QUEUE_PLAN_STATUSES,
    OPEN_CRITERION_STATUSES,
    OPEN_TASK_STATUSES,
    PlanAcceptanceCriterionRecord,
    PlanArtifactLinkRecord,
    PlanningSQLiteStore,
    PlanProgressRecord,
    PlanRecord,
    SupervisorTaskSummaryRecord,
    WorkerRunRecord,
    has_nonterminal_worker_run,
    has_unresolved_task_blockers,
    is_executable_afk_task,
    missing_execution_contract_fields,
)


@dataclass(frozen=True)
class StoryLoopPlanStatus:
    plan_id: str
    title: str
    plan_status: str
    priority: int
    state: str
    summary: str
    current_task_id: str | None
    running_task_ids: tuple[str, ...]
    ready_task_ids: tuple[str, ...]
    blocked_task_ids: tuple[str, ...]
    hitl_task_ids: tuple[str, ...]
    pending_task_ids: tuple[str, ...]
    open_task_ids: tuple[str, ...]
    pending_criterion_ids: tuple[str, ...]


@dataclass(frozen=True)
class StoryLoopStatus:
    queue_state: str
    current_task_id: str | None
    current_running_task_id: str | None
    current_hitl_task_id: str | None
    current_afk_task: SupervisorTaskSummaryRecord | None
    plans: tuple[StoryLoopPlanStatus, ...]
    current_task: SupervisorTaskSummaryRecord | None


@dataclass(frozen=True)
class StoryLoopRecordResult:
    progress: PlanProgressRecord
    artifact_links: tuple[PlanArtifactLinkRecord, ...]


def build_story_loop_status(
    store: PlanningSQLiteStore,
    *,
    active_only: bool = True,
    plan_id: str | None = None,
) -> StoryLoopStatus:
    """Build Story Loop status from planning helpers."""

    plans = _select_plans(store.list_plans(), active_only=active_only, plan_id=plan_id)
    tasks = store.list_supervisor_tasks()
    worker_runs = store.list_worker_runs()
    criteria = store.list_plan_acceptance_criteria()
    selected_plan_ids = {plan.plan_id for plan in plans}
    plan_statuses = tuple(
        _build_plan_status(
            plan,
            tuple(task for task in tasks if task.plan_id == plan.plan_id),
            tasks,
            tuple(
                run
                for run in worker_runs
                if _task_belongs_to_plan(run.task_id, tasks, plan.plan_id)
            ),
            tuple(criterion for criterion in criteria if criterion.plan_id == plan.plan_id),
        )
        for plan in plans
    )
    current_running_task_id = _current_running_task_id(plan_statuses)
    current_afk_task = (
        next(
            (
                task
                for task in tasks
                if task.plan_id in selected_plan_ids
                and is_executable_afk_task(task, tasks, worker_runs)
            ),
            None,
        )
        if current_running_task_id is None
        else None
    )
    queue_state = _queue_state(plan_statuses, current_afk_task)
    current_hitl_task_id = (
        _current_hitl_task_id(plan_statuses)
        if current_afk_task is None and current_running_task_id is None
        else None
    )
    current_task_id = (
        current_afk_task.task_id
        if current_afk_task is not None
        else current_running_task_id or current_hitl_task_id
    )
    current_task = _task_by_id(tasks, current_task_id)
    return StoryLoopStatus(
        queue_state=queue_state,
        current_task_id=current_task_id,
        current_running_task_id=current_running_task_id,
        current_hitl_task_id=current_hitl_task_id,
        current_afk_task=current_afk_task,
        plans=plan_statuses,
        current_task=current_task,
    )


def record_story_loop_progress(
    store: PlanningSQLiteStore,
    *,
    progress_id: str,
    plan_id: str,
    event_type: str,
    summary: str,
    details: str | None,
    artifact_ids: tuple[str, ...],
    artifact_relationship: str,
    task_id: str | None = None,
    worker_run_id: str | None = None,
    linked_artifact_id: str | None = None,
) -> StoryLoopRecordResult:
    """Record one Story Loop progress event and its artifact links."""

    _validate_story_loop_references(
        store,
        plan_id=plan_id,
        task_id=task_id,
        worker_run_id=worker_run_id,
    )
    metadata_details = _append_iteration_metadata(
        details,
        task_id=task_id,
        worker_run_id=worker_run_id,
    )
    progress = PlanProgressRecord(
        progress_id=progress_id,
        plan_id=plan_id,
        event_type=event_type,
        summary=summary,
        details=metadata_details,
        linked_artifact_id=linked_artifact_id or _first_or_none(artifact_ids),
    )
    artifact_links = tuple(
        PlanArtifactLinkRecord(
            plan_id=plan_id,
            artifact_id=artifact_id,
            relationship=artifact_relationship,
        )
        for artifact_id in artifact_ids
    )
    store.add_plan_progress_with_artifact_links(progress, artifact_links)
    return StoryLoopRecordResult(progress=progress, artifact_links=artifact_links)


def _select_plans(
    plans: tuple[PlanRecord, ...],
    *,
    active_only: bool,
    plan_id: str | None,
) -> tuple[PlanRecord, ...]:
    selected = plans
    if plan_id is not None:
        selected = tuple(plan for plan in selected if plan.plan_id == plan_id)
    if active_only:
        selected = tuple(plan for plan in selected if plan.status in CURRENT_QUEUE_PLAN_STATUSES)
    return selected


def _build_plan_status(
    plan: PlanRecord,
    tasks: tuple[SupervisorTaskSummaryRecord, ...],
    all_tasks: tuple[SupervisorTaskSummaryRecord, ...],
    worker_runs: tuple[WorkerRunRecord, ...],
    criteria: tuple[PlanAcceptanceCriterionRecord, ...],
) -> StoryLoopPlanStatus:
    open_tasks = tuple(task for task in tasks if task.status in OPEN_TASK_STATUSES)
    hitl_tasks = tuple(
        task
        for task in open_tasks
        if (
            (task.task_type == "HITL" and task.status == "ready")
            or task.status == "reviewing"
            or _has_worker_run_status(task.task_id, worker_runs, {"needs_review"})
        )
        and not has_unresolved_task_blockers(task, all_tasks)
    )
    ready_tasks = tuple(
        task for task in open_tasks if is_executable_afk_task(task, all_tasks, worker_runs)
    )
    running_tasks = tuple(
        task
        for task in open_tasks
        if task.status == "running"
        or _has_worker_run_status(task.task_id, worker_runs, {"queued", "running"})
    )
    running_task_ids = {task.task_id for task in running_tasks}
    hitl_task_ids = {task.task_id for task in hitl_tasks}
    pending_tasks = tuple(task for task in open_tasks if task.status == "pending")
    blocked_tasks = tuple(
        task
        for task in open_tasks
        if task.task_id not in running_task_ids
        and task.task_id not in hitl_task_ids
        and (
            task.status == "blocked"
            or plan.status == "blocked"
            or has_unresolved_task_blockers(task, all_tasks)
            or _has_worker_run_status(task.task_id, worker_runs, {"blocked"})
            or (
                task.task_type == "AFK"
                and task.status == "ready"
                and (
                    bool(missing_execution_contract_fields(task))
                    or has_nonterminal_worker_run(task.task_id, worker_runs)
                )
            )
        )
    )
    pending_criteria = tuple(
        criterion for criterion in criteria if criterion.status in OPEN_CRITERION_STATUSES
    )

    if running_tasks:
        state = "running"
        summary = f"Worker already claimed task: {running_tasks[0].task_id}"
        current_task_id = running_tasks[0].task_id
    elif ready_tasks:
        state = "ready"
        summary = f"Next ready AFK task: {ready_tasks[0].task_id}"
        current_task_id = ready_tasks[0].task_id
    elif hitl_tasks:
        state = "hitl"
        summary = f"Human input required for task: {hitl_tasks[0].task_id}"
        current_task_id = hitl_tasks[0].task_id
    elif pending_tasks:
        state = "blocked"
        summary = f"Pending task is not ready yet: {pending_tasks[0].task_id}"
        current_task_id = None
    elif open_tasks:
        state = "blocked"
        summary = "Open work exists, but no unblocked ready AFK task is available."
        current_task_id = None
    elif tasks or criteria:
        state = "completed" if not pending_criteria else "blocked"
        summary = "No open work remains." if state == "completed" else "Criteria remain pending."
        current_task_id = None
    else:
        state = "empty"
        summary = "No supervisor tasks or acceptance criteria are defined."
        current_task_id = None

    return StoryLoopPlanStatus(
        plan_id=plan.plan_id,
        title=plan.title,
        plan_status=plan.status,
        priority=plan.priority,
        state=state,
        summary=summary,
        current_task_id=current_task_id,
        running_task_ids=tuple(task.task_id for task in running_tasks),
        ready_task_ids=tuple(task.task_id for task in ready_tasks),
        blocked_task_ids=tuple(task.task_id for task in blocked_tasks),
        hitl_task_ids=tuple(task.task_id for task in hitl_tasks),
        pending_task_ids=tuple(task.task_id for task in pending_tasks),
        open_task_ids=tuple(task.task_id for task in open_tasks),
        pending_criterion_ids=tuple(criterion.criterion_id for criterion in pending_criteria),
    )


def _validate_story_loop_references(
    store: PlanningSQLiteStore,
    *,
    plan_id: str,
    task_id: str | None,
    worker_run_id: str | None,
) -> None:
    tasks = store.list_supervisor_tasks()
    task = _task_by_id(tasks, task_id)
    if task_id is not None and task is None:
        raise ValueError(f"task_id does not exist: {task_id}")
    if task is not None and task.plan_id != plan_id:
        raise ValueError(f"task_id {task_id} belongs to {task.plan_id}, not {plan_id}")
    if worker_run_id is None:
        return
    worker_run = next(
        (run for run in store.list_worker_runs() if run.worker_run_id == worker_run_id),
        None,
    )
    if worker_run is None:
        raise ValueError(f"worker_run_id does not exist: {worker_run_id}")
    if task_id is not None and worker_run.task_id != task_id:
        raise ValueError(f"worker_run_id {worker_run_id} belongs to {worker_run.task_id}")
    worker_task = _task_by_id(tasks, worker_run.task_id)
    if worker_task is None:
        raise ValueError(f"worker_run_id {worker_run_id} belongs to missing task")
    if worker_task.plan_id != plan_id:
        raise ValueError(
            f"worker_run_id {worker_run_id} belongs to plan {worker_task.plan_id}, not {plan_id}"
        )


def _task_belongs_to_plan(
    task_id: str,
    tasks: tuple[SupervisorTaskSummaryRecord, ...],
    plan_id: str,
) -> bool:
    return any(task.task_id == task_id and task.plan_id == plan_id for task in tasks)


def _queue_state(
    plan_statuses: tuple[StoryLoopPlanStatus, ...],
    current_task: SupervisorTaskSummaryRecord | None,
) -> str:
    if current_task is not None:
        return "ready"
    states = tuple(plan.state for plan in plan_statuses)
    if "running" in states:
        return "running"
    if "hitl" in states:
        return "hitl"
    if "blocked" in states:
        return "blocked"
    if not states or all(state == "empty" for state in states):
        return "empty"
    if all(state == "completed" for state in states):
        return "completed"
    if "empty" in states:
        return "empty"
    return "completed"


def _task_by_id(
    tasks: tuple[SupervisorTaskSummaryRecord, ...],
    task_id: str | None,
) -> SupervisorTaskSummaryRecord | None:
    if task_id is None:
        return None
    return next((task for task in tasks if task.task_id == task_id), None)


def _has_worker_run_status(
    task_id: str,
    worker_runs: tuple[WorkerRunRecord, ...],
    statuses: set[str],
) -> bool:
    return any(run.task_id == task_id and run.status in statuses for run in worker_runs)


def _current_running_task_id(plan_statuses: tuple[StoryLoopPlanStatus, ...]) -> str | None:
    return next(
        (
            plan.current_task_id
            for plan in plan_statuses
            if plan.state == "running" and plan.current_task_id is not None
        ),
        None,
    )


def _current_hitl_task_id(plan_statuses: tuple[StoryLoopPlanStatus, ...]) -> str | None:
    return next(
        (
            plan.current_task_id
            for plan in plan_statuses
            if plan.state == "hitl" and plan.current_task_id is not None
        ),
        None,
    )


def _append_iteration_metadata(
    details: str | None,
    *,
    task_id: str | None,
    worker_run_id: str | None,
) -> str | None:
    metadata = []
    if task_id is not None:
        metadata.append(f"task_id={task_id}")
    if worker_run_id is not None:
        metadata.append(f"worker_run_id={worker_run_id}")
    if not metadata:
        return details
    suffix = "Story Loop metadata: " + ", ".join(metadata) + "."
    if details is None or details == "":
        return suffix
    return f"{details}\n\n{suffix}"


def _first_or_none(values: tuple[str, ...]) -> str | None:
    if not values:
        return None
    return values[0]
