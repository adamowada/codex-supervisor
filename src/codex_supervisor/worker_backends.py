"""Worker backend protocol and deterministic contract backend implementation."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from codex_supervisor.execution_surface import (
    CODEX_EXEC_BACKEND,
    CODEX_REASONING_EFFORT_CONFIG_KEY,
    codex_exec_capability_mappings,
    goal_mode_decision,
)
from codex_supervisor.worker_results import (
    WorkerResult,
    WorkerResultError,
    validate_worker_result_file,
)
from codex_supervisor.worktree_artifacts import is_ignored_runtime_path

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class WorkerLaunchRequest:
    """Input required to run one worker backend attempt."""

    worker_run_id: str
    task_id: str
    repo_root: Path
    worktree_path: Path
    result_path: str
    prompt_path: str
    jsonl_path: str
    stdout_path: str
    stderr_path: str
    final_message_path: str
    diff_summary_path: str
    evidence_manifest_path: str
    result_schema_path: str
    prompt: str
    rendered_goal_contract: str
    sandbox_mode: str
    approval_policy: str
    allowed_paths: tuple[str, ...]
    verification_commands: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    codex_home: str | None = None
    codex_config_path: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    service_tier: str | None = None
    native_goal_mode: bool = False
    ignore_user_config: bool = False
    preflight_timeout_seconds: float | None = 30.0
    launch_timeout_seconds: float | None = 3600.0
    environment: dict[str, str] = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)
    allow_degraded_jsonl: bool = False


@dataclass(frozen=True)
class WorkerLaunchResult:
    """Backend launch outcome before planning ingestion."""

    worker_run_id: str
    task_id: str
    status: str
    result_path: str | None = None
    exit_code: int | None = None
    duration_seconds: float | None = None
    changed_files: tuple[str, ...] = ()
    prompt_path: str | None = None
    jsonl_path: str | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None
    final_message_path: str | None = None
    diff_summary_path: str | None = None
    failure_class: str | None = None
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class CommandExecutionResult:
    """Captured process result for backend preflight commands."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""
    stdout_bytes: bytes = b""
    stderr_bytes: bytes = b""


type CommandRunner = Callable[[tuple[str, ...], Path, dict[str, str]], CommandExecutionResult]
type CommandStartCallback = Callable[[int | None], None]


@dataclass(frozen=True)
class LaunchEnvironmentResult:
    """Effective worker subprocess environment or a fail-closed reason."""

    environment: dict[str, str]
    failure_class: str | None = None
    stderr: str = ""


@dataclass(frozen=True)
class CodexExecPreflightResult:
    """Codex executable/version evidence and launch command preview."""

    executable_path: str | None
    resolution_method: str
    version_command: tuple[str, ...]
    version_exit_code: int | None
    version_stdout: str
    version_stderr: str
    failure_class: str | None
    argv: tuple[str, ...]
    metadata: JsonObject


@dataclass(frozen=True)
class CodexCapabilityProbeResult:
    """Resolved model/reasoning launch capabilities before the worker prompt runs."""

    request: WorkerLaunchRequest
    failure_class: str | None
    stderr: str
    metadata: JsonObject


@dataclass(frozen=True)
class CodexExecutableResolution:
    """Resolved Codex executable path plus fail-closed launch diagnostics."""

    executable_path: str | None
    resolution_method: str
    failure_class: str | None = None
    stderr: str = ""


