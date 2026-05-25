"""Worker backend protocol and deterministic contract backend implementation."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path, PureWindowsPath
from typing import Any

from codex_supervisor.worker_results import WorkerResultError, validate_worker_result_file
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
        environment_result = _build_launch_environment(request)
        option_failure = _unsupported_launch_option_failure(request)
        argv = _build_codex_exec_argv(request, executable_path) if executable_path else ()
        version_command = (executable_path, "--version") if executable_path else ()
        version_exit_code: int | None = None
        version_stdout = ""
        version_stderr = ""
        failure_class = None
        if executable_path is None:
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
            environment=environment_result.environment,
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
        except subprocess.TimeoutExpired as exc:
            duration_seconds = time.perf_counter() - started_at
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
                process_jsonl=exec_result.stdout,
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
                process_jsonl=exec_result.stdout,
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
        try:
            validate_worker_result_file(
                result_file,
                repo_root=request.repo_root,
                result_path=request.result_path,
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
                    "result_path": request.result_path,
                },
                process_jsonl=exec_result.stdout,
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
                failure_class="worker_result_invalid",
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
            process_jsonl=exec_result.stdout,
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
            metadata={"backend": "contract_worker", "prompt_length": len(request.prompt)},
        )


def _write_text_artifact(repo_root: Path, relative_path: str, content: str) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _ensure_result_schema_available(request: WorkerLaunchRequest) -> str | None:
    schema_path = request.repo_root / request.result_schema_path
    if schema_path.exists():
        return None
    if not is_ignored_runtime_path(request.result_schema_path):
        return f"schema path is missing or not a runtime artifact: {request.result_schema_path}"
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(
        json.dumps(_worker_result_output_schema(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return None


def _worker_result_output_schema() -> JsonObject:
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
            "risks",
            "follow_up_tasks",
            "artifacts",
        ],
        "properties": {
            "worker_run_id": {"type": "string", "minLength": 1},
            "worker_run_ids": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "minItems": 1,
            },
            "status": {"enum": ["completed", "blocked", "failed", "needs_review"]},
            "summary": {"type": "string", "minLength": 1},
            "changed_files": {"type": "array", "items": {"type": "string"}},
            "tests_run": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["command", "exit_code", "summary"],
                    "properties": {
                        "command": {"type": "string", "minLength": 1},
                        "exit_code": {"type": "integer"},
                        "summary": {"type": "string", "minLength": 1},
                    },
                    "additionalProperties": True,
                },
            },
            "acceptance_results": {"type": "object"},
            "risks": {"type": "array", "items": {"type": "string"}},
            "follow_up_tasks": {"type": "array", "items": {"type": "string"}},
            "artifacts": {"type": "array", "items": {"type": "string"}},
            "completion_notes": {"type": "string"},
            "handoff_notes": {"type": "string"},
        },
        "additionalProperties": True,
    }


def _run_command(
    command_runner: CommandRunner | None,
    argv: tuple[str, ...],
    cwd: Path,
    environment: dict[str, str],
    *,
    stdin: str | None = None,
    timeout_seconds: float | None = None,
) -> CommandExecutionResult:
    if command_runner is None:
        return _default_command_runner(
            argv,
            cwd,
            environment,
            stdin=stdin,
            timeout_seconds=timeout_seconds,
        )
    return command_runner(argv, cwd, environment)


def _default_command_runner(
    argv: tuple[str, ...],
    cwd: Path,
    environment: dict[str, str],
    *,
    stdin: str | None = None,
    timeout_seconds: float | None = None,
) -> CommandExecutionResult:
    process_environment = _minimal_process_environment(os.environ)
    process_environment.update(environment)
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=process_environment,
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


def _resolve_codex_executable(configured_executable: str | None) -> tuple[str | None, str]:
    if configured_executable:
        return configured_executable, "configured"
    resolved = shutil.which("codex")
    if resolved is None:
        return None, "not_found"
    return resolved, "path"


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
            "Before finishing, write a Worker Result JSON file that satisfies the schema at "
            f"`{request.result_schema_path}` to `{_worker_visible_result_path(request)}`. "
            f"The supervisor imports that file as `{request.result_path}`."
        ),
        (
            "The JSON must include worker_run_id, status, summary, changed_files, tests_run, "
            "acceptance_results, risks, follow_up_tasks, artifacts, and completion_notes."
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

    target = request.repo_root / request.result_path
    try:
        return Path(os.path.relpath(target, request.worktree_path)).as_posix()
    except ValueError:
        return request.result_path


def _build_codex_exec_argv(
    request: WorkerLaunchRequest,
    executable_path: str,
) -> tuple[str, ...]:
    argv = [
        executable_path,
        "exec",
        "--json",
        "--output-schema",
        str(request.repo_root / request.result_schema_path),
        "--output-last-message",
        str(request.repo_root / request.final_message_path),
        "--sandbox",
        request.sandbox_mode,
        "--cd",
        str(request.worktree_path),
    ]
    if request.model is not None:
        argv.extend(("--model", request.model))
    if request.approval_policy:
        argv.extend(("-c", f"approval_policy={json.dumps(request.approval_policy)}"))
    if request.ignore_user_config:
        argv.append("--ignore-user-config")
    argv.append("-")
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
    environment: dict[str, str],
) -> JsonObject:
    composed_prompt = compose_worker_prompt(request)
    return {
        "backend": "codex_exec",
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
        "goal_mode_decision": (
            "native_goal_requested" if request.native_goal_mode else "prompt_rendered_fallback"
        ),
        "ignore_user_config": request.ignore_user_config,
        "model": request.model,
        "reasoning_effort": request.reasoning_effort,
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
        "environment_keys": sorted(environment),
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
        options.append("reasoning_effort_unsupported")
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
        "argv": preflight.metadata.get("argv", []),
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
        prefix = process_jsonl
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        _write_text_artifact(request.repo_root, request.jsonl_path, prefix + event_line)


def _build_launch_environment(request: WorkerLaunchRequest) -> LaunchEnvironmentResult:
    environment = dict(request.environment)
    if request.codex_home is not None:
        existing = environment.get("CODEX_HOME")
        if existing is not None and Path(existing) != Path(request.codex_home):
            return LaunchEnvironmentResult(
                environment=environment,
                failure_class="codex_home_conflict",
                stderr="codex_home conflicts with environment CODEX_HOME",
            )
        environment["CODEX_HOME"] = request.codex_home
    return LaunchEnvironmentResult(environment=environment)


def _unsupported_launch_option_failure(request: WorkerLaunchRequest) -> tuple[str, str] | None:
    unsupported: list[str] = []
    if request.reasoning_effort is not None:
        unsupported.append("reasoning_effort")
    if request.service_tier is not None:
        unsupported.append("service_tier")
    if request.native_goal_mode:
        unsupported.append("native_goal_mode")
    if request.codex_config_path is not None and request.codex_home is not None:
        expected_config = Path(request.codex_home) / "config.toml"
        if Path(request.codex_config_path) != expected_config:
            unsupported.append("codex_config_path")
    if unsupported:
        joined = ", ".join(unsupported)
        return "codex_launch_option_unsupported", f"Unsupported Codex launch option(s): {joined}"
    return None


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
    return {key: value for key, value in source.items() if key in allowed}


def _timeout_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


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
