"""Persist validated review results into planning evidence."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from codex_supervisor.planning import (
    PlanArtifactLinkRecord,
    PlanningSQLiteStore,
    PlanProgressRecord,
    ReviewPromotionRecord,
    SupervisorTaskSummaryRecord,
)
from codex_supervisor.review_loop import ReviewFinding, ReviewResult, ReviewVerificationEvidence
from codex_supervisor.review_repairs import (
    DEFAULT_REPAIR_VERIFICATION_COMMANDS,
    ReviewRepairRoutingResult,
    apply_repair_task_plan,
    plan_repair_tasks_from_review_result,
)
from codex_supervisor.worker_backends import (
    CommandExecutionResult,
    LaunchEnvironmentResult,
    _minimal_process_environment,
    build_codex_launch_environment,
)

REVIEW_RESULT_RECORDED_EVENT = "review_result_recorded"
REVIEW_RESULT_ARTIFACT_RELATIONSHIP = "review-result"
REVIEW_ARTIFACT_RELATIONSHIP = "review-artifact"
JsonObject = dict[str, Any]


@dataclass(frozen=True)
class ReviewResultPersistenceRecord:
    """Planning records created for one persisted review result."""

    progress: PlanProgressRecord
    artifact_links: tuple[PlanArtifactLinkRecord, ...]


@dataclass(frozen=True)
class ReviewLaunchRequest:
    """Input for one live reviewer launch."""

    review_id: str
    task_id: str
    mode: str
    target: str
    repo_root: Path
    result_path: str
    prompt_path: str
    jsonl_path: str
    stdout_path: str
    stderr_path: str
    final_message_path: str
    schema_path: str
    prompt: str
    sandbox_mode: str
    approval_policy: str
    codex_home: str | None = None
    model: str | None = None
    environment: dict[str, str] | None = None
    launch_timeout_seconds: float | None = 3600.0
    preflight_timeout_seconds: float | None = 30.0


@dataclass(frozen=True)
class ReviewLaunchResult:
    """Live reviewer backend result before persistence and repair routing."""

    review_id: str
    task_id: str
    status: str
    review_result: ReviewResult | None = None
    result_path: str | None = None
    exit_code: int | None = None
    duration_seconds: float | None = None
    failure_class: str | None = None
    prompt_path: str | None = None
    jsonl_path: str | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None
    final_message_path: str | None = None


class ReviewBackend(Protocol):
    """Backend surface required by live review execution."""

    def run(self, request: ReviewLaunchRequest) -> ReviewLaunchResult:
        """Run one review launch request."""


@dataclass(frozen=True)
class LiveReviewRunResult:
    """Persisted review execution result."""

    status: str
    review_id: str
    task_id: str
    progress_id: str | None
    result_path: str | None
    failure_class: str | None
    created_repair_task_ids: tuple[str, ...] = ()
    existing_repair_task_ids: tuple[str, ...] = ()
    skipped_finding_ids: tuple[str, ...] = ()
    launch_result: ReviewLaunchResult | None = None
    persistence: ReviewResultPersistenceRecord | None = None
    repair_result: ReviewRepairRoutingResult | None = None
    review_promotion: ReviewPromotionRecord | None = None


@dataclass(frozen=True)
class CodexReviewBackend:
    """Launch Codex Exec as a structured review worker."""

    codex_executable: str | None = None
    launch_enabled: bool = True

    def run(self, request: ReviewLaunchRequest) -> ReviewLaunchResult:
        """Run a live Codex review and validate the emitted ReviewResult JSON."""

        _write_text_artifact(request.repo_root, request.schema_path, _review_result_schema_json())
        _write_text_artifact(request.repo_root, request.prompt_path, request.prompt)
        executable = self.codex_executable or shutil.which("codex")
        if executable is None:
            return _failed_review_launch(
                request,
                failure_class="codex_cli_unavailable",
                stderr="codex executable was not found on PATH",
            )
        environment_result = _review_environment(request)
        if environment_result.failure_class is not None:
            return _failed_review_launch(
                request,
                failure_class=environment_result.failure_class,
                stderr=environment_result.stderr,
            )
        environment = environment_result.environment
        version = _run_review_command(
            (executable, "--version"),
            request.repo_root,
            environment,
            stdin=None,
            timeout_seconds=request.preflight_timeout_seconds,
        )
        if version.exit_code != 0:
            return _failed_review_launch(
                request,
                failure_class="codex_version_failed",
                stdout=version.stdout,
                stderr=version.stderr,
                exit_code=version.exit_code,
            )
        if not self.launch_enabled:
            return _failed_review_launch(
                request,
                failure_class="review_launch_disabled",
                stdout=version.stdout,
                stderr="live review launch is disabled",
                exit_code=0,
                status="blocked",
            )
        argv = _codex_review_argv(request, executable)
        started_at = time.perf_counter()
        try:
            completed = _run_review_command(
                argv,
                request.repo_root,
                environment,
                stdin=request.prompt,
                timeout_seconds=request.launch_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return _failed_review_launch(
                request,
                failure_class="codex_review_timeout",
                stdout=_timeout_text(exc.stdout),
                stderr=f"codex review timed out after {exc.timeout} seconds",
                exit_code=124,
            )
        duration = time.perf_counter() - started_at
        _write_text_artifact(request.repo_root, request.stdout_path, completed.stdout)
        _write_text_artifact(request.repo_root, request.stderr_path, completed.stderr)
        _write_text_artifact(request.repo_root, request.jsonl_path, completed.stdout)
        if completed.exit_code != 0:
            _write_text_artifact(
                request.repo_root,
                request.final_message_path,
                f"Codex review failed with exit code {completed.exit_code}.\n",
            )
            return ReviewLaunchResult(
                review_id=request.review_id,
                task_id=request.task_id,
                status="failed",
                exit_code=completed.exit_code,
                duration_seconds=duration,
                failure_class="codex_review_failed",
                prompt_path=request.prompt_path,
                jsonl_path=request.jsonl_path,
                stdout_path=request.stdout_path,
                stderr_path=request.stderr_path,
                final_message_path=request.final_message_path,
            )
        result_source = _review_result_source(request)
        if result_source is None:
            return _failed_review_launch(
                request,
                failure_class="review_result_missing",
                stdout=completed.stdout,
                stderr=(
                    "review result was not written to the structured final message "
                    f"or legacy result artifact: {request.final_message_path}, "
                    f"{request.result_path}"
                ),
                exit_code=completed.exit_code,
            )
        result_file, result_artifact_path = result_source
        try:
            review_result = _load_review_result_file(result_file)
            _validate_review_result_identity(review_result, request)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            return _failed_review_launch(
                request,
                failure_class="review_result_invalid",
                stdout=completed.stdout,
                stderr=str(exc),
                exit_code=completed.exit_code,
            )
        if result_artifact_path != request.result_path:
            _copy_review_result_artifact(request, result_file)
        return ReviewLaunchResult(
            review_id=request.review_id,
            task_id=request.task_id,
            status="completed",
            review_result=review_result,
            result_path=request.result_path,
            exit_code=completed.exit_code,
            duration_seconds=duration,
            prompt_path=request.prompt_path,
            jsonl_path=request.jsonl_path,
            stdout_path=request.stdout_path,
            stderr_path=request.stderr_path,
            final_message_path=request.final_message_path,
        )


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


def run_live_review_for_task(
    store: PlanningSQLiteStore,
    *,
    task_id: str,
    review_id: str,
    repo_root: Path,
    review_result_artifact_id: str,
    backend: ReviewBackend | None = None,
    mode: str = "everything",
    target: str | None = None,
    progress_id: str | None = None,
    review_artifact_ids: tuple[str, ...] = (),
    create_repair_tasks: bool = True,
    repair_task_id_prefix: str = "task-review-repair",
    repair_verification_commands: tuple[str, ...] = DEFAULT_REPAIR_VERIFICATION_COMMANDS,
    codex_executable: str | None = None,
    codex_home: str | None = None,
    model: str | None = None,
    sandbox_mode: str = "workspace-write",
    approval_policy: str = "never",
    environment: dict[str, str] | None = None,
) -> LiveReviewRunResult:
    """Launch a live review, persist validated evidence, and route accepted findings."""

    task = _task_by_id(store, task_id)
    source_task_id = _source_task_id_for_review_task(task)
    review_target = target or source_task_id or task_id
    effective_progress_id = progress_id or f"progress-review-{review_id}"
    request = _review_launch_request(
        task,
        review_id=review_id,
        target=review_target,
        mode=mode,
        repo_root=repo_root,
        codex_home=codex_home,
        model=model,
        sandbox_mode=sandbox_mode,
        approval_policy=approval_policy,
        environment=environment,
    )
    active_backend = backend or CodexReviewBackend(
        codex_executable=codex_executable,
        launch_enabled=True,
    )
    launch_result = active_backend.run(request)
    if launch_result.status != "completed" or launch_result.review_result is None:
        persistence = _persist_failed_review_launch(
            store,
            plan_id=task.plan_id,
            progress_id=effective_progress_id,
            launch_result=launch_result,
        )
        return LiveReviewRunResult(
            status=launch_result.status,
            review_id=review_id,
            task_id=task_id,
            progress_id=effective_progress_id,
            result_path=launch_result.result_path,
            failure_class=launch_result.failure_class,
            launch_result=launch_result,
            persistence=persistence,
        )
    review_result = launch_result.review_result
    _validate_review_result_identity(review_result, request)
    repair_plan: ReviewRepairRoutingResult | None = None
    if create_repair_tasks:
        repair_plan = plan_repair_tasks_from_review_result(
            store,
            plan_id=task.plan_id,
            review_result=review_result,
            source_task_id=source_task_id or task_id,
            task_id_prefix=repair_task_id_prefix,
            verification_commands=repair_verification_commands,
        )
    persistence = record_review_result(
        store,
        plan_id=task.plan_id,
        progress_id=effective_progress_id,
        review_result=review_result,
        review_result_artifact_id=review_result_artifact_id,
        review_artifact_ids=review_artifact_ids,
    )
    repair_result = apply_repair_task_plan(store, repair_plan) if repair_plan is not None else None
    review_promotion: ReviewPromotionRecord | None = None
    if _needs_hitl_findings(review_result):
        status = "needs_hitl"
    elif source_task_id is not None:
        review_promotion = store.promote_reviewed_task_completion(
            source_task_id=source_task_id,
            review_task_id=task_id,
            worker_run_id=_worker_run_id_for_review_task(task),
            review_progress_id=effective_progress_id,
        )
        status = "completed"
    else:
        store.update_supervisor_task_status(task_id, "completed")
        status = "completed"
    return LiveReviewRunResult(
        status=status,
        review_id=review_id,
        task_id=task_id,
        progress_id=effective_progress_id,
        result_path=launch_result.result_path,
        failure_class=None,
        created_repair_task_ids=(
            tuple(task.task_id for task in repair_result.created_tasks)
            if repair_result is not None
            else ()
        ),
        existing_repair_task_ids=(
            repair_result.existing_task_ids if repair_result is not None else ()
        ),
        skipped_finding_ids=(
            tuple(finding.finding_id for finding in repair_result.skipped_findings)
            if repair_result is not None
            else ()
        ),
        launch_result=launch_result,
        persistence=persistence,
        repair_result=repair_result,
        review_promotion=review_promotion,
    )


def _summary(review_result: ReviewResult) -> str:
    counts = _finding_counts(review_result)
    return (
        f"Recorded {review_result.mode} review {review_result.review_id} for "
        f"{review_result.target}: {counts['accepted']} accepted, {counts['waived']} waived, "
        f"{counts['needs_hitl']} needs HITL."
    )


def _persist_failed_review_launch(
    store: PlanningSQLiteStore,
    *,
    plan_id: str,
    progress_id: str,
    launch_result: ReviewLaunchResult,
) -> ReviewResultPersistenceRecord:
    artifacts = tuple(
        path
        for path in (
            launch_result.result_path,
            launch_result.prompt_path,
            launch_result.jsonl_path,
            launch_result.stdout_path,
            launch_result.stderr_path,
            launch_result.final_message_path,
        )
        if path
    )
    progress = PlanProgressRecord(
        progress_id=progress_id,
        plan_id=plan_id,
        event_type="review_launch_failed",
        summary=(
            f"Review launch {launch_result.review_id} ended as {launch_result.status}"
            + (
                f" ({launch_result.failure_class})"
                if launch_result.failure_class is not None
                else ""
            )
        ),
        details=json.dumps(
            {
                "review_id": launch_result.review_id,
                "task_id": launch_result.task_id,
                "status": launch_result.status,
                "exit_code": launch_result.exit_code,
                "duration_seconds": launch_result.duration_seconds,
                "failure_class": launch_result.failure_class,
                "result_path": launch_result.result_path,
                "prompt_path": launch_result.prompt_path,
                "jsonl_path": launch_result.jsonl_path,
                "stdout_path": launch_result.stdout_path,
                "stderr_path": launch_result.stderr_path,
                "final_message_path": launch_result.final_message_path,
            },
            sort_keys=True,
        ),
        linked_artifact_id=artifacts[0] if artifacts else None,
    )
    artifact_links = tuple(
        PlanArtifactLinkRecord(plan_id=plan_id, artifact_id=artifact, relationship="review-launch")
        for artifact in artifacts
    )
    store.add_plan_progress_with_artifact_links(progress, artifact_links)
    return ReviewResultPersistenceRecord(progress=progress, artifact_links=artifact_links)


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


def _task_by_id(store: PlanningSQLiteStore, task_id: str) -> SupervisorTaskSummaryRecord:
    task = next((task for task in store.list_supervisor_tasks() if task.task_id == task_id), None)
    if task is None:
        raise ValueError(f"task does not exist: {task_id}")
    return task


def _source_task_id_for_review_task(task: SupervisorTaskSummaryRecord) -> str | None:
    if task.scope.get("review_gate") != "separate_review_required_task":
        return None
    value = task.scope.get("source_task_id")
    return value if isinstance(value, str) and value.strip() else None


def _worker_run_id_for_review_task(task: SupervisorTaskSummaryRecord) -> str | None:
    value = task.scope.get("worker_run_id")
    return value if isinstance(value, str) and value.strip() else None


def _review_launch_request(
    task: SupervisorTaskSummaryRecord,
    *,
    review_id: str,
    target: str,
    mode: str,
    repo_root: Path,
    codex_home: str | None,
    model: str | None,
    sandbox_mode: str,
    approval_policy: str,
    environment: dict[str, str] | None,
) -> ReviewLaunchRequest:
    base = f"runs/reviews/{task.task_id}/{review_id}"
    result_path = f"{base}/review-result.json"
    schema_path = f"{base}/review-result.schema.json"
    prompt = _review_prompt(
        task,
        review_id=review_id,
        target=target,
        mode=mode,
        result_path=result_path,
        schema_path=schema_path,
    )
    return ReviewLaunchRequest(
        review_id=review_id,
        task_id=task.task_id,
        mode=mode,
        target=target,
        repo_root=repo_root,
        result_path=result_path,
        prompt_path=f"{base}/prompt.md",
        jsonl_path=f"{base}/codex.jsonl",
        stdout_path=f"{base}/stdout.txt",
        stderr_path=f"{base}/stderr.txt",
        final_message_path=f"{base}/final-message.txt",
        schema_path=schema_path,
        prompt=prompt,
        sandbox_mode=sandbox_mode,
        approval_policy=approval_policy,
        codex_home=codex_home,
        model=model,
        environment=environment,
    )


def _review_prompt(
    task: SupervisorTaskSummaryRecord,
    *,
    review_id: str,
    target: str,
    mode: str,
    result_path: str,
    schema_path: str,
) -> str:
    acceptance = "\n".join(f"- {criterion}" for criterion in task.acceptance_criteria)
    verification = "\n".join(f"- `{command}`" for command in task.verification_commands)
    allowed_paths = "\n".join(f"- `{path}`" for path in task.allowed_paths)
    return (
        "# Review Contract\n\n"
        f"Review ID: `{review_id}`\n"
        f"Mode: `{mode}`\n"
        f"Target: `{target}`\n"
        f"Task: `{task.task_id}` - {task.title}\n\n"
        "Review the completed task for correctness, quality, source-of-truth drift, and "
        "production readiness. Do not edit source files; only write the structured review result. "
        "Classify each finding as accepted, waived, or needs_hitl.\n\n"
        "# Acceptance Criteria\n"
        f"{acceptance or '- none'}\n\n"
        "# Verification Commands\n"
        f"{verification or '- none'}\n\n"
        "# Allowed Paths\n"
        f"{allowed_paths or '- none'}\n\n"
        "# Required Output\n"
        f"Write a ReviewResult JSON file to `{result_path}` that satisfies `{schema_path}`. "
        "The JSON must include review_id, mode, target, findings, and verification_evidence. "
        "Use the exact review_id, mode, and target from this contract.\n"
    )


def _review_result_schema_json() -> str:
    return json.dumps(_review_result_schema(), indent=2, sort_keys=True) + "\n"


def _review_result_schema() -> JsonObject:
    location_schema = {
        "type": "object",
        "required": ["path", "line", "scope"],
        "properties": {
            "path": {"type": ["string", "null"]},
            "line": {"type": ["integer", "null"], "minimum": 1},
            "scope": {"type": ["string", "null"]},
        },
        "additionalProperties": False,
    }
    finding_schema = {
        "type": "object",
        "required": [
            "finding_id",
            "mode",
            "severity",
            "status",
            "title",
            "evidence",
            "location",
            "recommendation",
            "waiver_rationale",
            "allowed_paths",
        ],
        "properties": {
            "finding_id": {"type": "string", "minLength": 1},
            "mode": {
                "enum": [
                    "everything",
                    "code_quality",
                    "architecture",
                    "source_of_truth_drift",
                ]
            },
            "severity": {"enum": ["P0", "P1", "P2", "P3"]},
            "status": {"enum": ["accepted", "waived", "needs_hitl"]},
            "title": {"type": "string", "minLength": 1},
            "evidence": {"type": "string", "minLength": 1},
            "location": location_schema,
            "recommendation": {"type": "string", "minLength": 1},
            "waiver_rationale": {"type": ["string", "null"]},
            "allowed_paths": {"type": "array", "items": {"type": "string", "minLength": 1}},
        },
        "additionalProperties": False,
    }
    verification_schema = {
        "type": "object",
        "required": ["command", "exit_code", "summary"],
        "properties": {
            "command": {"type": "string", "minLength": 1},
            "exit_code": {"type": "integer"},
            "summary": {"type": "string", "minLength": 1},
        },
        "additionalProperties": False,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["review_id", "mode", "target", "findings", "verification_evidence"],
        "properties": {
            "review_id": {"type": "string", "minLength": 1},
            "mode": {
                "enum": [
                    "everything",
                    "code_quality",
                    "architecture",
                    "source_of_truth_drift",
                ]
            },
            "target": {"type": "string", "minLength": 1},
            "findings": {
                "type": "array",
                "items": finding_schema,
            },
            "verification_evidence": {
                "type": "array",
                "minItems": 1,
                "items": verification_schema,
            },
        },
        "additionalProperties": False,
    }


def _load_review_result_file(path: Path) -> ReviewResult:
    from codex_supervisor.review_loop import validate_review_result_payload

    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_review_result_payload(payload)


def _review_result_source(request: ReviewLaunchRequest) -> tuple[Path, str] | None:
    final_message_file = request.repo_root / request.final_message_path
    if final_message_file.exists():
        return final_message_file, request.final_message_path
    result_file = request.repo_root / request.result_path
    if result_file.exists():
        return result_file, request.result_path
    return None


def _copy_review_result_artifact(request: ReviewLaunchRequest, source: Path) -> None:
    target = request.repo_root / request.result_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def _validate_review_result_identity(
    review_result: ReviewResult,
    request: ReviewLaunchRequest,
) -> None:
    if review_result.review_id != request.review_id:
        raise ValueError("review result review_id does not match launch request")
    if review_result.mode != request.mode:
        raise ValueError("review result mode does not match launch request")
    if review_result.target != request.target:
        raise ValueError("review result target does not match launch request")


def _needs_hitl_findings(review_result: ReviewResult) -> tuple[ReviewFinding, ...]:
    return tuple(finding for finding in review_result.findings if finding.status == "needs_hitl")


def _codex_review_argv(request: ReviewLaunchRequest, executable: str) -> tuple[str, ...]:
    repo_root = request.repo_root.resolve(strict=False)
    argv = [
        executable,
        "exec",
        "--json",
        "--output-schema",
        str((repo_root / request.schema_path).resolve(strict=False)),
        "--output-last-message",
        str((repo_root / request.final_message_path).resolve(strict=False)),
        "--sandbox",
        request.sandbox_mode,
        "--cd",
        str(repo_root),
    ]
    if request.model is not None:
        argv.extend(("--model", request.model))
    if request.approval_policy:
        argv.extend(("-c", f"approval_policy={json.dumps(request.approval_policy)}"))
    argv.append("-")
    return tuple(argv)


def _review_environment(request: ReviewLaunchRequest) -> LaunchEnvironmentResult:
    environment = _minimal_process_environment(os.environ)
    environment.update(request.environment or {})
    return build_codex_launch_environment(
        codex_home=request.codex_home,
        environment=environment,
    )


def _run_review_command(
    argv: tuple[str, ...],
    cwd: Path,
    environment: dict[str, str],
    *,
    stdin: str | None,
    timeout_seconds: float | None,
) -> CommandExecutionResult:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=environment,
        text=True,
        input=stdin,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )
    return CommandExecutionResult(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _failed_review_launch(
    request: ReviewLaunchRequest,
    *,
    failure_class: str,
    stdout: str = "",
    stderr: str = "",
    exit_code: int | None = 1,
    status: str = "failed",
) -> ReviewLaunchResult:
    _write_text_artifact(request.repo_root, request.stdout_path, stdout)
    _write_text_artifact(request.repo_root, request.stderr_path, stderr)
    _write_text_artifact(request.repo_root, request.jsonl_path, stdout)
    _write_text_artifact(
        request.repo_root,
        request.final_message_path,
        f"Codex review did not produce a completed ReviewResult: {failure_class}\n",
    )
    return ReviewLaunchResult(
        review_id=request.review_id,
        task_id=request.task_id,
        status=status,
        exit_code=exit_code,
        failure_class=failure_class,
        prompt_path=request.prompt_path,
        jsonl_path=request.jsonl_path,
        stdout_path=request.stdout_path,
        stderr_path=request.stderr_path,
        final_message_path=request.final_message_path,
    )


def _write_text_artifact(repo_root: Path, relative_path: str, content: str) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _timeout_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
