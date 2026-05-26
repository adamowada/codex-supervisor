"""Story Loop status and progress helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from codex_supervisor.goal_contracts import render_goal_contract, render_goal_contract_markdown
from codex_supervisor.planning import (
    CURRENT_QUEUE_PLAN_STATUSES,
    OPEN_CRITERION_STATUSES,
    OPEN_TASK_STATUSES,
    PlanAcceptanceCriterionRecord,
    PlanArtifactLinkRecord,
    PlanningSQLiteStore,
    PlanProgressRecord,
    PlanRecord,
    SupervisorTaskRecord,
    SupervisorTaskSummaryRecord,
    WorkerResultRecord,
    WorkerRunEventRecord,
    WorkerRunRecord,
    has_nonterminal_worker_run,
    has_unresolved_task_blockers,
    is_executable_afk_task,
    missing_execution_contract_fields,
)
from codex_supervisor.worker_backends import (
    CodexExecBackend,
    CommandExecutionResult,
    CommandRunner,
    WorkerLaunchRequest,
    WorkerLaunchResult,
)
from codex_supervisor.worker_orchestration import (
    _default_git_command_runner,
    orchestrate_worker_launch,
)
from codex_supervisor.worktree_artifacts import WorktreeRunLayout, build_worktree_run_layout


class WorkerBackend(Protocol):
    """Backend surface required by the live Story Loop runner."""

    def run(self, request: WorkerLaunchRequest) -> WorkerLaunchResult:
        """Run one prepared worker request."""


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


@dataclass(frozen=True)
class LiveStoryLoopRunResult:
    """Outcome of one production Story Loop worker execution attempt."""

    status: str
    task_id: str | None
    worker_run_id: str
    worktree_path: str | None
    prompt_path: str | None
    jsonl_path: str | None
    result_path: str | None
    result_id: str | None
    failure_class: str | None
    changed_files: tuple[str, ...]
    changed_files_source: str | None
    worktree_created: bool
    launch_result: WorkerLaunchResult | None = None
    ingested_result: WorkerResultRecord | None = None


@dataclass(frozen=True)
class StoryLoopAdvanceResult:
    """One state-machine advance result."""

    state_before: str
    state_after: str
    transition: str
    task_id: str | None
    worker_run_id: str | None
    failure_class: str | None = None
    live_run: LiveStoryLoopRunResult | None = None


def build_story_loop_status(
    store: PlanningSQLiteStore,
    *,
    active_only: bool = True,
    plan_id: str | None = None,
) -> StoryLoopStatus:
    """Build Story Loop status from planning helpers."""

    snapshot = store.read_queue_snapshot()
    plans = _select_plans(snapshot.plans, active_only=active_only, plan_id=plan_id)
    tasks = snapshot.tasks
    worker_runs = snapshot.worker_runs
    criteria = snapshot.criteria
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


def advance_story_loop_once(
    store: PlanningSQLiteStore,
    *,
    repo_root: Path,
    worker_run_id: str,
    result_schema_path: str | None = None,
    sandbox_mode: str = "workspace-write",
    approval_policy: str = "never",
    codex_executable: str | None = None,
    codex_home: str | None = None,
    codex_config_path: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    service_tier: str | None = None,
    native_goal_mode: bool = False,
    ignore_user_config: bool = False,
    allow_degraded_jsonl: bool = False,
    environment: dict[str, str] | None = None,
    prompt: str | None = None,
    backend: WorkerBackend | None = None,
    command_runner: CommandRunner | None = None,
    git_command_runner: CommandRunner | None = None,
    git_executable: str = "git",
) -> StoryLoopAdvanceResult:
    """Advance the Story Loop state machine by exactly one transition."""

    before = build_story_loop_status(store)
    if before.queue_state != "ready":
        return StoryLoopAdvanceResult(
            state_before=before.queue_state,
            state_after=before.queue_state,
            transition=f"no_transition_{before.queue_state}",
            task_id=before.current_task_id,
            worker_run_id=None,
            failure_class=None
            if before.queue_state in {"completed", "empty"}
            else before.queue_state,
        )
    live_run = run_live_story_loop_once(
        store,
        repo_root=repo_root,
        worker_run_id=worker_run_id,
        result_schema_path=result_schema_path,
        sandbox_mode=sandbox_mode,
        approval_policy=approval_policy,
        codex_executable=codex_executable,
        codex_home=codex_home,
        codex_config_path=codex_config_path,
        model=model,
        reasoning_effort=reasoning_effort,
        service_tier=service_tier,
        native_goal_mode=native_goal_mode,
        ignore_user_config=ignore_user_config,
        allow_degraded_jsonl=allow_degraded_jsonl,
        environment=environment,
        prompt=prompt,
        backend=backend,
        command_runner=command_runner,
        git_command_runner=git_command_runner,
        git_executable=git_executable,
    )
    after = build_story_loop_status(store)
    return StoryLoopAdvanceResult(
        state_before=before.queue_state,
        state_after=after.queue_state,
        transition="ready_to_worker_result",
        task_id=live_run.task_id,
        worker_run_id=worker_run_id,
        failure_class=live_run.failure_class,
        live_run=live_run,
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
    if progress.linked_artifact_id is not None and not any(
        link.artifact_id == progress.linked_artifact_id for link in artifact_links
    ):
        artifact_links = (
            *artifact_links,
            PlanArtifactLinkRecord(
                plan_id=plan_id,
                artifact_id=progress.linked_artifact_id,
                relationship="progress-linked-artifact",
            ),
        )
    store.add_plan_progress_with_artifact_links(progress, artifact_links)
    return StoryLoopRecordResult(progress=progress, artifact_links=artifact_links)


def run_live_story_loop_once(
    store: PlanningSQLiteStore,
    *,
    repo_root: Path,
    worker_run_id: str,
    result_schema_path: str | None = None,
    sandbox_mode: str = "workspace-write",
    approval_policy: str = "never",
    codex_executable: str | None = None,
    codex_home: str | None = None,
    codex_config_path: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    service_tier: str | None = None,
    native_goal_mode: bool = False,
    ignore_user_config: bool = False,
    allow_degraded_jsonl: bool = False,
    environment: dict[str, str] | None = None,
    prompt: str | None = None,
    backend: WorkerBackend | None = None,
    command_runner: CommandRunner | None = None,
    git_command_runner: CommandRunner | None = None,
    git_executable: str = "git",
) -> LiveStoryLoopRunResult:
    """Claim and execute one ready AFK task through the live Codex Exec path."""

    status = build_story_loop_status(store)
    task = status.current_afk_task
    if task is None:
        return LiveStoryLoopRunResult(
            status="no_ready_task",
            task_id=status.current_task_id,
            worker_run_id=worker_run_id,
            worktree_path=None,
            prompt_path=None,
            jsonl_path=None,
            result_path=None,
            result_id=None,
            failure_class="no_ready_afk_task",
            changed_files=(),
            changed_files_source=None,
            worktree_created=False,
        )
    layout = build_worktree_run_layout(task.task_id, worker_run_id)
    effective_result_schema_path = (
        result_schema_path or f"{layout.run_directory}/worker-result.schema.json"
    )
    claim = store.claim_next_ready_afk_task(
        worker_run_id=worker_run_id,
        backend=task.worker_backend,
        task_id=task.task_id,
        status="running",
        worktree_path=layout.worktree_path,
        prompt_path=layout.prompt_path,
        jsonl_path=layout.jsonl_path,
        metadata=_live_worker_run_metadata(
            layout,
            result_schema_path=effective_result_schema_path,
            sandbox_mode=sandbox_mode,
            approval_policy=approval_policy,
            codex_home=codex_home,
            codex_config_path=codex_config_path,
            model=model,
            reasoning_effort=reasoning_effort,
            service_tier=service_tier,
            native_goal_mode=native_goal_mode,
            ignore_user_config=ignore_user_config,
            allow_degraded_jsonl=allow_degraded_jsonl,
        ),
    )
    if claim is None:
        return LiveStoryLoopRunResult(
            status="claim_conflict",
            task_id=task.task_id,
            worker_run_id=worker_run_id,
            worktree_path=layout.worktree_path,
            prompt_path=layout.prompt_path,
            jsonl_path=layout.jsonl_path,
            result_path=None,
            result_id=None,
            failure_class="claim_conflict",
            changed_files=(),
            changed_files_source=None,
            worktree_created=False,
        )
    base_commit = _git_single_line(
        git_command_runner or _default_git_command_runner,
        repo_root,
        ("rev-parse", "HEAD"),
        git_executable=git_executable,
    )
    if base_commit.exit_code != 0:
        return _fail_claimed_run(
            store,
            worker_run_id=worker_run_id,
            task_id=claim.task.task_id,
            layout=layout,
            failure_class="worktree_base_ref_failed",
            changed_files_source=None,
        )
    worktree_result = _git_single_line(
        git_command_runner or _default_git_command_runner,
        repo_root,
        ("worktree", "add", "--detach", str(repo_root / layout.worktree_path), base_commit.stdout),
        git_executable=git_executable,
    )
    if worktree_result.exit_code != 0:
        return _fail_claimed_run(
            store,
            worker_run_id=worker_run_id,
            task_id=claim.task.task_id,
            layout=layout,
            failure_class="worktree_create_failed",
            changed_files_source=None,
        )

    goal_contract = render_goal_contract(task)
    rendered_goal_contract = render_goal_contract_markdown(goal_contract)
    active_backend = backend or CodexExecBackend(
        codex_executable=codex_executable,
        command_runner=command_runner,
        launch_enabled=True,
    )
    orchestration = orchestrate_worker_launch(
        claim.task,
        backend=active_backend,
        worker_run_id=worker_run_id,
        repo_root=repo_root,
        result_schema_path=effective_result_schema_path,
        prompt=prompt or _default_live_worker_prompt(),
        rendered_goal_contract=rendered_goal_contract,
        sandbox_mode=sandbox_mode,
        approval_policy=approval_policy,
        codex_home=codex_home,
        codex_config_path=codex_config_path,
        model=model,
        reasoning_effort=reasoning_effort,
        service_tier=service_tier,
        native_goal_mode=native_goal_mode,
        ignore_user_config=ignore_user_config,
        allow_degraded_jsonl=allow_degraded_jsonl,
        environment=environment,
        metadata={"launch_mode": "live_story_loop_run"},
        require_git_changed_files=True,
        git_command_runner=git_command_runner,
        git_base_ref=base_commit.stdout,
        git_executable=git_executable,
    )
    launch_result = orchestration.launch_result
    _record_worker_launch_event(
        store,
        worker_run_id=worker_run_id,
        launch_result=launch_result,
        changed_files=orchestration.changed_files,
        changed_files_source=orchestration.changed_files_source,
    )
    if (
        launch_result.status in {"completed", "needs_review"}
        and launch_result.result_path is not None
    ):
        missing_evidence = _missing_launch_evidence_paths(repo_root, launch_result)
        if missing_evidence:
            failure_class = "worker_evidence_missing"
            store.update_worker_run_status(
                worker_run_id,
                "failed",
                failure_class=failure_class,
                result_path=launch_result.result_path,
            )
            store.add_worker_run_event(
                WorkerRunEventRecord(
                    event_id=f"{worker_run_id}-evidence-missing",
                    worker_run_id=worker_run_id,
                    event_type="worker_evidence_missing",
                    summary=(
                        "Story Loop refused completion because launch evidence paths are missing."
                    ),
                    details={
                        "task_id": claim.task.task_id,
                        "missing_evidence_paths": list(missing_evidence),
                    },
                    artifact_path=launch_result.metadata.get("evidence_manifest_path")
                    if isinstance(launch_result.metadata.get("evidence_manifest_path"), str)
                    else launch_result.jsonl_path,
                    metadata=launch_result.metadata,
                )
            )
            return LiveStoryLoopRunResult(
                status="failed",
                task_id=claim.task.task_id,
                worker_run_id=worker_run_id,
                worktree_path=layout.worktree_path,
                prompt_path=layout.prompt_path,
                jsonl_path=layout.jsonl_path,
                result_path=launch_result.result_path,
                result_id=None,
                failure_class=failure_class,
                changed_files=orchestration.changed_files,
                changed_files_source=orchestration.changed_files_source,
                worktree_created=True,
                launch_result=launch_result,
            )
        ingested = store.ingest_worker_result(worker_run_id, launch_result.result_path)
        _create_review_task_for_review_required_result(
            store,
            source_task=claim.task,
            worker_run_id=worker_run_id,
            worker_result=ingested,
        )
        return LiveStoryLoopRunResult(
            status=ingested.status,
            task_id=claim.task.task_id,
            worker_run_id=worker_run_id,
            worktree_path=layout.worktree_path,
            prompt_path=layout.prompt_path,
            jsonl_path=layout.jsonl_path,
            result_path=ingested.source_path,
            result_id=ingested.result_id,
            failure_class=None,
            changed_files=orchestration.changed_files,
            changed_files_source=orchestration.changed_files_source,
            worktree_created=True,
            launch_result=launch_result,
            ingested_result=ingested,
        )
    terminal_status = _terminal_worker_run_status(launch_result.status)
    store.update_worker_run_status(
        worker_run_id,
        terminal_status,
        failure_class=launch_result.failure_class,
        result_path=launch_result.result_path,
    )
    return LiveStoryLoopRunResult(
        status=terminal_status,
        task_id=claim.task.task_id,
        worker_run_id=worker_run_id,
        worktree_path=layout.worktree_path,
        prompt_path=layout.prompt_path,
        jsonl_path=layout.jsonl_path,
        result_path=launch_result.result_path,
        result_id=None,
        failure_class=launch_result.failure_class,
        changed_files=orchestration.changed_files,
        changed_files_source=orchestration.changed_files_source,
        worktree_created=True,
        launch_result=launch_result,
    )


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


def _live_worker_run_metadata(
    layout: WorktreeRunLayout,
    *,
    result_schema_path: str,
    sandbox_mode: str,
    approval_policy: str,
    codex_home: str | None,
    codex_config_path: str | None,
    model: str | None,
    reasoning_effort: str | None,
    service_tier: str | None,
    native_goal_mode: bool,
    ignore_user_config: bool,
    allow_degraded_jsonl: bool,
) -> dict[str, object]:
    return {
        "backend": "codex_exec",
        "worker_run_id": layout.worker_run_id,
        "launch_preparation": {
            "mode": "live_story_loop_run",
            "result_schema_path": result_schema_path,
            "sandbox_mode": sandbox_mode,
            "approval_policy": approval_policy,
            "native_goal_mode": native_goal_mode,
            "ignore_user_config": ignore_user_config,
            "jsonl_required": not allow_degraded_jsonl,
        },
        "codex_home": codex_home,
        "codex_config_path": codex_config_path,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "service_tier": service_tier,
        "worktree_path": layout.worktree_path,
        "raw_result_path": layout.raw_result_path,
        "raw_evidence_paths": layout.raw_evidence_paths(),
    }


def _git_single_line(
    command_runner: CommandRunner,
    cwd: Path,
    args: tuple[str, ...],
    *,
    git_executable: str,
) -> CommandExecutionResult:
    result = command_runner((git_executable, *args), cwd, {"GIT_OPTIONAL_LOCKS": "0"})
    if result.exit_code != 0:
        return result
    stdout = result.stdout.strip().splitlines()[0].strip() if result.stdout.strip() else ""
    return CommandExecutionResult(exit_code=0, stdout=stdout, stderr=result.stderr)


def _fail_claimed_run(
    store: PlanningSQLiteStore,
    *,
    worker_run_id: str,
    task_id: str,
    layout: WorktreeRunLayout,
    failure_class: str,
    changed_files_source: str | None,
) -> LiveStoryLoopRunResult:
    store.update_worker_run_status(worker_run_id, "failed", failure_class=failure_class)
    store.add_worker_run_event(
        WorkerRunEventRecord(
            event_id=f"{worker_run_id}-claim-failed",
            worker_run_id=worker_run_id,
            event_type="worker_launch_failed",
            summary=f"Story Loop worker launch failed before Codex Exec: {failure_class}",
            details={
                "task_id": task_id,
                "failure_class": failure_class,
                "changed_files_source": changed_files_source,
            },
        )
    )
    return LiveStoryLoopRunResult(
        status="failed",
        task_id=task_id,
        worker_run_id=worker_run_id,
        worktree_path=layout.worktree_path,
        prompt_path=layout.prompt_path,
        jsonl_path=layout.jsonl_path,
        result_path=None,
        result_id=None,
        failure_class=failure_class,
        changed_files=(),
        changed_files_source=changed_files_source,
        worktree_created=False,
    )


def _default_live_worker_prompt() -> str:
    return (
        "Execute the claimed Story Loop task exactly once from this isolated worktree. "
        "Keep edits within the allowed paths, run the required verification commands, "
        "write the required Worker Result JSON, and stop."
    )


def _record_worker_launch_event(
    store: PlanningSQLiteStore,
    *,
    worker_run_id: str,
    launch_result: WorkerLaunchResult,
    changed_files: tuple[str, ...],
    changed_files_source: str,
) -> None:
    store.add_worker_run_event(
        WorkerRunEventRecord(
            event_id=f"{worker_run_id}-launch-result",
            worker_run_id=worker_run_id,
            event_type="codex_exec_launch_result",
            summary=(
                f"Codex Exec launch ended as {launch_result.status}"
                + (
                    f" ({launch_result.failure_class})"
                    if launch_result.failure_class is not None
                    else ""
                )
            ),
            details={
                "task_id": launch_result.task_id,
                "status": launch_result.status,
                "exit_code": launch_result.exit_code,
                "duration_seconds": launch_result.duration_seconds,
                "failure_class": launch_result.failure_class,
                "changed_files": list(changed_files),
                "changed_files_source": changed_files_source,
                "result_path": launch_result.result_path,
                "prompt_path": launch_result.prompt_path,
                "jsonl_path": launch_result.jsonl_path,
                "stdout_path": launch_result.stdout_path,
                "stderr_path": launch_result.stderr_path,
                "final_message_path": launch_result.final_message_path,
                "diff_summary_path": launch_result.diff_summary_path,
                "evidence_manifest_path": launch_result.metadata.get("evidence_manifest_path"),
            },
            artifact_path=launch_result.jsonl_path,
            metadata=launch_result.metadata,
        )
    )


def _missing_launch_evidence_paths(
    repo_root: Path,
    launch_result: WorkerLaunchResult,
) -> tuple[str, ...]:
    paths = [
        launch_result.result_path,
        launch_result.prompt_path,
        launch_result.jsonl_path,
        launch_result.stdout_path,
        launch_result.stderr_path,
        launch_result.final_message_path,
        launch_result.diff_summary_path,
    ]
    manifest_path = launch_result.metadata.get("evidence_manifest_path")
    if isinstance(manifest_path, str) and manifest_path.strip():
        paths.append(manifest_path)
    return tuple(
        path
        for path in dict.fromkeys(item for item in paths if isinstance(item, str) and item.strip())
        if not (repo_root / path).is_file()
    )


def _create_review_task_for_review_required_result(
    store: PlanningSQLiteStore,
    *,
    source_task: SupervisorTaskSummaryRecord,
    worker_run_id: str,
    worker_result: WorkerResultRecord,
) -> None:
    if not source_task.review_required or worker_result.status not in {"completed", "needs_review"}:
        return
    review_task_id = _review_task_id(source_task.task_id, worker_run_id)
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id=review_task_id,
            plan_id=source_task.plan_id,
            title=f"Review {source_task.title}",
            goal=(
                f"Review worker run {worker_run_id} for source task {source_task.task_id} "
                "before the source task can be closed."
            ),
            task_type="HITL",
            status="ready",
            scope={
                "source_task_id": source_task.task_id,
                "worker_run_id": worker_run_id,
                "worker_result_id": worker_result.result_id,
                "worker_result_path": worker_result.source_path,
                "review_gate": "separate_review_required_task",
            },
            out_of_scope={
                "implementation": "Do not make code changes from the review task itself.",
            },
            acceptance_criteria=[
                "A separate review verdict is recorded for the worker result.",
                "Accepted findings are routed into repair tasks before the source task is closed.",
            ],
            verification_commands=list(source_task.verification_commands),
            allowed_paths=["plans/planning.sqlite3", "runs/**", "artifacts/**"],
            worker_backend="human_review",
            review_required=False,
        ),
        validate_current_queue_contract=False,
    )


def _review_task_id(source_task_id: str, worker_run_id: str) -> str:
    return f"task-review-{source_task_id}-{worker_run_id}"


def _terminal_worker_run_status(launch_status: str) -> str:
    if launch_status == "blocked":
        return "blocked"
    return "failed"


def _build_plan_status(
    plan: PlanRecord,
    tasks: tuple[SupervisorTaskSummaryRecord, ...],
    all_tasks: tuple[SupervisorTaskSummaryRecord, ...],
    worker_runs: tuple[WorkerRunRecord, ...],
    criteria: tuple[PlanAcceptanceCriterionRecord, ...],
) -> StoryLoopPlanStatus:
    open_tasks = tuple(task for task in tasks if task.status in OPEN_TASK_STATUSES)
    failed_tasks = tuple(task for task in tasks if task.status == "failed")
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
    elif failed_tasks:
        state = "blocked"
        summary = f"Failed task requires reconciliation: {failed_tasks[0].task_id}"
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
        blocked_task_ids=tuple(task.task_id for task in (*blocked_tasks, *failed_tasks)),
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
    snapshot = store.read_queue_snapshot()
    tasks = snapshot.tasks
    task = _task_by_id(tasks, task_id)
    if task_id is not None and task is None:
        raise ValueError(f"task_id does not exist: {task_id}")
    if task is not None and task.plan_id != plan_id:
        raise ValueError(f"task_id {task_id} belongs to {task.plan_id}, not {plan_id}")
    if worker_run_id is None:
        return
    worker_run = next(
        (run for run in snapshot.worker_runs if run.worker_run_id == worker_run_id),
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