@dataclass(frozen=True)
class CodexExecBackend:
    """Codex Exec backend preflight, argv builder, and launch wrapper.

    Launch stays behind ``launch_enabled`` so tests can prove process behavior with an injected
    runner without invoking the local Codex binary.
    """

    codex_executable: str | None = None
    command_runner: CommandRunner | None = None
    launch_enabled: bool = False

    def preflight(self, request: WorkerLaunchRequest) -> CodexExecPreflightResult:
        """Resolve Codex, run version preflight, and build the intended argv list."""

        executable_resolution = _resolve_codex_executable(self.codex_executable)
        executable_path = executable_resolution.executable_path
        resolution_method = executable_resolution.resolution_method
        environment_result = _build_launch_environment(request)
        option_failure = _unsupported_launch_option_failure(request)
        effective_request = request
        capability_probe = CodexCapabilityProbeResult(
            request=request,
            failure_class=None,
            stderr="",
            metadata={"status": "skipped", "reason": "no_requested_model_or_reasoning"},
        )
        argv: tuple[str, ...] = ()
        version_command = (executable_path, "--version") if executable_path else ()
        version_exit_code: int | None = None
        version_stdout = ""
        version_stderr = ""
        failure_class = None
        if executable_resolution.failure_class is not None:
            failure_class = executable_resolution.failure_class
            version_stderr = executable_resolution.stderr
        elif executable_path is None:
            failure_class = "codex_cli_unavailable"
            version_stderr = "codex executable was not found on PATH"
        elif environment_result.failure_class is not None:
            failure_class = environment_result.failure_class
            version_stderr = environment_result.stderr
        elif option_failure is not None:
            failure_class = option_failure[0]
            version_stderr = option_failure[1]
        else:
            try:
                version_result = _run_command(
                    self.command_runner,
                    version_command,
                    request.worktree_path,
                    environment_result.environment,
                    timeout_seconds=request.preflight_timeout_seconds,
                )
            except OSError as exc:
                failure_class = _classify_version_exception(executable_path, exc)
                version_stderr = str(exc)
            except subprocess.TimeoutExpired as exc:
                failure_class = "codex_version_timeout"
                version_exit_code = 124
                version_stdout = _timeout_text(exc.stdout)
                version_stderr = f"codex --version timed out after {exc.timeout} seconds"
            else:
                version_exit_code = version_result.exit_code
                version_stdout = version_result.stdout
                version_stderr = version_result.stderr
                if version_result.exit_code != 0:
                    failure_class = _classify_version_failure(
                        executable_path,
                        version_result.stderr,
                    )
        if failure_class is None and executable_path is not None:
            capability_probe = _probe_codex_launch_capabilities(
                request,
                executable_path=executable_path,
                environment=environment_result.environment,
                command_runner=self.command_runner,
                probe_enabled=self.launch_enabled,
            )
            effective_request = capability_probe.request
            if capability_probe.failure_class is not None:
                failure_class = capability_probe.failure_class
                version_stderr = capability_probe.stderr
        argv = _build_codex_exec_argv(effective_request, executable_path) if executable_path else ()
        metadata = _codex_exec_metadata(
            effective_request,
            executable_path=executable_path,
            resolution_method=resolution_method,
            version_command=version_command,
            version_exit_code=version_exit_code,
            version_stdout=version_stdout,
            version_stderr=version_stderr,
            failure_class=failure_class,
            argv=argv,
            environment=environment_result.environment,
        )
        metadata["requested_capabilities"] = {
            "model": request.model,
            "reasoning_effort": request.reasoning_effort,
        }
        metadata["resolved_capabilities"] = {
            "model": effective_request.model,
            "reasoning_effort": effective_request.reasoning_effort,
        }
        metadata["capability_preflight"] = capability_probe.metadata
        return CodexExecPreflightResult(
            executable_path=executable_path,
            resolution_method=resolution_method,
            version_command=version_command,
            version_exit_code=version_exit_code,
            version_stdout=version_stdout,
            version_stderr=version_stderr,
            failure_class=failure_class,
            argv=argv,
            metadata=metadata,
        )

    def run(self, request: WorkerLaunchRequest) -> WorkerLaunchResult:
        """Run Codex Exec preflight and, when enabled, the prepared exec argv."""

        composed_prompt = compose_worker_prompt(request)
        _write_text_artifact(request.repo_root, request.prompt_path, composed_prompt)
        preflight = self.preflight(request)
        if preflight.failure_class is not None:
            _write_codex_exec_evidence(
                request,
                event="codex_exec.preflight_failed",
                stdout=preflight.version_stdout,
                stderr=preflight.version_stderr,
                final_message=f"Codex Exec preflight failed: {preflight.failure_class}\n",
                preflight=preflight,
            )
            return WorkerLaunchResult(
                worker_run_id=request.worker_run_id,
                task_id=request.task_id,
                status="failed",
                exit_code=preflight.version_exit_code or 1,
                duration_seconds=0.0,
                prompt_path=request.prompt_path,
                jsonl_path=request.jsonl_path,
                stdout_path=request.stdout_path,
                stderr_path=request.stderr_path,
                final_message_path=request.final_message_path,
                diff_summary_path=request.diff_summary_path,
                failure_class=preflight.failure_class,
                metadata=preflight.metadata,
            )
        if not self.launch_enabled:
            metadata = {
                **preflight.metadata,
                "launch_decision": "stage6b_preflight_only_launch_disabled",
            }
            _write_codex_exec_evidence(
                request,
                event="codex_exec.preflight_ready",
                stdout="Codex Exec preflight passed; launch skipped by Stage 6B.\n",
                stderr="",
                final_message="Codex Exec preflight passed; live launch is not enabled.\n",
                preflight=preflight,
            )
            return WorkerLaunchResult(
                worker_run_id=request.worker_run_id,
                task_id=request.task_id,
                status="blocked",
                exit_code=0,
                duration_seconds=0.0,
                prompt_path=request.prompt_path,
                jsonl_path=request.jsonl_path,
                stdout_path=request.stdout_path,
                stderr_path=request.stderr_path,
                final_message_path=request.final_message_path,
                diff_summary_path=request.diff_summary_path,
                metadata=metadata,
            )
        schema_failure = _ensure_result_schema_available(request)
        if schema_failure is not None:
            metadata = {
                **preflight.metadata,
                "launch_decision": "result_schema_unavailable",
            }
            _write_codex_exec_evidence(
                request,
                event="codex_exec.result_schema_unavailable",
                stdout="",
                stderr=schema_failure,
                final_message=f"Codex Exec result schema is unavailable: {schema_failure}\n",
                preflight=preflight,
                extra_event={"failure_class": "worker_result_schema_unavailable"},
            )
            return WorkerLaunchResult(
                worker_run_id=request.worker_run_id,
                task_id=request.task_id,
                status="failed",
                exit_code=1,
                duration_seconds=0.0,
                prompt_path=request.prompt_path,
                jsonl_path=request.jsonl_path,
                stdout_path=request.stdout_path,
                stderr_path=request.stderr_path,
                final_message_path=request.final_message_path,
                diff_summary_path=request.diff_summary_path,
                failure_class="worker_result_schema_unavailable",
                metadata=metadata,
            )
        environment_result = _build_launch_environment(request)
        if environment_result.failure_class is not None:
            _write_codex_exec_evidence(
                request,
                event="codex_exec.environment_failed",
                stdout="",
                stderr=environment_result.stderr,
                final_message=(
                    f"Codex Exec environment failed: {environment_result.failure_class}\n"
                ),
                preflight=preflight,
            )
            return WorkerLaunchResult(
                worker_run_id=request.worker_run_id,
                task_id=request.task_id,
                status="failed",
                exit_code=1,
                duration_seconds=0.0,
                prompt_path=request.prompt_path,
                jsonl_path=request.jsonl_path,
                stdout_path=request.stdout_path,
                stderr_path=request.stderr_path,
                final_message_path=request.final_message_path,
                diff_summary_path=request.diff_summary_path,
                failure_class=environment_result.failure_class,
                metadata=preflight.metadata,
            )
        started_at = time.perf_counter()
        try:
            exec_result = _run_command(
                self.command_runner,
                preflight.argv,
                request.worktree_path,
                environment_result.environment,
                stdin=composed_prompt,
                timeout_seconds=request.launch_timeout_seconds,
                on_start=_liveness_start_callback(
                    request,
                    preflight,
                    "exec_started",
                ),
            )
            _write_liveness_probe(
                request,
                preflight=preflight,
                stage="exec_exited",
                exit_code=exec_result.exit_code,
            )
        except KeyboardInterrupt:
            duration_seconds = time.perf_counter() - started_at
            _write_liveness_probe(
                request,
                preflight=preflight,
                stage="exec_interrupted",
            )
            metadata = _codex_exec_launch_metadata(
                preflight,
                launch_decision="exec_interrupted",
                exec_exit_code=None,
                duration_seconds=duration_seconds,
            )
            _write_codex_exec_evidence(
                request,
                event="codex_exec.interrupted",
                stdout="",
                stderr="Codex Exec launch was interrupted; child process cleanup was requested.\n",
                final_message="Codex Exec launch was interrupted before producing a result.\n",
                preflight=preflight,
                extra_event={"failure_class": "codex_exec_interrupted"},
                preserve_existing_jsonl=True,
                preserve_existing_diff_summary=True,
            )
            return WorkerLaunchResult(
                worker_run_id=request.worker_run_id,
                task_id=request.task_id,
                status="failed",
                exit_code=130,
                duration_seconds=duration_seconds,
                prompt_path=request.prompt_path,
                jsonl_path=request.jsonl_path,
                stdout_path=request.stdout_path,
                stderr_path=request.stderr_path,
                final_message_path=request.final_message_path,
                diff_summary_path=request.diff_summary_path,
                failure_class="codex_exec_interrupted",
                metadata=metadata,
            )
        except OSError as exc:
            duration_seconds = time.perf_counter() - started_at
            _write_liveness_probe(
                request,
                preflight=preflight,
                stage="exec_failed_to_start",
            )
            metadata = _codex_exec_launch_metadata(
                preflight,
                launch_decision="exec_raised",
                exec_exit_code=None,
                duration_seconds=duration_seconds,
            )
            _write_codex_exec_evidence(
                request,
                event="codex_exec.failed",
                stdout="",
                stderr=str(exc),
                final_message="Codex Exec launch failed before producing a result.\n",
                preflight=preflight,
                extra_event={"failure_class": "codex_exec_failed"},
                preserve_existing_jsonl=True,
                preserve_existing_diff_summary=True,
            )
            return WorkerLaunchResult(
                worker_run_id=request.worker_run_id,
                task_id=request.task_id,
                status="failed",
                exit_code=1,
                duration_seconds=duration_seconds,
                prompt_path=request.prompt_path,
                jsonl_path=request.jsonl_path,
                stdout_path=request.stdout_path,
                stderr_path=request.stderr_path,
                final_message_path=request.final_message_path,
                diff_summary_path=request.diff_summary_path,
                failure_class="codex_exec_failed",
                metadata=metadata,
            )
        except subprocess.TimeoutExpired as exc:
            duration_seconds = time.perf_counter() - started_at
            _write_liveness_probe(
                request,
                preflight=preflight,
                stage="exec_timeout",
                exit_code=124,
            )
            metadata = _codex_exec_launch_metadata(
                preflight,
                launch_decision="exec_timeout",
                exec_exit_code=124,
                duration_seconds=duration_seconds,
            )
            _write_codex_exec_evidence(
                request,
                event="codex_exec.timeout",
                stdout=_timeout_text(exc.stdout),
                stderr=f"codex exec timed out after {exc.timeout} seconds",
                final_message="Codex Exec launch timed out before producing a result.\n",
                preflight=preflight,
                extra_event={"failure_class": "codex_exec_timeout"},
                process_jsonl=_timeout_text(exc.stdout),
                process_jsonl_bytes=exc.stdout if isinstance(exc.stdout, bytes) else b"",
                preserve_existing_jsonl=True,
                preserve_existing_diff_summary=True,
            )
            return WorkerLaunchResult(
                worker_run_id=request.worker_run_id,
                task_id=request.task_id,
                status="failed",
                exit_code=124,
                duration_seconds=duration_seconds,
                prompt_path=request.prompt_path,
                jsonl_path=request.jsonl_path,
                stdout_path=request.stdout_path,
                stderr_path=request.stderr_path,
                final_message_path=request.final_message_path,
                diff_summary_path=request.diff_summary_path,
                failure_class="codex_exec_timeout",
                metadata=metadata,
            )
        duration_seconds = time.perf_counter() - started_at
        if exec_result.exit_code != 0:
            retry = _codex_exec_capability_retry(
                request,
                preflight,
                exec_result,
                command_runner=self.command_runner,
            )
            if retry is not None:
                retry_request, retry_preflight, retry_metadata = retry
                retry_started_at = time.perf_counter()
                try:
                    retry_exec_result = _run_command(
                        self.command_runner,
                        retry_preflight.argv,
                        retry_request.worktree_path,
                        environment_result.environment,
                        stdin=composed_prompt,
                        timeout_seconds=retry_request.launch_timeout_seconds,
                        on_start=_liveness_start_callback(
                            retry_request,
                            retry_preflight,
                            "exec_retry_started",
                        ),
                    )
                except OSError, subprocess.TimeoutExpired, KeyboardInterrupt:
                    pass
                else:
                    _write_liveness_probe(
                        retry_request,
                        preflight=retry_preflight,
                        stage="exec_retry_exited",
                        exit_code=retry_exec_result.exit_code,
                    )
                    if retry_exec_result.exit_code == 0:
                        request = retry_request
                        preflight = replace(
                            retry_preflight,
                            metadata={
                                **retry_preflight.metadata,
                                "capability_retry": {
                                    **retry_metadata,
                                    "retry_exit_code": retry_exec_result.exit_code,
                                    "retry_duration_seconds": (
                                        time.perf_counter() - retry_started_at
                                    ),
                                },
                            },
                        )
                        exec_result = retry_exec_result
                        duration_seconds = time.perf_counter() - started_at
        if exec_result.exit_code != 0:
            _write_codex_exec_evidence(
                request,
                event="codex_exec.failed",
                stdout=exec_result.stdout,
                stderr=exec_result.stderr,
                final_message=f"Codex Exec failed with exit code {exec_result.exit_code}.\n",
                preflight=preflight,
                extra_event={
                    "exec_exit_code": exec_result.exit_code,
                    "failure_class": "codex_exec_failed",
                },
                process_jsonl=exec_result.stdout,
                process_jsonl_bytes=exec_result.stdout_bytes,
                preserve_existing_jsonl=True,
                preserve_existing_diff_summary=True,
                preserve_existing_final_message=True,
                stdout_bytes=exec_result.stdout_bytes,
                stderr_bytes=exec_result.stderr_bytes,
            )
            completed_worker_result = _load_canonical_worker_result(request)
            jsonl_failure = _jsonl_validation_failure(request)
            if completed_worker_result is not None and jsonl_failure is None:
                _copy_canonical_worker_result(request)
                metadata = _codex_exec_launch_metadata(
                    preflight,
                    launch_decision="executed_with_worker_result_after_nonzero_exit",
                    exec_exit_code=exec_result.exit_code,
                    duration_seconds=duration_seconds,
                )
                missing_evidence = _write_evidence_manifest(
                    request,
                    status=completed_worker_result.status,
                    launch_decision="executed_with_worker_result_after_nonzero_exit",
                )
                metadata["evidence_manifest_path"] = request.evidence_manifest_path
                if missing_evidence:
                    metadata["missing_evidence_paths"] = list(missing_evidence)
                    return WorkerLaunchResult(
                        worker_run_id=request.worker_run_id,
                        task_id=request.task_id,
                        status="failed",
                        exit_code=1,
                        duration_seconds=duration_seconds,
                        prompt_path=request.prompt_path,
                        jsonl_path=request.jsonl_path,
                        stdout_path=request.stdout_path,
                        stderr_path=request.stderr_path,
                        final_message_path=request.final_message_path,
                        diff_summary_path=request.diff_summary_path,
                        failure_class="worker_evidence_missing",
                        metadata=metadata,
                    )
                return WorkerLaunchResult(
                    worker_run_id=request.worker_run_id,
                    task_id=request.task_id,
                    status=completed_worker_result.status,
                    result_path=request.result_path,
                    exit_code=exec_result.exit_code,
                    duration_seconds=duration_seconds,
                    changed_files=completed_worker_result.changed_files,
                    prompt_path=request.prompt_path,
                    jsonl_path=request.jsonl_path,
                    stdout_path=request.stdout_path,
                    stderr_path=request.stderr_path,
                    final_message_path=request.final_message_path,
                    diff_summary_path=request.diff_summary_path,
                    failure_class=(
                        None
                        if completed_worker_result.status in {"completed", "needs_review"}
                        else completed_worker_result.status
                    ),
                    metadata={
                        **metadata,
                        "worker_result_source": "output_last_message",
                        "canonical_output_last_message_path": request.final_message_path,
                    },
                )
            metadata = _codex_exec_launch_metadata(
                preflight,
                launch_decision="exec_failed",
                exec_exit_code=exec_result.exit_code,
                duration_seconds=duration_seconds,
            )
            if jsonl_failure is not None:
                metadata["jsonl_validation"] = jsonl_failure
            return WorkerLaunchResult(
                worker_run_id=request.worker_run_id,
                task_id=request.task_id,
                status="failed",
                exit_code=exec_result.exit_code,
                duration_seconds=duration_seconds,
                prompt_path=request.prompt_path,
                jsonl_path=request.jsonl_path,
                stdout_path=request.stdout_path,
                stderr_path=request.stderr_path,
                final_message_path=request.final_message_path,
                diff_summary_path=request.diff_summary_path,
                failure_class="codex_exec_failed",
                metadata=metadata,
            )
        _write_codex_exec_evidence(
            request,
            event="codex_exec.completed",
            stdout=exec_result.stdout,
            stderr=exec_result.stderr,
            final_message="Codex Exec completed without a Worker Result JSON final message.\n",
            preflight=preflight,
            extra_event={"exec_exit_code": exec_result.exit_code},
            process_jsonl=exec_result.stdout,
            process_jsonl_bytes=exec_result.stdout_bytes,
            preserve_existing_final_message=True,
            write_final_message_if_missing=False,
            preserve_existing_jsonl=True,
            preserve_existing_diff_summary=True,
            stdout_bytes=exec_result.stdout_bytes,
            stderr_bytes=exec_result.stderr_bytes,
        )
        jsonl_failure = _jsonl_validation_failure(request)
        result_file = request.repo_root / request.final_message_path
        if not result_file.exists():
            metadata = _codex_exec_launch_metadata(
                preflight,
                launch_decision="worker_result_missing",
                exec_exit_code=exec_result.exit_code,
                duration_seconds=duration_seconds,
            )
            _write_codex_exec_evidence(
                request,
                event="codex_exec.worker_result_missing",
                stdout=exec_result.stdout,
                stderr=exec_result.stderr,
                final_message="Codex Exec completed without a Worker Result JSON final message.\n",
                preflight=preflight,
                extra_event={
                    "exec_exit_code": exec_result.exit_code,
                    "failure_class": "worker_result_missing",
                    "result_path": request.final_message_path,
                },
                process_jsonl=exec_result.stdout,
                process_jsonl_bytes=exec_result.stdout_bytes,
                preserve_existing_jsonl=True,
                preserve_existing_diff_summary=True,
                stdout_bytes=exec_result.stdout_bytes,
                stderr_bytes=exec_result.stderr_bytes,
            )
            return WorkerLaunchResult(
                worker_run_id=request.worker_run_id,
                task_id=request.task_id,
                status="failed",
                exit_code=exec_result.exit_code,
                duration_seconds=duration_seconds,
                prompt_path=request.prompt_path,
                jsonl_path=request.jsonl_path,
                stdout_path=request.stdout_path,
                stderr_path=request.stderr_path,
                final_message_path=request.final_message_path,
                diff_summary_path=request.diff_summary_path,
                failure_class="worker_result_missing",
                metadata=metadata,
            )
        try:
            worker_result = validate_worker_result_file(
                result_file,
                repo_root=request.repo_root,
                changed_files_root=request.worktree_path,
                artifact_root=request.worktree_path,
                result_path=request.final_message_path,
                worker_run_id=request.worker_run_id,
                allowed_paths=request.allowed_paths,
                verification_commands=request.verification_commands,
                acceptance_criteria=request.acceptance_criteria,
            )
        except (OSError, WorkerResultError, json.JSONDecodeError) as exc:
            metadata = _codex_exec_launch_metadata(
                preflight,
                launch_decision="worker_result_invalid",
                exec_exit_code=exec_result.exit_code,
                duration_seconds=duration_seconds,
            )
            _write_codex_exec_evidence(
                request,
                event="codex_exec.worker_result_invalid",
                stdout=exec_result.stdout,
                stderr=exec_result.stderr,
                final_message=f"Codex Exec produced an invalid Worker Result: {exc}\n",
                preflight=preflight,
                extra_event={
                    "exec_exit_code": exec_result.exit_code,
                    "failure_class": "worker_result_invalid",
                    "result_path": request.final_message_path,
                },
                process_jsonl=exec_result.stdout,
                process_jsonl_bytes=exec_result.stdout_bytes,
                preserve_existing_final_message=True,
                preserve_existing_jsonl=True,
                preserve_existing_diff_summary=True,
                stdout_bytes=exec_result.stdout_bytes,
                stderr_bytes=exec_result.stderr_bytes,
            )
            return WorkerLaunchResult(
                worker_run_id=request.worker_run_id,
                task_id=request.task_id,
                status="failed",
                exit_code=1,
                duration_seconds=duration_seconds,
                prompt_path=request.prompt_path,
                jsonl_path=request.jsonl_path,
                stdout_path=request.stdout_path,
                stderr_path=request.stderr_path,
                final_message_path=request.final_message_path,
                diff_summary_path=request.diff_summary_path,
                failure_class="worker_result_invalid",
                metadata=metadata,
            )
        if jsonl_failure is not None:
            metadata = _codex_exec_launch_metadata(
                preflight,
                launch_decision="jsonl_invalid",
                exec_exit_code=exec_result.exit_code,
                duration_seconds=duration_seconds,
            )
            metadata["jsonl_validation"] = jsonl_failure
            return WorkerLaunchResult(
                worker_run_id=request.worker_run_id,
                task_id=request.task_id,
                status="failed",
                exit_code=1,
                duration_seconds=duration_seconds,
                prompt_path=request.prompt_path,
                jsonl_path=request.jsonl_path,
                stdout_path=request.stdout_path,
                stderr_path=request.stderr_path,
                final_message_path=request.final_message_path,
                diff_summary_path=request.diff_summary_path,
                failure_class=jsonl_failure["failure_class"],
                metadata=metadata,
            )
        _copy_worker_result_support_artifacts(request, worker_result)
        _copy_canonical_worker_result(request)
        metadata = _codex_exec_launch_metadata(
            preflight,
            launch_decision="executed",
            exec_exit_code=exec_result.exit_code,
            duration_seconds=duration_seconds,
        )
        _write_codex_exec_evidence(
            request,
            event="codex_exec.completed",
            stdout=exec_result.stdout,
            stderr=exec_result.stderr,
            final_message="Codex Exec completed and produced a Worker Result JSON final message.\n",
            preflight=preflight,
            extra_event={
                "exec_exit_code": exec_result.exit_code,
                "result_path": request.result_path,
                "canonical_output_last_message_path": request.final_message_path,
            },
            process_jsonl=exec_result.stdout,
            process_jsonl_bytes=exec_result.stdout_bytes,
            preserve_existing_final_message=True,
            preserve_existing_jsonl=True,
            preserve_existing_diff_summary=True,
            stdout_bytes=exec_result.stdout_bytes,
            stderr_bytes=exec_result.stderr_bytes,
        )
        missing_evidence = _write_evidence_manifest(
            request,
            status=worker_result.status,
            launch_decision="executed",
        )
        metadata["evidence_manifest_path"] = request.evidence_manifest_path
        if missing_evidence:
            metadata["missing_evidence_paths"] = list(missing_evidence)
            return WorkerLaunchResult(
                worker_run_id=request.worker_run_id,
                task_id=request.task_id,
                status="failed",
                exit_code=1,
                duration_seconds=duration_seconds,
                prompt_path=request.prompt_path,
                jsonl_path=request.jsonl_path,
                stdout_path=request.stdout_path,
                stderr_path=request.stderr_path,
                final_message_path=request.final_message_path,
                diff_summary_path=request.diff_summary_path,
                failure_class="worker_evidence_missing",
                metadata=metadata,
            )
        return WorkerLaunchResult(
            worker_run_id=request.worker_run_id,
            task_id=request.task_id,
            status=worker_result.status,
            result_path=request.result_path,
            exit_code=exec_result.exit_code,
            duration_seconds=duration_seconds,
            changed_files=worker_result.changed_files,
            prompt_path=request.prompt_path,
            jsonl_path=request.jsonl_path,
            stdout_path=request.stdout_path,
            stderr_path=request.stderr_path,
            final_message_path=request.final_message_path,
            diff_summary_path=request.diff_summary_path,
            metadata={
                **metadata,
                "worker_result_source": "output_last_message",
                "canonical_output_last_message_path": request.final_message_path,
            },
        )


