"""Story Loop launch-result outcome application."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from codex_supervisor.evidence_vocabulary import (
    BROWSER_SMOKE_FAILED_EVENT,
    BROWSER_SMOKE_PASSED_EVENT,
    WORKER_EVIDENCE_MANIFEST_ARTIFACT_RELATIONSHIP,
    WORKER_RESULT_ARTIFACT_RELATIONSHIP,
    WORKER_RESULT_NORMALIZED_ARTIFACT_RELATIONSHIP,
)
from codex_supervisor.planning import (
    PlanArtifactLinkRecord,
    PlanningSQLiteStore,
    PlanProgressRecord,
    SupervisorTaskRecord,
    SupervisorTaskSummaryRecord,
    WorkerResultRecord,
    WorkerRunEventRecord,
)
from codex_supervisor.worker_backends import WorkerLaunchResult
from codex_supervisor.worker_orchestration import WorkerOrchestrationResult
from codex_supervisor.worker_result_ingestion import ingest_worker_result_path


@dataclass(frozen=True)
class StoryLoopLaunchOutcome:
    """Durable planning outcome for one backend launch result."""

    status: str
    result_path: str | None
    result_id: str | None
    failure_class: str | None
    ingested_result: WorkerResultRecord | None = None
    rejected_result: WorkerResultRecord | None = None


def apply_story_loop_launch_outcome(
    store: PlanningSQLiteStore,
    *,
    source_task: SupervisorTaskSummaryRecord,
    worker_run_id: str,
    repo_root: Path,
    orchestration: WorkerOrchestrationResult,
) -> StoryLoopLaunchOutcome:
    """Apply one launch result to planning SQLite and related durable evidence rows."""

    launch_result = orchestration.launch_result
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
                        "task_id": source_task.task_id,
                        "missing_evidence_paths": list(missing_evidence),
                    },
                    artifact_path=launch_result.metadata.get("evidence_manifest_path")
                    if isinstance(launch_result.metadata.get("evidence_manifest_path"), str)
                    else launch_result.jsonl_path,
                    metadata=launch_result.metadata,
                )
            )
            return StoryLoopLaunchOutcome(
                status="failed",
                result_path=launch_result.result_path,
                result_id=None,
                failure_class=failure_class,
            )
        ingested = ingest_worker_result_path(store, worker_run_id, launch_result.result_path)
        _link_completed_worker_evidence_artifacts(
            store,
            plan_id=source_task.plan_id,
            launch_result=launch_result,
            worker_result=ingested,
        )
        _record_browser_smoke_progress_from_result(
            store,
            plan_id=source_task.plan_id,
            worker_run_id=worker_run_id,
            worker_result=ingested,
        )
        _create_review_task_for_review_required_result(
            store,
            source_task=source_task,
            worker_run_id=worker_run_id,
            worker_result=ingested,
        )
        return StoryLoopLaunchOutcome(
            status=ingested.status,
            result_path=ingested.source_path,
            result_id=ingested.result_id,
            failure_class=None,
            ingested_result=ingested,
        )

    terminal_status = _terminal_worker_run_status(launch_result.status)
    store.update_worker_run_status(
        worker_run_id,
        terminal_status,
        failure_class=launch_result.failure_class,
        result_path=launch_result.result_path,
    )
    rejected_result = None
    if launch_result.result_path is not None and launch_result.failure_class is not None:
        rejected_result = store.record_rejected_worker_result_attempt(
            worker_run_id=worker_run_id,
            source_path=launch_result.result_path,
            failure_class=launch_result.failure_class,
            rejection_metadata={
                "changed_files": list(orchestration.changed_files),
                "changed_files_source": orchestration.changed_files_source,
                "changed_path_violations": [
                    {"path": violation.path, "reason": violation.reason}
                    for violation in orchestration.changed_path_violations
                ],
                "launch_result_metadata": launch_result.metadata,
            },
        )
        store.add_worker_run_event(
            WorkerRunEventRecord(
                event_id=f"{worker_run_id}-worker-result-rejected",
                worker_run_id=worker_run_id,
                event_type="worker_result_rejected",
                summary="Supervisor rejected a Worker Result after launch acceptance gates.",
                details={
                    "result_id": rejected_result.result_id,
                    "source_path": rejected_result.source_path,
                    "failure_class": launch_result.failure_class,
                },
                artifact_path=launch_result.result_path,
                metadata={"supervisor_acceptance_status": "failed"},
            )
        )
    return StoryLoopLaunchOutcome(
        status=terminal_status,
        result_path=launch_result.result_path,
        result_id=rejected_result.result_id if rejected_result is not None else None,
        failure_class=launch_result.failure_class,
        rejected_result=rejected_result,
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
            task_type="AFK",
            status="ready",
            scope={
                "source_task_id": source_task.task_id,
                "worker_run_id": worker_run_id,
                "worker_result_id": worker_result.result_id,
                "worker_result_path": worker_result.source_path,
                "review_gate": "separate_review_required_task",
                "review_execution": "codex_review",
            },
            out_of_scope={
                "implementation": "Do not make code changes from the review task itself.",
            },
            acceptance_criteria=[
                "A separate Codex review verdict is recorded for the worker result.",
                "Accepted findings are routed into repair tasks before the source task is closed.",
            ],
            verification_commands=list(source_task.verification_commands),
            allowed_paths=["plans/planning.sqlite3", "runs/**", "artifacts/**"],
            worker_backend="codex_review",
            review_required=False,
        ),
        validate_current_queue_contract=False,
    )


def _link_completed_worker_evidence_artifacts(
    store: PlanningSQLiteStore,
    *,
    plan_id: str,
    launch_result: WorkerLaunchResult,
    worker_result: WorkerResultRecord,
) -> None:
    manifest_path = launch_result.metadata.get("evidence_manifest_path")
    links: list[PlanArtifactLinkRecord] = []
    if isinstance(manifest_path, str) and manifest_path.strip():
        links.append(
            PlanArtifactLinkRecord(
                plan_id=plan_id,
                artifact_id=manifest_path,
                relationship=WORKER_EVIDENCE_MANIFEST_ARTIFACT_RELATIONSHIP,
            )
        )
    if launch_result.result_path is not None:
        links.append(
            PlanArtifactLinkRecord(
                plan_id=plan_id,
                artifact_id=launch_result.result_path,
                relationship=WORKER_RESULT_ARTIFACT_RELATIONSHIP,
            )
        )
    normalized_path = worker_result.metadata.get("normalized_result_path")
    if isinstance(normalized_path, str) and normalized_path.strip():
        links.append(
            PlanArtifactLinkRecord(
                plan_id=plan_id,
                artifact_id=normalized_path,
                relationship=WORKER_RESULT_NORMALIZED_ARTIFACT_RELATIONSHIP,
            )
        )
    for link in links:
        store.add_plan_artifact_link(link)


def _record_browser_smoke_progress_from_result(
    store: PlanningSQLiteStore,
    *,
    plan_id: str,
    worker_run_id: str,
    worker_result: WorkerResultRecord,
) -> None:
    entries = worker_result.raw_payload.get("browser_smoke_results")
    if not isinstance(entries, list) or not entries:
        return
    statuses = tuple(
        item.get("status") for item in entries if isinstance(item, dict) and item.get("status")
    )
    if not statuses:
        return
    event_type = (
        BROWSER_SMOKE_PASSED_EVENT
        if statuses and all(status == "passed" for status in statuses)
        else BROWSER_SMOKE_FAILED_EVENT
    )
    artifacts = _browser_smoke_artifact_paths_from_entries(entries)
    store.add_plan_progress(
        PlanProgressRecord(
            progress_id=f"{worker_run_id}-{event_type}",
            plan_id=plan_id,
            event_type=event_type,
            summary=f"Worker run {worker_run_id} recorded {event_type.replace('_', ' ')}.",
            details=json.dumps(
                {
                    "worker_run_id": worker_run_id,
                    "worker_result_id": worker_result.result_id,
                    "statuses": list(statuses),
                    "artifacts": list(artifacts),
                },
                sort_keys=True,
            ),
        )
    )


def _browser_smoke_artifact_paths_from_entries(entries: list[object]) -> tuple[str, ...]:
    paths: list[str] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        artifact = item.get("artifact")
        if isinstance(artifact, str) and artifact.strip():
            paths.append(artifact.strip().replace("\\", "/"))
        artifacts = item.get("artifacts")
        if isinstance(artifacts, list):
            paths.extend(
                artifact.strip().replace("\\", "/")
                for artifact in artifacts
                if isinstance(artifact, str) and artifact.strip()
            )
    return tuple(dict.fromkeys(paths))


def _review_task_id(source_task_id: str, worker_run_id: str) -> str:
    return f"task-review-{source_task_id}-{worker_run_id}"


def _terminal_worker_run_status(launch_status: str) -> str:
    if launch_status == "blocked":
        return "blocked"
    return "failed"
