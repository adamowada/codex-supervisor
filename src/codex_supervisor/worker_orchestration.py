"""Worker launch orchestration and changed-path acceptance gates."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from codex_supervisor.planning import SupervisorTaskRecord, SupervisorTaskSummaryRecord
from codex_supervisor.worker_backends import WorkerLaunchRequest, WorkerLaunchResult
from codex_supervisor.worker_launches import WorkerLaunchPreparation, prepare_worker_launch_request
from codex_supervisor.worktree_artifacts import ChangedPathViolation, validate_changed_files

TaskRecord = SupervisorTaskRecord | SupervisorTaskSummaryRecord


class WorkerBackend(Protocol):
    """Backend surface required by the orchestrator."""

    def run(self, request: WorkerLaunchRequest) -> WorkerLaunchResult:
        """Run one prepared launch request."""


@dataclass(frozen=True)
class WorkerOrchestrationResult:
    """Prepared launch metadata plus backend result after acceptance gates."""

    preparation: WorkerLaunchPreparation
    launch_result: WorkerLaunchResult
    changed_files: tuple[str, ...]
    changed_files_source: str
    changed_path_violations: tuple[ChangedPathViolation, ...]


def orchestrate_worker_launch(
    task: TaskRecord,
    *,
    backend: WorkerBackend,
    worker_run_id: str,
    repo_root: Path,
    result_schema_path: str,
    prompt: str,
    rendered_goal_contract: str,
    sandbox_mode: str,
    approval_policy: str,
    codex_home: str | None = None,
    codex_config_path: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    service_tier: str | None = None,
    native_goal_mode: bool = False,
    ignore_user_config: bool = False,
    environment: dict[str, str] | None = None,
    metadata: dict[str, object] | None = None,
) -> WorkerOrchestrationResult:
    """Prepare and run one worker backend, then apply changed-path acceptance gates."""

    preparation = prepare_worker_launch_request(
        task,
        worker_run_id=worker_run_id,
        repo_root=repo_root,
        result_schema_path=result_schema_path,
        prompt=prompt,
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
        environment=environment,
        metadata=metadata,
    )
    launch_result = backend.run(preparation.request)
    changed_files, source = _changed_files_for_validation(
        repo_root,
        diff_summary_path=preparation.request.diff_summary_path,
        launch_result=launch_result,
    )
    violations = validate_changed_files(changed_files, tuple(task.allowed_paths))
    gated_result = _apply_changed_path_gate(
        launch_result,
        changed_files=changed_files,
        changed_files_source=source,
        violations=violations,
        allowed_paths=tuple(task.allowed_paths),
    )
    return WorkerOrchestrationResult(
        preparation=preparation,
        launch_result=gated_result,
        changed_files=changed_files,
        changed_files_source=source,
        changed_path_violations=violations,
    )


def load_diff_summary_changed_files(
    repo_root: Path,
    diff_summary_path: str | None,
) -> tuple[str, ...]:
    """Load newline-delimited repo-relative paths from a worker diff summary."""

    if diff_summary_path is None:
        return ()
    try:
        content = (repo_root / diff_summary_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ()
    return tuple(line.strip() for line in content.splitlines() if line.strip())


def _changed_files_for_validation(
    repo_root: Path,
    *,
    diff_summary_path: str | None,
    launch_result: WorkerLaunchResult,
) -> tuple[tuple[str, ...], str]:
    diff_summary_files = load_diff_summary_changed_files(repo_root, diff_summary_path)
    if diff_summary_files:
        return diff_summary_files, "diff_summary"
    if launch_result.changed_files:
        return launch_result.changed_files, "backend_result"
    return (), "none"


def _apply_changed_path_gate(
    launch_result: WorkerLaunchResult,
    *,
    changed_files: tuple[str, ...],
    changed_files_source: str,
    violations: tuple[ChangedPathViolation, ...],
    allowed_paths: tuple[str, ...],
) -> WorkerLaunchResult:
    metadata = {
        **launch_result.metadata,
        "changed_path_validation": {
            "source": changed_files_source,
            "changed_files": list(changed_files),
            "allowed_paths": list(allowed_paths),
            "violations": [_violation_payload(violation) for violation in violations],
        },
    }
    if violations:
        metadata["changed_path_violations"] = [
            _violation_payload(violation) for violation in violations
        ]
    if launch_result.status == "completed" and violations:
        return replace(
            launch_result,
            status="failed",
            result_path=None,
            exit_code=_failed_exit_code(launch_result.exit_code),
            changed_files=changed_files,
            failure_class="changed_paths_out_of_scope",
            metadata=metadata,
        )
    return replace(
        launch_result,
        changed_files=changed_files,
        metadata=metadata,
    )


def _failed_exit_code(exit_code: int | None) -> int:
    if exit_code is None or exit_code == 0:
        return 1
    return exit_code


def _violation_payload(violation: ChangedPathViolation) -> dict[str, str]:
    return {
        "path": violation.path,
        "reason": violation.reason,
    }