@dataclass(frozen=True)
class ContractWorkerBackend:
    """Deterministic local backend used to prove the worker result ingestion contract."""

    changed_files: tuple[str, ...]
    summary: str = "Contract worker completed the requested slice."
    risks: tuple[str, ...] = ("Contract backend does not launch live Codex.",)
    follow_up_tasks: tuple[str, ...] = ()
    failure_class: str | None = None

    def run(self, request: WorkerLaunchRequest) -> WorkerLaunchResult:
        """Emit deterministic worker evidence without launching Codex."""

        _write_text_artifact(request.repo_root, request.prompt_path, request.prompt)
        _write_liveness_probe(request, stage="contract_worker_started")
        if self.failure_class is not None:
            _write_text_artifact(request.repo_root, request.stdout_path, "")
            _write_text_artifact(
                request.repo_root,
                request.stderr_path,
                f"Contract worker failed: {self.failure_class}\n",
            )
            _write_text_artifact(
                request.repo_root,
                request.final_message_path,
                f"Contract worker failed: {self.failure_class}\n",
            )
            _write_text_artifact(request.repo_root, request.diff_summary_path, "")
            _write_text_artifact(
                request.repo_root,
                request.jsonl_path,
                json.dumps(
                    {
                        "event": "contract_worker.failed",
                        "failure_class": self.failure_class,
                    },
                    sort_keys=True,
                )
                + "\n",
            )
            _write_liveness_probe(request, stage="contract_worker_failed", exit_code=1)
            return WorkerLaunchResult(
                worker_run_id=request.worker_run_id,
                task_id=request.task_id,
                status="failed",
                exit_code=1,
                duration_seconds=0.0,
                prompt_path=request.prompt_path,
                jsonl_path=request.jsonl_path,
                stdout_path=request.stdout_path,
                stderr_path=request.stderr_path,
                final_message_path=request.final_message_path,
                diff_summary_path=request.diff_summary_path,
                failure_class=self.failure_class,
                metadata={"backend": "contract_worker", "prompt_length": len(request.prompt)},
            )

        result_file = request.repo_root / request.result_path
        result_file.parent.mkdir(parents=True, exist_ok=True)
        _write_text_artifact(request.repo_root, request.stdout_path, self.summary + "\n")
        _write_text_artifact(request.repo_root, request.stderr_path, "")
        _write_text_artifact(request.repo_root, request.final_message_path, self.summary + "\n")
        _write_text_artifact(
            request.repo_root,
            request.diff_summary_path,
            "\n".join(self.changed_files) + ("\n" if self.changed_files else ""),
        )
        _write_text_artifact(
            request.repo_root,
            request.jsonl_path,
            '{"event":"contract_worker.completed"}\n',
        )
        payload = {
            "worker_run_id": request.worker_run_id,
            "status": "completed",
            "summary": self.summary,
            "changed_files": list(self.changed_files),
            "tests_run": [
                {"command": command, "exit_code": 0, "summary": "passed"}
                for command in request.verification_commands
            ],
            "browser_smoke_results": [],
            "acceptance_results": {
                criterion: {
                    "status": "passed",
                    "evidence": "Contract backend generated contract-compatible evidence.",
                }
                for criterion in request.acceptance_criteria
            },
            "risks": list(self.risks),
            "follow_up_tasks": list(self.follow_up_tasks),
            "artifacts": [request.result_path],
            "handoff_notes": ("Contract backend result is ready for shared ingestion validation."),
        }
        result_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        _write_liveness_probe(request, stage="contract_worker_completed", exit_code=0)
        missing_evidence = _write_evidence_manifest(
            request,
            status="completed",
            launch_decision="contract_worker",
        )
        metadata = {
            "backend": "contract_worker",
            "prompt_length": len(request.prompt),
            "evidence_manifest_path": request.evidence_manifest_path,
        }
        if missing_evidence:
            metadata["missing_evidence_paths"] = list(missing_evidence)
            return WorkerLaunchResult(
                worker_run_id=request.worker_run_id,
                task_id=request.task_id,
                status="failed",
                exit_code=1,
                duration_seconds=0.0,
                prompt_path=request.prompt_path,
                jsonl_path=request.jsonl_path,
                stdout_path=request.stdout_path,
                stderr_path=request.stderr_path,
                final_message_path=request.final_message_path,
                diff_summary_path=request.diff_summary_path,
                failure_class="worker_evidence_missing",
                metadata=metadata,
            )
        return WorkerLaunchResult(
            worker_run_id=request.worker_run_id,
            task_id=request.task_id,
            status="completed",
            result_path=request.result_path,
            exit_code=0,
            duration_seconds=0.0,
            changed_files=self.changed_files,
            prompt_path=request.prompt_path,
            jsonl_path=request.jsonl_path,
            stdout_path=request.stdout_path,
            stderr_path=request.stderr_path,
            final_message_path=request.final_message_path,
            diff_summary_path=request.diff_summary_path,
            metadata=metadata,
        )


