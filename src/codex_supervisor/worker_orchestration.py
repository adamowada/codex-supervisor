"""Worker launch orchestration and changed-path acceptance gates."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from codex_supervisor.planning import SupervisorTaskRecord, SupervisorTaskSummaryRecord
from codex_supervisor.worker_backends import (
    CommandExecutionResult,
    CommandRunner,
    WorkerLaunchRequest,
    WorkerLaunchResult,
    _minimal_process_environment,
)
from codex_supervisor.worker_launches import WorkerLaunchPreparation, prepare_worker_launch_request
from codex_supervisor.worktree_artifacts import ChangedPathViolation, validate_changed_files
from codex_supervisor.worktree_state import WorktreeStateSnapshot, inspect_worktree_state

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
    worktree_state: WorktreeStateSnapshot | None = None


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
    allow_degraded_jsonl: bool = False,
    environment: dict[str, str] | None = None,
    metadata: dict[str, object] | None = None,
    require_git_changed_files: bool = False,
    git_command_runner: CommandRunner | None = None,
    git_base_ref: str = "HEAD",
    git_executable: str = "git",
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
        allow_degraded_jsonl=allow_degraded_jsonl,
        environment=environment,
        metadata=metadata,
    )
    launch_result = backend.run(preparation.request)
    worktree_state: WorktreeStateSnapshot | None = None
    if require_git_changed_files and launch_result.status in {"completed", "needs_review"}:
        worktree_state = inspect_worktree_state(
            workspace_root=repo_root,
            worktree_path=preparation.request.worktree_path,
            allowed_paths=tuple(task.allowed_paths),
            command_runner=git_command_runner or _default_git_command_runner,
            base_ref=git_base_ref,
            git_executable=git_executable,
            environment={"GIT_OPTIONAL_LOCKS": "0"},
        )
    changed_files, source = _changed_files_for_validation(
        repo_root,
        diff_summary_path=preparation.request.diff_summary_path,
        launch_result=launch_result,
        worktree_state=worktree_state,
    )
    reported_changed_files = _reported_worker_result_changed_files(
        repo_root,
        launch_result.result_path,
    )
    support_artifact_files = _reported_worker_result_support_artifact_files(
        repo_root,
        launch_result.result_path,
    )
    validation_changed_files = _without_declared_support_artifacts(
        changed_files,
        support_artifact_files,
    )
    violations = validate_changed_files(validation_changed_files, tuple(task.allowed_paths))
    gated_result = _apply_changed_path_gate(
        launch_result,
        changed_files=validation_changed_files,
        changed_files_source=source,
        reported_changed_files=reported_changed_files,
        ignored_support_artifacts=tuple(
            path for path in changed_files if path not in validation_changed_files
        ),
        violations=violations,
        allowed_paths=tuple(task.allowed_paths),
        worktree_state=worktree_state,
    )
    return WorkerOrchestrationResult(
        preparation=preparation,
        launch_result=gated_result,
        changed_files=validation_changed_files,
        changed_files_source=source,
        changed_path_violations=violations,
        worktree_state=worktree_state,
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
    worktree_state: WorktreeStateSnapshot | None,
) -> tuple[tuple[str, ...], str]:
    if worktree_state is not None:
        if worktree_state.status == "completed":
            return worktree_state.changed_files, "git_worktree"
        return (), "git_worktree_failed"
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
    reported_changed_files: tuple[str, ...] | None,
    ignored_support_artifacts: tuple[str, ...],
    violations: tuple[ChangedPathViolation, ...],
    allowed_paths: tuple[str, ...],
    worktree_state: WorktreeStateSnapshot | None,
) -> WorkerLaunchResult:
    metadata = {
        **launch_result.metadata,
        "changed_path_validation": {
            "source": changed_files_source,
            "changed_files": list(changed_files),
            "reported_changed_files": (
                None if reported_changed_files is None else list(reported_changed_files)
            ),
            "allowed_paths": list(allowed_paths),
            "ignored_support_artifacts": list(ignored_support_artifacts),
            "violations": [_violation_payload(violation) for violation in violations],
        },
    }
    if worktree_state is not None:
        metadata["worktree_state"] = _worktree_state_payload(worktree_state)
    if (
        launch_result.status in {"completed", "needs_review"}
        and worktree_state is not None
        and worktree_state.status != "completed"
    ):
        return replace(
            launch_result,
            status="failed",
            result_path=None,
            exit_code=_failed_exit_code(launch_result.exit_code),
            changed_files=(),
            failure_class="worktree_state_unavailable",
            metadata=metadata,
        )
    if (
        launch_result.status in {"completed", "needs_review"}
        and worktree_state is not None
        and worktree_state.status == "completed"
    ):
        if violations:
            metadata["changed_path_violations"] = [
                _violation_payload(violation) for violation in violations
            ]
            if reported_changed_files is None:
                metadata["changed_files_mismatch"] = {
                    "git_detected_files": list(changed_files),
                    "worker_result_changed_files": None,
                }
            elif _normalized_path_set(reported_changed_files) != _normalized_path_set(
                changed_files
            ):
                metadata["changed_files_mismatch"] = {
                    "git_detected_files": list(changed_files),
                    "worker_result_changed_files": list(reported_changed_files),
                }
            return replace(
                launch_result,
                status="failed",
                exit_code=_failed_exit_code(launch_result.exit_code),
                changed_files=changed_files,
                failure_class="changed_paths_out_of_scope",
                metadata=metadata,
            )
        if reported_changed_files is None:
            metadata["changed_files_mismatch"] = {
                "git_detected_files": list(changed_files),
                "worker_result_changed_files": None,
            }
            return replace(
                launch_result,
                status="failed",
                exit_code=_failed_exit_code(launch_result.exit_code),
                changed_files=changed_files,
                failure_class="changed_files_mismatch",
                metadata=metadata,
            )
        if _normalized_path_set(reported_changed_files) != _normalized_path_set(changed_files):
            metadata["changed_files_mismatch"] = {
                "git_detected_files": list(changed_files),
                "worker_result_changed_files": list(reported_changed_files),
            }
            return replace(
                launch_result,
                status="failed",
                exit_code=_failed_exit_code(launch_result.exit_code),
                changed_files=changed_files,
                failure_class="changed_files_mismatch",
                metadata=metadata,
            )
    if violations:
        metadata["changed_path_violations"] = [
            _violation_payload(violation) for violation in violations
        ]
    if launch_result.status in {"completed", "needs_review"} and violations:
        return replace(
            launch_result,
            status="failed",
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


def _reported_worker_result_changed_files(
    repo_root: Path,
    result_path: str | None,
) -> tuple[str, ...] | None:
    if result_path is None:
        return None
    try:
        payload = json.loads((repo_root / result_path).read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    changed_files = payload.get("changed_files")
    if not isinstance(changed_files, list):
        return None
    return tuple(path for path in changed_files if isinstance(path, str))


def _reported_worker_result_support_artifact_files(
    repo_root: Path,
    result_path: str | None,
) -> tuple[str, ...]:
    if result_path is None:
        return ()
    try:
        payload = json.loads((repo_root / result_path).read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return ()
    if not isinstance(payload, dict):
        return ()
    paths: list[str] = []
    artifacts = payload.get("artifacts")
    if isinstance(artifacts, list):
        paths.extend(path for path in artifacts if isinstance(path, str))
    browser_smoke_results = payload.get("browser_smoke_results")
    if isinstance(browser_smoke_results, list):
        for item in browser_smoke_results:
            if not isinstance(item, dict):
                continue
            artifact = item.get("artifact")
            if isinstance(artifact, str):
                paths.append(artifact)
            browser_artifacts = item.get("artifacts")
            if isinstance(browser_artifacts, list):
                paths.extend(path for path in browser_artifacts if isinstance(path, str))
    return tuple(dict.fromkeys(_normalize_support_artifact(path) for path in paths))


def _without_declared_support_artifacts(
    changed_files: tuple[str, ...],
    support_artifact_files: tuple[str, ...],
) -> tuple[str, ...]:
    support_artifacts = {
        path
        for path in support_artifact_files
        if path == "artifacts" or path.startswith("artifacts/")
    }
    if not support_artifacts:
        return changed_files
    return tuple(
        path for path in changed_files if _normalize_support_artifact(path) not in support_artifacts
    )


def _normalize_support_artifact(path: str) -> str:
    return path.strip().replace("\\", "/").strip("/")


def _normalized_path_set(paths: tuple[str, ...]) -> set[str]:
    return {path.strip().replace("\\", "/") for path in paths if path.strip()}


def _violation_payload(violation: ChangedPathViolation) -> dict[str, str]:
    return {
        "path": violation.path,
        "reason": violation.reason,
    }


def _worktree_state_payload(snapshot: WorktreeStateSnapshot) -> dict[str, object]:
    return {
        "status": snapshot.status,
        "worktree_path": snapshot.worktree_path,
        "branch": snapshot.branch,
        "base_commit": snapshot.base_commit,
        "head_commit": snapshot.head_commit,
        "dirty": snapshot.dirty,
        "changed_files": list(snapshot.changed_files),
        "failure_class": snapshot.failure_class,
        "failure_reason": snapshot.failure_reason,
        "commands": [
            {
                "name": command.name,
                "argv": list(command.argv),
                "cwd": snapshot.worktree_path,
                "exit_code": command.exit_code,
                "stdout": command.stdout,
                "stderr": command.stderr,
            }
            for command in snapshot.commands
        ],
    }


def _default_git_command_runner(
    argv: tuple[str, ...],
    cwd: Path,
    environment: dict[str, str],
) -> CommandExecutionResult:
    process_environment = _minimal_process_environment(os.environ)
    process_environment.update(environment)
    process = subprocess.run(
        argv,
        cwd=cwd,
        env=process_environment,
        text=True,
        capture_output=True,
        check=False,
    )
    return CommandExecutionResult(
        exit_code=process.returncode,
        stdout=process.stdout,
        stderr=process.stderr,
    )
