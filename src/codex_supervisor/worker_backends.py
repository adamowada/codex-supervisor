"""Worker backend protocol and fake backend implementation."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    environment: dict[str, str] = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)


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


type CommandRunner = Callable[[tuple[str, ...], Path, dict[str, str]], CommandExecutionResult]


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

        executable_path, resolution_method = _resolve_codex_executable(self.codex_executable)
        argv = _build_codex_exec_argv(request, executable_path) if executable_path else ()
        version_command = (executable_path, "--version") if executable_path else ()
        version_exit_code: int | None = None
        version_stdout = ""
        version_stderr = ""
        failure_class = None
        if executable_path is None:
            failure_class = "codex_cli_unavailable"
            version_stderr = "codex executable was not found on PATH"
        else:
            try:
                command_runner = self.command_runner or _default_command_runner
                version_result = command_runner(
                    version_command,
                    request.worktree_path,
                    request.environment,
                )
            except OSError as exc:
                failure_class = _classify_version_exception(executable_path, exc)
                version_stderr = str(exc)
            else:
                version_exit_code = version_result.exit_code
                version_stdout = version_result.stdout
                version_stderr = version_result.stderr
                if version_result.exit_code != 0:
                    failure_class = _classify_version_failure(
                        executable_path,
                        version_result.stderr,
                    )
        metadata = _codex_exec_metadata(
            request,
            executable_path=executable_path,
            resolution_method=resolution_method,
            version_command=version_command,
            version_exit_code=version_exit_code,
            version_stdout=version_stdout,
            version_stderr=version_stderr,
            failure_class=failure_class,
            argv=argv,
        )
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

        _write_text_artifact(request.repo_root, request.prompt_path, request.prompt)
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
        command_runner = self.command_runner or _default_command_runner
        started_at = time.perf_counter()
        try:
            exec_result = command_runner(
                preflight.argv,
                request.worktree_path,
                request.environment,
            )
        except OSError as exc:
            duration_seconds = time.perf_counter() - started_at
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
        duration_seconds = time.perf_counter() - started_at
        if exec_result.exit_code != 0:
            metadata = _codex_exec_launch_metadata(
                preflight,
                launch_decision="exec_failed",
                exec_exit_code=exec_result.exit_code,
                duration_seconds=duration_seconds,
            )
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
                preserve_existing_jsonl=True,
                preserve_existing_diff_summary=True,
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
                failure_class="codex_exec_failed",
                metadata=metadata,
            )
        result_file = request.repo_root / request.result_path
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
                final_message="Codex Exec completed without a Worker Result JSON artifact.\n",
                preflight=preflight,
                extra_event={
                    "exec_exit_code": exec_result.exit_code,
                    "failure_class": "worker_result_missing",
                    "result_path": request.result_path,
                },
                preserve_existing_jsonl=True,
                preserve_existing_diff_summary=True,
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
            final_message="Codex Exec completed and produced a Worker Result JSON artifact.\n",
            preflight=preflight,
            extra_event={
                "exec_exit_code": exec_result.exit_code,
                "result_path": request.result_path,
            },
            preserve_existing_final_message=True,
            preserve_existing_jsonl=True,
            preserve_existing_diff_summary=True,
        )
        return WorkerLaunchResult(
            worker_run_id=request.worker_run_id,
            task_id=request.task_id,
            status="completed",
            result_path=request.result_path,
            exit_code=exec_result.exit_code,
            duration_seconds=duration_seconds,
            prompt_path=request.prompt_path,
            jsonl_path=request.jsonl_path,
            stdout_path=request.stdout_path,
            stderr_path=request.stderr_path,
            final_message_path=request.final_message_path,
            diff_summary_path=request.diff_summary_path,
            metadata=metadata,
        )


@dataclass(frozen=True)
class FakeWorkerBackend:
    """Non-live backend used to prove the worker result ingestion contract."""

    changed_files: tuple[str, ...]
    summary: str = "Fake worker completed the requested slice."
    risks: tuple[str, ...] = ("Fake backend does not launch live Codex.",)
    follow_up_tasks: tuple[str, ...] = ()
    failure_class: str | None = None

    def run(self, request: WorkerLaunchRequest) -> WorkerLaunchResult:
        """Emit deterministic worker evidence without launching Codex."""

        _write_text_artifact(request.repo_root, request.prompt_path, request.prompt)
        if self.failure_class is not None:
            _write_text_artifact(request.repo_root, request.stdout_path, "")
            _write_text_artifact(
                request.repo_root,
                request.stderr_path,
                f"Fake worker failed: {self.failure_class}\n",
            )
            _write_text_artifact(
                request.repo_root,
                request.final_message_path,
                f"Fake worker failed: {self.failure_class}\n",
            )
            _write_text_artifact(request.repo_root, request.diff_summary_path, "")
            _write_text_artifact(
                request.repo_root,
                request.jsonl_path,
                json.dumps(
                    {
                        "event": "fake.failed",
                        "failure_class": self.failure_class,
                    },
                    sort_keys=True,
                )
                + "\n",
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
                failure_class=self.failure_class,
                metadata={"backend": "fake", "prompt_length": len(request.prompt)},
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
        _write_text_artifact(request.repo_root, request.jsonl_path, '{"event":"fake.completed"}\n')
        payload = {
            "worker_run_id": request.worker_run_id,
            "status": "completed",
            "summary": self.summary,
            "changed_files": list(self.changed_files),
            "tests_run": [
                {"command": command, "exit_code": 0, "summary": "passed"}
                for command in request.verification_commands
            ],
            "acceptance_results": {
                criterion: {
                    "status": "passed",
                    "evidence": "Fake backend generated contract-compatible evidence.",
                }
                for criterion in request.acceptance_criteria
            },
            "risks": list(self.risks),
            "follow_up_tasks": list(self.follow_up_tasks),
            "artifacts": [request.result_path],
            "handoff_notes": "Fake backend result is ready for shared ingestion validation.",
        }
        result_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
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
            metadata={"backend": "fake", "prompt_length": len(request.prompt)},
        )


def _write_text_artifact(repo_root: Path, relative_path: str, content: str) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _default_command_runner(
    argv: tuple[str, ...],
    cwd: Path,
    environment: dict[str, str],
) -> CommandExecutionResult:
    process_environment = os.environ.copy()
    process_environment.update(environment)
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=process_environment,
        text=True,
        capture_output=True,
        check=False,
    )
    return CommandExecutionResult(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _resolve_codex_executable(configured_executable: str | None) -> tuple[str | None, str]:
    if configured_executable:
        return configured_executable, "configured"
    resolved = shutil.which("codex")
    if resolved is None:
        return None, "not_found"
    return resolved, "path"


def _build_codex_exec_argv(
    request: WorkerLaunchRequest,
    executable_path: str,
) -> tuple[str, ...]:
    argv = [
        executable_path,
        "exec",
        "--json",
        "--output-schema",
        request.result_schema_path,
        "--output-last-message",
        request.final_message_path,
        "--sandbox",
        request.sandbox_mode,
    ]
    if request.ignore_user_config:
        argv.append("--ignore-user-config")
    argv.append(request.prompt)
    return tuple(argv)


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
) -> JsonObject:
    return {
        "backend": "codex_exec",
        "resolved_executable": executable_path,
        "resolution_method": resolution_method,
        "version_command": list(version_command),
        "version_exit_code": version_exit_code,
        "version_stdout": version_stdout,
        "version_stderr": version_stderr,
        "failure_class": failure_class,
        "codex_home": request.codex_home,
        "codex_config_path": request.codex_config_path,
        "sandbox_mode": request.sandbox_mode,
        "approval_policy": request.approval_policy,
        "native_goal_mode": request.native_goal_mode,
        "goal_mode_decision": (
            "native_goal_requested" if request.native_goal_mode else "prompt_rendered_fallback"
        ),
        "ignore_user_config": request.ignore_user_config,
        "model": request.model,
        "reasoning_effort": request.reasoning_effort,
        "service_tier": request.service_tier,
        "version_gated_options": _version_gated_options(request),
        "host_platform": platform.platform(),
        "working_directory": str(request.worktree_path),
        "raw_evidence_paths": _raw_evidence_paths(request),
        "argv": list(argv),
        "environment_keys": sorted(request.environment),
    }


def _raw_evidence_paths(request: WorkerLaunchRequest) -> JsonObject:
    return {
        "prompt": request.prompt_path,
        "jsonl": request.jsonl_path,
        "stdout": request.stdout_path,
        "stderr": request.stderr_path,
        "final_message": request.final_message_path,
        "diff_summary": request.diff_summary_path,
        "result": request.result_path,
    }


def _version_gated_options(request: WorkerLaunchRequest) -> list[str]:
    options: list[str] = []
    if request.model is not None:
        options.append("model")
    if request.reasoning_effort is not None:
        options.append("reasoning_effort")
    if request.service_tier is not None:
        options.append("service_tier")
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
    preserve_existing_final_message: bool = False,
    preserve_existing_jsonl: bool = False,
    preserve_existing_diff_summary: bool = False,
) -> None:
    _write_text_artifact(request.repo_root, request.stdout_path, stdout)
    _write_text_artifact(request.repo_root, request.stderr_path, stderr)
    final_message_file = request.repo_root / request.final_message_path
    if not preserve_existing_final_message or not final_message_file.exists():
        _write_text_artifact(request.repo_root, request.final_message_path, final_message)
    diff_summary_file = request.repo_root / request.diff_summary_path
    if not preserve_existing_diff_summary or not diff_summary_file.exists():
        _write_text_artifact(request.repo_root, request.diff_summary_path, "")
    event_payload = {
        "event": event,
        "failure_class": preflight.failure_class,
        "argv": list(preflight.argv),
    }
    if extra_event:
        event_payload.update(extra_event)
    event_line = json.dumps(event_payload, sort_keys=True) + "\n"
    jsonl_file = request.repo_root / request.jsonl_path
    if preserve_existing_jsonl and jsonl_file.exists():
        existing_jsonl = jsonl_file.read_text(encoding="utf-8")
        separator = "" if existing_jsonl.endswith("\n") else "\n"
        _write_text_artifact(
            request.repo_root,
            request.jsonl_path,
            existing_jsonl + separator + event_line,
        )
    else:
        _write_text_artifact(request.repo_root, request.jsonl_path, event_line)
