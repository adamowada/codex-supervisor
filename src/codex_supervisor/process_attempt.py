"""Run a worker process as one durable attempt."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from codex_supervisor.small_interface import AttemptTransitionResult, attempt_transition


@dataclass(frozen=True)
class ProcessAttemptResult:
    """Result for a process attempt and its recorded transition."""

    command: tuple[str, ...]
    workspace: str
    exit_code: int
    assignment_path: str
    stdout_path: str
    stderr_path: str
    transition: AttemptTransitionResult


def run_process_attempt(
    database_path: Path,
    *,
    task_id: str,
    workspace: Path,
    command: tuple[str, ...],
    attempt_id: str | None = None,
    executor: str = "codex",
    timeout_seconds: int = 300,
    summary: str | None = None,
    checks: tuple[str, ...] = (),
    artifacts: tuple[str, ...] = (),
    acceptance_results: dict[str, bool] | None = None,
    risks: tuple[str, ...] = (),
    gaps: tuple[str, ...] = (),
    next_actions: tuple[str, ...] = (),
    review_evidence: tuple[str, ...] = (),
) -> ProcessAttemptResult:
    """Execute a command and record attempt, evidence, and acceptance."""

    if not command:
        raise ValueError("command must include at least one argument")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    run_summary = summary or _command_summary(command)
    running = attempt_transition(
        database_path,
        task_id=task_id,
        attempt_id=attempt_id,
        executor=executor,
        status="running",
        summary=run_summary,
    )
    recorded_attempt_id = str(running.attempt["attempt_id"])

    telemetry_errors: list[str] = []
    evidence_dir = workspace / ".codex-supervisor" / "evidence"
    try:
        evidence_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        telemetry_errors.append(f"could not create workspace evidence directory: {exc}")
        evidence_dir = Path(tempfile.mkdtemp(prefix="codex-supervisor-evidence-"))
    assignment_path = evidence_dir / f"{recorded_attempt_id}-assignment.json"
    stdout_path = evidence_dir / f"{recorded_attempt_id}-stdout.txt"
    stderr_path = evidence_dir / f"{recorded_attempt_id}-stderr.txt"
    command_path = evidence_dir / f"{recorded_attempt_id}-command.json"
    assignment_payload = {
        "task": running.task,
        "attempt": running.attempt,
        "workspace": str(workspace),
    }
    assignment_error = _write_text(
        assignment_path,
        json.dumps(assignment_payload, indent=2, sort_keys=True),
    )
    if assignment_error is not None:
        telemetry_errors.append(f"could not write assignment metadata: {assignment_error}")

    exit_code = 1
    stdout = ""
    stderr = ""
    terminal_status = "failed"
    terminal_summary = run_summary
    env = os.environ.copy()
    env.update(
        {
            "CODEX_SUPERVISOR_TASK_ID": task_id,
            "CODEX_SUPERVISOR_ATTEMPT_ID": recorded_attempt_id,
            "CODEX_SUPERVISOR_TASK_JSON": str(assignment_path),
            "CODEX_SUPERVISOR_WORKSPACE": str(workspace),
        }
    )
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
        terminal_status = "succeeded" if exit_code == 0 else "failed"
        terminal_summary = f"{run_summary} Exit code: {exit_code}."
    except subprocess.TimeoutExpired as exc:
        stdout = _coerce_output(exc.stdout)
        stderr = _coerce_output(exc.stderr)
        terminal_summary = f"{run_summary} Timed out after {timeout_seconds} seconds."
    except OSError as exc:
        stderr = str(exc)
        terminal_summary = f"{run_summary} Could not start worker process: {exc}."
    finally:
        stdout_error = _write_text(stdout_path, stdout)
        stderr_error = _write_text(stderr_path, stderr)
        command_error = _write_text(
            command_path,
            json.dumps(
                {
                    "command": list(command),
                    "workspace": str(workspace),
                    "timeout_seconds": timeout_seconds,
                    "exit_code": exit_code,
                    "assignment_path": str(assignment_path),
                },
                indent=2,
                sort_keys=True,
            ),
        )
        if stdout_error is not None:
            telemetry_errors.append(f"could not write stdout metadata: {stdout_error}")
        if stderr_error is not None:
            telemetry_errors.append(f"could not write stderr metadata: {stderr_error}")
        if command_error is not None:
            telemetry_errors.append(f"could not write command metadata: {command_error}")

    missing_artifacts = _missing_declared_artifacts(artifacts, workspace=workspace)
    if missing_artifacts:
        terminal_summary = (
            f"{terminal_summary} Missing declared artifact(s): "
            f"{', '.join(missing_artifacts)}."
        )
    if telemetry_errors:
        terminal_summary = f"{terminal_summary} Telemetry warning(s): {'; '.join(telemetry_errors)}."

    recorded_artifacts = (
        str(command_path),
        str(assignment_path),
        str(stdout_path),
        str(stderr_path),
        *artifacts,
    )
    recorded_checks = (
        f"process exit code: {exit_code}",
        *(f"missing artifact: {artifact}" for artifact in missing_artifacts),
        *(f"telemetry warning: {error}" for error in telemetry_errors),
        *checks,
    )
    recorded_acceptance_results = _acceptance_results_for_terminal_status(
        acceptance_results,
        terminal_status=terminal_status,
        missing_artifacts=missing_artifacts,
    )
    recorded_gaps = (
        *(f"missing declared artifact: {artifact}" for artifact in missing_artifacts),
        *gaps,
    )
    transition = attempt_transition(
        database_path,
        task_id=task_id,
        attempt_id=recorded_attempt_id,
        executor=executor,
        status=terminal_status,
        summary=terminal_summary,
        checks=recorded_checks,
        artifacts=recorded_artifacts,
        acceptance_results=recorded_acceptance_results,
        risks=risks,
        gaps=recorded_gaps,
        next_actions=next_actions,
        review_evidence=review_evidence,
    )
    return ProcessAttemptResult(
        command=command,
        workspace=str(workspace),
        exit_code=exit_code,
        assignment_path=str(assignment_path),
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        transition=transition,
    )


def _command_summary(command: tuple[str, ...]) -> str:
    return "Run worker process: " + " ".join(command)


def _acceptance_results_for_terminal_status(
    acceptance_results: dict[str, bool] | None,
    *,
    terminal_status: str,
    missing_artifacts: tuple[str, ...] = (),
) -> dict[str, bool] | None:
    if terminal_status == "succeeded" and not missing_artifacts:
        return acceptance_results
    if not acceptance_results:
        return acceptance_results
    return dict.fromkeys(acceptance_results, False)


def _coerce_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _write_text(path: Path, content: str) -> str | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        return str(exc)
    return None


def _missing_declared_artifacts(
    artifacts: tuple[str, ...],
    *,
    workspace: Path,
) -> tuple[str, ...]:
    missing: list[str] = []
    for artifact in artifacts:
        artifact_path = Path(artifact)
        candidate = artifact_path if artifact_path.is_absolute() else workspace / artifact_path
        if not candidate.exists():
            missing.append(artifact)
    return tuple(missing)