def _write_text_artifact(repo_root: Path, relative_path: str, content: str) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_process_output_artifact(
    repo_root: Path,
    relative_path: str,
    *,
    decoded_text: str,
    raw_bytes: bytes,
) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if raw_bytes:
        path.write_bytes(raw_bytes)
        return
    path.write_text(decoded_text, encoding="utf-8")


def _write_process_jsonl_artifact(
    repo_root: Path,
    relative_path: str,
    *,
    decoded_text: str,
    raw_bytes: bytes,
    event_line: str,
    preserve_existing: bool,
) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    event_bytes = event_line.encode("utf-8")
    if preserve_existing and path.exists():
        existing = path.read_bytes()
        separator = b"" if not existing or existing.endswith(b"\n") else b"\n"
        path.write_bytes(existing + separator + event_bytes)
        return
    prefix = raw_bytes if raw_bytes else decoded_text.encode("utf-8")
    if prefix and not prefix.endswith(b"\n"):
        prefix += b"\n"
    path.write_bytes(prefix + event_bytes)


def _load_canonical_worker_result(request: WorkerLaunchRequest) -> WorkerResult | None:
    result_file = request.repo_root / request.final_message_path
    if not result_file.exists():
        return None
    try:
        return validate_worker_result_file(
            result_file,
            repo_root=request.repo_root,
            changed_files_root=request.worktree_path,
            artifact_root=request.worktree_path,
            result_path=request.final_message_path,
            worker_run_id=request.worker_run_id,
            allowed_paths=request.allowed_paths,
            verification_commands=request.verification_commands,
            acceptance_criteria=request.acceptance_criteria,
        )
    except OSError, WorkerResultError, json.JSONDecodeError:
        return None


def _copy_canonical_worker_result(request: WorkerLaunchRequest) -> None:
    source = request.repo_root / request.final_message_path
    target = request.repo_root / request.result_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def _copy_worker_result_support_artifacts(
    request: WorkerLaunchRequest,
    worker_result: WorkerResult,
) -> None:
    for relative_path in _worker_result_support_artifact_paths(worker_result, request.result_path):
        source = request.worktree_path / relative_path
        target = request.repo_root / relative_path
        if target.exists() or not source.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())


def _worker_result_support_artifact_paths(
    worker_result: WorkerResult,
    result_path: str,
) -> tuple[str, ...]:
    paths: list[str] = list(worker_result.artifacts)
    for item in worker_result.payload.get("browser_smoke_results", []):
        if isinstance(item, dict):
            artifact = item.get("artifact")
            if isinstance(artifact, str) and artifact.strip():
                paths.append(artifact)
    normalized_result_path = result_path.strip().replace("\\", "/")
    return tuple(
        dict.fromkeys(
            path.strip().replace("\\", "/")
            for path in paths
            if path.strip().replace("\\", "/") != normalized_result_path
        )
    )


def _liveness_probe_relative_path(request: WorkerLaunchRequest) -> str:
    run_directory = PurePosixPath(request.jsonl_path.replace("\\", "/")).parent
    return (run_directory / "liveness.json").as_posix()


def _liveness_start_callback(
    request: WorkerLaunchRequest,
    preflight: CodexExecPreflightResult,
    stage: str,
) -> CommandStartCallback:
    def callback(pid: int | None) -> None:
        _write_liveness_probe(request, preflight=preflight, stage=stage, pid=pid)

    return callback


def _write_liveness_probe(
    request: WorkerLaunchRequest,
    *,
    stage: str,
    preflight: CodexExecPreflightResult | None = None,
    pid: int | None = None,
    exit_code: int | None = None,
) -> str:
    payload: JsonObject = {
        "worker_run_id": request.worker_run_id,
        "task_id": request.task_id,
        "backend": (
            CODEX_EXEC_BACKEND if preflight is not None else request.metadata.get("backend")
        ),
        "stage": stage,
        "pid": pid,
        "exit_code": exit_code,
        "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "worktree_path": _repo_relative_or_placeholder(request.worktree_path, request.repo_root),
        "prompt_path": request.prompt_path,
        "jsonl_path": request.jsonl_path,
        "result_path": request.result_path,
    }
    if preflight is not None:
        payload["argv"] = preflight.metadata.get("argv", [])
        payload["resolved_executable"] = preflight.metadata.get("resolved_executable")
        payload["resolution_method"] = preflight.metadata.get("resolution_method")
    relative_path = _liveness_probe_relative_path(request)
    _write_text_artifact(
        request.repo_root,
        relative_path,
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
    )
    return relative_path


def _write_evidence_manifest(
    request: WorkerLaunchRequest,
    *,
    status: str,
    launch_decision: str,
) -> tuple[str, ...]:
    paths = {
        "prompt": request.prompt_path,
        "liveness_probe": _liveness_probe_relative_path(request),
        "jsonl": request.jsonl_path,
        "stdout": request.stdout_path,
        "stderr": request.stderr_path,
        "final_message": request.final_message_path,
        "diff_summary": request.diff_summary_path,
        "raw_result": request.result_path,
    }
    path_records = {
        name: _evidence_path_record(request.repo_root / relative_path)
        for name, relative_path in paths.items()
    }
    missing = tuple(
        relative_path
        for name, relative_path in paths.items()
        if not bool(path_records[name]["exists"])
    )
    manifest = {
        "worker_run_id": request.worker_run_id,
        "task_id": request.task_id,
        "status": status,
        "launch_decision": launch_decision,
        "raw_evidence_paths": paths,
        "paths": path_records,
    }
    _write_text_artifact(
        request.repo_root,
        request.evidence_manifest_path,
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )
    return missing


def _evidence_path_record(path: Path) -> JsonObject:
    if not path.exists() or not path.is_file():
        return {"exists": False}
    raw_bytes = path.read_bytes()
    return {
        "exists": True,
        "bytes": len(raw_bytes),
        "sha256": sha256(raw_bytes).hexdigest(),
    }


def _jsonl_validation_failure(request: WorkerLaunchRequest) -> JsonObject | None:
    if request.allow_degraded_jsonl:
        return None
    path = request.repo_root / request.jsonl_path
    if not path.exists():
        return {
            "failure_class": "jsonl_missing",
            "path": request.jsonl_path,
            "reason": "Codex JSONL evidence file is missing.",
        }
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return {
            "failure_class": "jsonl_unreadable",
            "path": request.jsonl_path,
            "reason": str(exc),
        }
    parsed_count = 0
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            return {
                "failure_class": "jsonl_malformed",
                "path": request.jsonl_path,
                "line": line_number,
                "reason": exc.msg,
            }
        if not isinstance(parsed, dict):
            return {
                "failure_class": "jsonl_malformed",
                "path": request.jsonl_path,
                "line": line_number,
                "reason": "JSONL event must be an object.",
            }
        parsed_count += 1
    if parsed_count == 0:
        return {
            "failure_class": "jsonl_empty",
            "path": request.jsonl_path,
            "reason": "Codex JSONL evidence file has no events.",
        }
    return None


def _ensure_result_schema_available(request: WorkerLaunchRequest) -> str | None:
    schema_path = request.repo_root / request.result_schema_path
    if schema_path.exists():
        return None
    if not is_ignored_runtime_path(request.result_schema_path):
        return f"schema path is missing or not a runtime artifact: {request.result_schema_path}"
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(
        json.dumps(_worker_result_output_schema(request), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return None


def _worker_result_output_schema(request: WorkerLaunchRequest) -> JsonObject:
    acceptance_result_schema = {
        "type": "object",
        "required": ["status", "evidence"],
        "properties": {
            "status": {"enum": ["passed", "failed", "blocked"]},
            "evidence": {"type": "string"},
        },
        "additionalProperties": False,
    }
    acceptance_results = dict.fromkeys(request.acceptance_criteria, acceptance_result_schema)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": [
            "worker_run_id",
            "status",
            "summary",
            "changed_files",
            "tests_run",
            "acceptance_results",
            "browser_smoke_results",
            "risks",
            "follow_up_tasks",
            "artifacts",
            "completion_notes",
        ],
        "properties": {
            "worker_run_id": {"type": "string"},
            "status": {"enum": ["completed", "blocked", "failed", "needs_review"]},
            "summary": {"type": "string"},
            "changed_files": {"type": "array", "items": {"type": "string"}},
            "tests_run": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["command", "exit_code", "summary"],
                    "properties": {
                        "command": {"type": "string"},
                        "exit_code": {"type": "integer"},
                        "summary": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            "browser_smoke_results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "artifact",
                        "command",
                        "exit_code",
                        "status",
                        "summary",
                        "tool",
                        "url",
                    ],
                    "properties": {
                        "status": {"enum": ["passed", "failed", "blocked"]},
                        "summary": {"type": "string"},
                        "tool": {"type": "string"},
                        "command": {"type": "string"},
                        "exit_code": {"type": "integer"},
                        "artifact": {"type": "string"},
                        "url": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            "acceptance_results": {
                "type": "object",
                "required": list(request.acceptance_criteria),
                "properties": acceptance_results,
                "additionalProperties": False,
            },
            "risks": {"type": "array", "items": {"type": "string"}},
            "follow_up_tasks": {"type": "array", "items": {"type": "string"}},
            "artifacts": {"type": "array", "items": {"type": "string"}},
            "completion_notes": {"type": "string"},
        },
        "additionalProperties": False,
    }


def _run_command(
    command_runner: CommandRunner | None,
    argv: tuple[str, ...],
    cwd: Path,
    environment: dict[str, str],
    *,
    stdin: str | None = None,
    timeout_seconds: float | None = None,
    on_start: CommandStartCallback | None = None,
) -> CommandExecutionResult:
    if command_runner is None:
        return _default_command_runner(
            argv,
            cwd,
            environment,
            stdin=stdin,
            timeout_seconds=timeout_seconds,
            on_start=on_start,
        )
    if on_start is not None:
        on_start(None)
    return command_runner(argv, cwd, environment)


def _default_command_runner(
    argv: tuple[str, ...],
    cwd: Path,
    environment: dict[str, str],
    *,
    stdin: str | None = None,
    timeout_seconds: float | None = None,
    on_start: CommandStartCallback | None = None,
) -> CommandExecutionResult:
    process_environment = _minimal_process_environment(os.environ)
    process_environment.update(environment)
    encoded_stdin = stdin.encode("utf-8") if stdin is not None else None
    creationflags = (
        int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) if os.name == "nt" else 0
    )
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        env=process_environment,
        text=False,
        stdin=subprocess.PIPE if encoded_stdin is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
        start_new_session=os.name != "nt",
    )
    if on_start is not None:
        on_start(process.pid)
    try:
        stdout, stderr = process.communicate(encoded_stdin, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_tree(process)
        stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(
            exc.cmd,
            exc.timeout,
            output=stdout,
            stderr=stderr,
        ) from exc
    except KeyboardInterrupt:
        _terminate_process_tree(process)
        process.wait()
        raise
    return CommandExecutionResult(
        exit_code=process.returncode,
        stdout=_decode_process_output(stdout),
        stderr=_decode_process_output(stderr),
        stdout_bytes=stdout or b"",
        stderr_bytes=stderr or b"",
    )


def _resolve_codex_executable(configured_executable: str | None) -> CodexExecutableResolution:
    if configured_executable:
        if configured_executable.casefold() == "codex":
            return _resolve_path_codex_executable(configured_bare=True)
        if _is_unlaunchable_powershell_shim(configured_executable):
            return _unlaunchable_powershell_shim_resolution(
                configured_executable,
                method="configured_powershell_shim",
            )
        return CodexExecutableResolution(configured_executable, "configured")
    return _resolve_path_codex_executable(configured_bare=False)


def _resolve_path_codex_executable(*, configured_bare: bool) -> CodexExecutableResolution:
    if os.name == "nt":
        powershell_shim: str | None = None
        for candidate in ("codex.cmd", "codex.exe", "codex"):
            resolved = shutil.which(candidate)
            if resolved is None:
                continue
            if _is_unlaunchable_powershell_shim(resolved):
                powershell_shim = resolved
                continue
            method = "configured_path_windows" if configured_bare else "path_windows"
            if candidate.endswith(".cmd"):
                method = f"{method}_cmd"
            elif candidate.endswith(".exe"):
                method = f"{method}_exe"
            return CodexExecutableResolution(resolved, method)
        if powershell_shim is not None:
            return _unlaunchable_powershell_shim_resolution(
                powershell_shim,
                method="configured_path_powershell_shim"
                if configured_bare
                else "path_powershell_shim",
            )
        return CodexExecutableResolution(None, "not_found")
    resolved = shutil.which("codex")
    if resolved is None:
        return CodexExecutableResolution(None, "not_found")
    return CodexExecutableResolution(resolved, "path")


def _is_unlaunchable_powershell_shim(value: str) -> bool:
    return Path(value).suffix.casefold() == ".ps1"


def _unlaunchable_powershell_shim_resolution(
    executable_path: str,
    *,
    method: str,
) -> CodexExecutableResolution:
    return CodexExecutableResolution(
        executable_path=executable_path,
        resolution_method=method,
        failure_class="codex_cli_unavailable",
        stderr=(
            "codex resolved to a PowerShell .ps1 shim, which cannot be launched directly by "
            "the noninteractive worker backend on Windows. Use codex.cmd or codex.exe."
        ),
    )


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ("taskkill", "/PID", str(process.pid), "/T", "/F"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    kill_process_group = getattr(os, "killpg", None)
    if callable(kill_process_group):
        try:
            kill_process_group(process.pid, 15)
            return
        except OSError:
            pass
    process.terminate()


def compose_worker_prompt(request: WorkerLaunchRequest) -> str:
    """Return the prompt sent to Codex Exec over stdin and saved as raw evidence."""

    acceptance = "\n".join(f"- {criterion}" for criterion in request.acceptance_criteria)
    verification = "\n".join(f"- `{command}`" for command in request.verification_commands)
    allowed_paths = "\n".join(f"- `{path}`" for path in request.allowed_paths)
    sections = (
        "# Goal Contract",
        request.rendered_goal_contract.strip() or "No rendered Goal Contract supplied.",
        "# Worker Instructions",
        request.prompt.strip(),
        "# Required Worker Result",
        (
            "Your final assistant message must be only a Worker Result JSON object that "
            f"satisfies the schema at `{request.result_schema_path}`. Codex Exec writes that "
            f"structured final message to `{request.final_message_path}` with "
            "`--output-last-message`; the supervisor treats that file as canonical and copies "
            f"it into `{_worker_visible_result_path(request)}` for planning ingestion."
        ),
        (
            "The JSON must include worker_run_id, status, summary, changed_files, tests_run, "
            "acceptance_results, risks, follow_up_tasks, artifacts, and completion_notes."
        ),
        (
            "Always include browser_smoke_results as an array. Use [] when no browser or UI "
            "smoke was run. When entries are present, include status, summary, tool, command, "
            "exit_code, artifact, and url. Do not put ad hoc browser-smoke commands in tests_run "
            "unless they are listed verification commands in the task contract."
        ),
        (
            "Browser or UI smoke must be bounded: use a harness that starts any API/client "
            "servers as child processes, applies a timeout, captures artifacts, and always "
            "terminates those children. Never leave foreground `npm run dev`, `vite`, "
            "`node server`, or non-detached `docker compose up` commands as worker evidence."
        ),
        "# Acceptance Criteria",
        acceptance or "- none",
        "# Verification Commands",
        verification or "- none",
        "# Allowed Paths",
        allowed_paths or "- none",
    )
    return "\n\n".join(sections).rstrip() + "\n"


def _worker_visible_result_path(request: WorkerLaunchRequest) -> str:
    """Return a path the worker can use from its configured worktree cwd."""

    target = (request.repo_root / request.result_path).resolve(strict=False)
    worktree_path = request.worktree_path.resolve(strict=False)
    try:
        return Path(os.path.relpath(target, worktree_path)).as_posix()
    except ValueError:
        return request.result_path


def _build_codex_exec_argv(
    request: WorkerLaunchRequest,
    executable_path: str,
) -> tuple[str, ...]:
    repo_root = request.repo_root.resolve(strict=False)
    worktree_path = request.worktree_path.resolve(strict=False)
    argv = [
        executable_path,
        "exec",
        "--json",
        "--output-schema",
        str((repo_root / request.result_schema_path).resolve(strict=False)),
        "--output-last-message",
        str((repo_root / request.final_message_path).resolve(strict=False)),
        "--sandbox",
        request.sandbox_mode,
        "--cd",
        str(worktree_path),
    ]
    if request.model is not None:
        argv.extend(("--model", request.model))
    for key, value in _codex_exec_config_overrides(request).items():
        argv.extend(("-c", f"{key}={json.dumps(value)}"))
    if request.ignore_user_config:
        argv.append("--ignore-user-config")
    argv.append("-")
    return tuple(argv)


def _codex_exec_config_overrides(request: WorkerLaunchRequest) -> dict[str, str]:
    overrides: dict[str, str] = {}
    if request.reasoning_effort is not None:
        overrides[CODEX_REASONING_EFFORT_CONFIG_KEY] = request.reasoning_effort
    if request.approval_policy:
        overrides["approval_policy"] = request.approval_policy
    return overrides


def _codex_exec_capability_mappings(request: WorkerLaunchRequest) -> JsonObject:
    return codex_exec_capability_mappings(
        model=request.model,
        reasoning_effort=request.reasoning_effort,
    )


def _probe_codex_launch_capabilities(
    request: WorkerLaunchRequest,
    *,
    executable_path: str,
    environment: dict[str, str],
    command_runner: CommandRunner | None,
    probe_enabled: bool,
) -> CodexCapabilityProbeResult:
    if request.model is None and request.reasoning_effort is None:
        return CodexCapabilityProbeResult(
            request=request,
            failure_class=None,
            stderr="",
            metadata={"status": "skipped", "reason": "no_requested_model_or_reasoning"},
        )
    if not probe_enabled:
        return CodexCapabilityProbeResult(
            request=request,
            failure_class=None,
            stderr="",
            metadata={"status": "skipped", "reason": "launch_disabled"},
        )

    effective_model = request.model
    effective_reasoning_effort = request.reasoning_effort
    attempts: list[JsonObject] = []
    removed_options: list[str] = []
    metadata: JsonObject
    for _ in range(3):
        probe_request = replace(
            request,
            model=effective_model,
            reasoning_effort=effective_reasoning_effort,
        )
        argv = _build_codex_capability_probe_argv(probe_request, executable_path)
        try:
            result = _run_command(
                command_runner,
                argv,
                probe_request.worktree_path,
                environment,
                stdin=_capability_probe_prompt(),
                timeout_seconds=probe_request.preflight_timeout_seconds,
            )
        except KeyboardInterrupt:
            metadata = {
                "status": "failed",
                "failure_class": "codex_capability_probe_interrupted",
                "attempts": attempts,
                "removed_options": removed_options,
            }
            return CodexCapabilityProbeResult(
                request=probe_request,
                failure_class="codex_capability_probe_interrupted",
                stderr="Codex capability probe was interrupted.",
                metadata=metadata,
            )
        except subprocess.TimeoutExpired as exc:
            attempts.append(
                {
                    "argv": _redact_argv(argv, probe_request),
                    "exit_code": 124,
                    "stdout": _truncate_diagnostic(_timeout_text(exc.stdout)),
                    "stderr": f"capability probe timed out after {exc.timeout} seconds",
                }
            )
            metadata = {
                "status": "failed",
                "failure_class": "codex_capability_probe_timeout",
                "attempts": attempts,
                "removed_options": removed_options,
            }
            return CodexCapabilityProbeResult(
                request=probe_request,
                failure_class="codex_capability_probe_timeout",
                stderr=str(attempts[-1]["stderr"]),
                metadata=metadata,
            )
        except OSError as exc:
            attempts.append(
                {
                    "argv": _redact_argv(argv, probe_request),
                    "exit_code": None,
                    "stdout": "",
                    "stderr": _truncate_diagnostic(str(exc)),
                }
            )
            metadata = {
                "status": "failed",
                "failure_class": "codex_capability_probe_failed",
                "attempts": attempts,
                "removed_options": removed_options,
            }
            return CodexCapabilityProbeResult(
                request=probe_request,
                failure_class="codex_capability_probe_failed",
                stderr=str(exc),
                metadata=metadata,
            )

        attempts.append(
            {
                "argv": _redact_argv(argv, probe_request),
                "exit_code": result.exit_code,
                "stdout": _truncate_diagnostic(result.stdout),
                "stderr": _truncate_diagnostic(result.stderr),
            }
        )
        if result.exit_code == 0:
            status = "passed" if not removed_options else "fallback_resolved"
            return CodexCapabilityProbeResult(
                request=probe_request,
                failure_class=None,
                stderr="",
                metadata={
                    "status": status,
                    "requested_model": request.model,
                    "requested_reasoning_effort": request.reasoning_effort,
                    "resolved_model": probe_request.model,
                    "resolved_reasoning_effort": probe_request.reasoning_effort,
                    "removed_options": removed_options,
                    "attempts": attempts,
                },
            )

        removed_this_attempt: list[str] = []
        if effective_model is not None and _looks_like_unsupported_model_failure(result):
            effective_model = None
            removed_this_attempt.append("model")
        if effective_reasoning_effort is not None and _looks_like_unsupported_reasoning_failure(
            result
        ):
            effective_reasoning_effort = None
            removed_this_attempt.append("reasoning_effort")
        if not removed_this_attempt:
            metadata = {
                "status": "failed",
                "failure_class": "codex_capability_probe_failed",
                "requested_model": request.model,
                "requested_reasoning_effort": request.reasoning_effort,
                "resolved_model": effective_model,
                "resolved_reasoning_effort": effective_reasoning_effort,
                "removed_options": removed_options,
                "attempts": attempts,
            }
            return CodexCapabilityProbeResult(
                request=probe_request,
                failure_class="codex_capability_probe_failed",
                stderr=result.stderr or result.stdout,
                metadata=metadata,
            )
        removed_options.extend(removed_this_attempt)

    fallback_request = replace(
        request,
        model=effective_model,
        reasoning_effort=effective_reasoning_effort,
    )
    metadata = {
        "status": "failed",
        "failure_class": "codex_capability_probe_exhausted",
        "requested_model": request.model,
        "requested_reasoning_effort": request.reasoning_effort,
        "resolved_model": effective_model,
        "resolved_reasoning_effort": effective_reasoning_effort,
        "removed_options": removed_options,
        "attempts": attempts,
    }
    return CodexCapabilityProbeResult(
        request=fallback_request,
        failure_class="codex_capability_probe_exhausted",
        stderr="Codex capability probe exhausted fallback attempts.",
        metadata=metadata,
    )


def _build_codex_capability_probe_argv(
    request: WorkerLaunchRequest,
    executable_path: str,
) -> tuple[str, ...]:
    worktree_path = request.worktree_path.resolve(strict=False)
    argv = [
        executable_path,
        "exec",
        "--json",
        "--sandbox",
        "read-only",
        "--cd",
        str(worktree_path),
    ]
    if request.model is not None:
        argv.extend(("--model", request.model))
    for key, value in _codex_exec_config_overrides(request).items():
        argv.extend(("-c", f"{key}={json.dumps(value)}"))
    if request.ignore_user_config:
        argv.append("--ignore-user-config")
    argv.append("-")
    return tuple(argv)


def _capability_probe_prompt() -> str:
    return (
        "Supervisor runtime capability probe. Reply with exactly OK. "
        "Do not inspect or modify files.\n"
    )


def _codex_exec_capability_retry(
    request: WorkerLaunchRequest,
    preflight: CodexExecPreflightResult,
    exec_result: CommandExecutionResult,
    *,
    command_runner: CommandRunner | None,
) -> tuple[WorkerLaunchRequest, CodexExecPreflightResult, JsonObject] | None:
    removed_options: list[str] = []
    model = request.model
    reasoning_effort = request.reasoning_effort
    if model is not None and _looks_like_unsupported_model_failure(exec_result):
        model = None
        removed_options.append("model")
    if reasoning_effort is not None and _looks_like_unsupported_reasoning_failure(exec_result):
        reasoning_effort = None
        removed_options.append("reasoning_effort")
    if not removed_options:
        return None
    retry_request = replace(request, model=model, reasoning_effort=reasoning_effort)
    retry_preflight = CodexExecBackend(
        codex_executable=preflight.executable_path,
        command_runner=command_runner,
        launch_enabled=True,
    ).preflight(retry_request)
    if retry_preflight.failure_class is not None:
        return None
    retry_metadata: JsonObject = {
        "decision": "retry_without_unsupported_cli_options",
        "removed_options": removed_options,
        "first_exit_code": exec_result.exit_code,
        "first_stdout": _truncate_diagnostic(exec_result.stdout),
        "first_stderr": _truncate_diagnostic(exec_result.stderr),
        "first_argv": preflight.metadata.get("argv", []),
        "retry_argv": retry_preflight.metadata.get("argv", []),
    }
    return retry_request, retry_preflight, retry_metadata


def _looks_like_unsupported_model_failure(result: CommandExecutionResult) -> bool:
    text = f"{result.stdout}\n{result.stderr}".casefold()
    return "model" in text and any(
        phrase in text
        for phrase in (
            "not supported",
            "unsupported",
            "unknown model",
            "model_not_found",
            "invalid_request_error",
        )
    )


def _looks_like_unsupported_reasoning_failure(result: CommandExecutionResult) -> bool:
    text = f"{result.stdout}\n{result.stderr}".casefold()
    if "reasoning" not in text and CODEX_REASONING_EFFORT_CONFIG_KEY not in text:
        return False
    return any(
        phrase in text
        for phrase in (
            "not supported",
            "unsupported",
            "unknown",
            "unrecognized",
            "invalid",
            "unexpected argument",
        )
    )


def _truncate_diagnostic(value: str, *, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "...<truncated>"


def _classify_version_exception(executable_path: str, exc: OSError) -> str:
    message = str(exc).lower()
    if isinstance(exc, PermissionError) or _looks_like_windowsapps_access_denied(
        executable_path,
        message,
    ):
        return "codex_cli_unavailable"
    return "codex_version_failed"


def _classify_version_failure(executable_path: str, stderr: str) -> str:
    if _looks_like_windowsapps_access_denied(executable_path, stderr.lower()):
        return "codex_cli_unavailable"
    return "codex_version_failed"


def _looks_like_windowsapps_access_denied(executable_path: str, message: str) -> bool:
    normalized_path = executable_path.replace("\\", "/").lower()
    return "windowsapps" in normalized_path and "access is denied" in message


def _codex_exec_metadata(
    request: WorkerLaunchRequest,
    *,
    executable_path: str | None,
    resolution_method: str,
    version_command: tuple[str, ...],
    version_exit_code: int | None,
    version_stdout: str,
    version_stderr: str,
    failure_class: str | None,
    argv: tuple[str, ...],
    environment: dict[str, str],
) -> JsonObject:
    composed_prompt = compose_worker_prompt(request)
    goal_mode_preflight = _goal_mode_preflight_metadata(request)
    return {
        "backend": CODEX_EXEC_BACKEND,
        "resolved_executable": _redact_executable(executable_path),
        "resolution_method": resolution_method,
        "version_command": _redact_argv(version_command, request),
        "version_exit_code": version_exit_code,
        "version_stdout": version_stdout,
        "version_stderr": version_stderr,
        "failure_class": failure_class,
        "codex_home": _redact_optional_path(request.codex_home, label="codex-home"),
        "codex_config_path": _redact_optional_path(request.codex_config_path, label="codex-config"),
        "sandbox_mode": request.sandbox_mode,
        "approval_policy": request.approval_policy,
        "native_goal_mode": request.native_goal_mode,
        "goal_mode_decision": goal_mode_decision(native_goal_mode=request.native_goal_mode),
        "goal_mode_preflight": goal_mode_preflight,
        "official_noninteractive_native_goal_path": False,
        "ignore_user_config": request.ignore_user_config,
        "model": request.model,
        "reasoning_effort": request.reasoning_effort,
        "capability_mappings": _codex_exec_capability_mappings(request),
        "service_tier": request.service_tier,
        "version_gated_options": _version_gated_options(request),
        "host_platform": platform.platform(),
        "working_directory": _repo_relative_or_placeholder(
            request.worktree_path,
            request.repo_root,
        ),
        "raw_evidence_paths": _raw_evidence_paths(request),
        "argv": _redact_argv(argv, request),
        "prompt_sha256": sha256(composed_prompt.encode("utf-8")).hexdigest(),
        "prompt_length": len(composed_prompt),
        "prompt_transport": "stdin",
        "worker_result_source": "output_last_message",
        "jsonl_required": not request.allow_degraded_jsonl,
        "environment_keys": sorted(environment),
    }


def _raw_evidence_paths(request: WorkerLaunchRequest) -> JsonObject:
    return {
        "prompt": request.prompt_path,
        "liveness_probe": _liveness_probe_relative_path(request),
        "jsonl": request.jsonl_path,
        "stdout": request.stdout_path,
        "stderr": request.stderr_path,
        "final_message": request.final_message_path,
        "diff_summary": request.diff_summary_path,
        "result": request.result_path,
        "evidence_manifest": request.evidence_manifest_path,
    }


def _goal_mode_preflight_metadata(request: WorkerLaunchRequest) -> JsonObject:
    config_path = _effective_codex_config_path(request)
    metadata: JsonObject = {
        "requested": request.native_goal_mode,
        "config_path": _redact_optional_path(
            str(config_path) if config_path is not None else None,
            label="codex-config",
        ),
        "feature_goals": "unknown",
        "feature_source": "config_unavailable",
    }
    if config_path is None:
        return metadata
    try:
        config_bytes = config_path.read_bytes()
    except FileNotFoundError:
        metadata["feature_goals"] = False
        metadata["feature_source"] = "config_missing"
        return metadata
    except OSError as exc:
        metadata["feature_goals"] = "unknown"
        metadata["feature_source"] = f"config_unreadable:{type(exc).__name__}"
        return metadata
    try:
        parsed = tomllib.loads(config_bytes.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        metadata["feature_goals"] = "unknown"
        metadata["feature_source"] = f"config_invalid:{type(exc).__name__}"
        return metadata
    features = parsed.get("features")
    if isinstance(features, dict) and isinstance(features.get("goals"), bool):
        metadata["feature_goals"] = features["goals"]
        metadata["feature_source"] = "config_features_goals"
        return metadata
    metadata["feature_goals"] = False
    metadata["feature_source"] = "config_feature_missing"
    return metadata


def _effective_codex_config_path(request: WorkerLaunchRequest) -> Path | None:
    if request.codex_config_path is not None:
        return Path(request.codex_config_path)
    if request.codex_home is not None:
        return Path(request.codex_home) / "config.toml"
    return None


def _version_gated_options(request: WorkerLaunchRequest) -> list[str]:
    options: list[str] = []
    if request.model is not None:
        options.append("model")
    if request.reasoning_effort is not None:
        options.append("reasoning_effort_config")
    if request.service_tier is not None:
        options.append("service_tier_unsupported")
    if request.codex_config_path is not None:
        options.append("config")
    return options


def _codex_exec_launch_metadata(
    preflight: CodexExecPreflightResult,
    *,
    launch_decision: str,
    exec_exit_code: int | None,
    duration_seconds: float,
) -> JsonObject:
    return {
        **preflight.metadata,
        "launch_decision": launch_decision,
        "exec_exit_code": exec_exit_code,
        "duration_seconds": duration_seconds,
    }


def _write_codex_exec_evidence(
    request: WorkerLaunchRequest,
    *,
    event: str,
    stdout: str,
    stderr: str,
    final_message: str,
    preflight: CodexExecPreflightResult,
    extra_event: JsonObject | None = None,
    process_jsonl: str = "",
    process_jsonl_bytes: bytes = b"",
    preserve_existing_final_message: bool = False,
    write_final_message_if_missing: bool = True,
    preserve_existing_jsonl: bool = False,
    preserve_existing_diff_summary: bool = False,
    stdout_bytes: bytes = b"",
    stderr_bytes: bytes = b"",
) -> None:
    _write_process_output_artifact(
        request.repo_root,
        request.stdout_path,
        decoded_text=stdout,
        raw_bytes=stdout_bytes,
    )
    _write_process_output_artifact(
        request.repo_root,
        request.stderr_path,
        decoded_text=stderr,
        raw_bytes=stderr_bytes,
    )
    final_message_file = request.repo_root / request.final_message_path
    if not preserve_existing_final_message or (
        write_final_message_if_missing and not final_message_file.exists()
    ):
        _write_text_artifact(request.repo_root, request.final_message_path, final_message)
    diff_summary_file = request.repo_root / request.diff_summary_path
    if not preserve_existing_diff_summary or not diff_summary_file.exists():
        _write_text_artifact(request.repo_root, request.diff_summary_path, "")
    event_payload = {
        "event": event,
        "failure_class": preflight.failure_class,
        "argv": preflight.metadata.get("argv", []),
    }
    if extra_event:
        event_payload.update(extra_event)
    event_line = json.dumps(event_payload, sort_keys=True) + "\n"
    _write_process_jsonl_artifact(
        request.repo_root,
        request.jsonl_path,
        decoded_text=process_jsonl,
        raw_bytes=process_jsonl_bytes,
        event_line=event_line,
        preserve_existing=preserve_existing_jsonl,
    )


def build_codex_launch_environment(
    *,
    codex_home: str | None,
    environment: Mapping[str, str] | None,
) -> LaunchEnvironmentResult:
    """Build a Codex subprocess environment with shared CODEX_HOME conflict checks."""

    effective_environment = dict(environment or {})
    if codex_home is not None:
        existing = effective_environment.get("CODEX_HOME")
        if existing is not None and _canonical_launch_path(existing) != _canonical_launch_path(
            codex_home
        ):
            return LaunchEnvironmentResult(
                environment=effective_environment,
                failure_class="codex_home_conflict",
                stderr="codex_home conflicts with environment CODEX_HOME",
            )
        effective_environment["CODEX_HOME"] = codex_home
    return LaunchEnvironmentResult(environment=effective_environment)


def _build_launch_environment(request: WorkerLaunchRequest) -> LaunchEnvironmentResult:
    return build_codex_launch_environment(
        codex_home=request.codex_home,
        environment=request.environment,
    )


def _unsupported_launch_option_failure(request: WorkerLaunchRequest) -> tuple[str, str] | None:
    unsupported: list[str] = []
    if request.service_tier is not None:
        unsupported.append("service_tier")
    if request.native_goal_mode:
        unsupported.append("native_goal_mode")
    if request.codex_config_path is not None:
        if request.codex_home is None:
            unsupported.append("codex_config_path_without_codex_home")
        else:
            expected_config = _codex_home_config_path(request.codex_home)
            if _canonical_launch_path(request.codex_config_path) != _canonical_launch_path(
                expected_config
            ):
                unsupported.append("codex_config_path")
    if unsupported:
        joined = ", ".join(unsupported)
        return "codex_launch_option_unsupported", f"Unsupported Codex launch option(s): {joined}"
    return None


def _codex_home_config_path(codex_home: str) -> str:
    trimmed = codex_home.rstrip("/\\")
    return f"{trimmed}/config.toml"


def _canonical_launch_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    windows_path = PureWindowsPath(normalized)
    if windows_path.drive:
        return windows_path.as_posix().rstrip("/").lower()
    return Path(normalized).expanduser().resolve(strict=False).as_posix().rstrip("/")


def _minimal_process_environment(source: os._Environ[str]) -> dict[str, str]:
    allowed = {
        "APPDATA",
        "COMSPEC",
        "HOME",
        "LANG",
        "LC_ALL",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "PROGRAMDATA",
        "SystemRoot",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "WINDIR",
    }
    normalized_allowed = {key.upper() for key in allowed}
    return {key: value for key, value in source.items() if key.upper() in normalized_allowed}


def _timeout_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return _decode_process_output(value)
    return str(value)


def _decode_process_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace")


def _redact_executable(value: str | None) -> str | None:
    if value is None:
        return None
    return f"<codex-executable:{Path(value).name}>"


def _redact_optional_path(value: str | None, *, label: str) -> str | None:
    if value is None:
        return None
    return f"<{label}>"


def _redact_argv(argv: tuple[str, ...], request: WorkerLaunchRequest) -> list[str]:
    return [_redact_argv_item(item, request) for item in argv]


def _redact_argv_item(item: str, request: WorkerLaunchRequest) -> str:
    if item == request.prompt:
        return "<prompt>"
    windows_path = PureWindowsPath(item)
    if windows_path.is_absolute() or windows_path.drive:
        return f"<local-path:{windows_path.name}>"
    path = Path(item)
    if path.is_absolute():
        return _repo_relative_or_placeholder(path, request.repo_root)
    return item


def _repo_relative_or_placeholder(path: Path, repo_root: Path) -> str:
    try:
        relative = path.resolve(strict=False).relative_to(repo_root.resolve(strict=False))
    except ValueError:
        return f"<local-path:{path.name}>"
    if relative.as_posix() == ".":
        return "<repo-root>"
    return f"<repo-root>/{relative.as_posix()}"
