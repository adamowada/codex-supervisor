"""Run a worker process as one durable attempt."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from codex_supervisor.small_interface import AttemptTransitionResult, attempt_transition


@dataclass(frozen=True)
class ProcessAttemptResult:
    """Result for a process attempt and its recorded transition."""

    command: tuple[str, ...]
    workspace: str
    exit_code: int
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

    evidence_dir = workspace / ".codex-supervisor" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = evidence_dir / f"{recorded_attempt_id}-stdout.txt"
    stderr_path = evidence_dir / f"{recorded_attempt_id}-stderr.txt"
    command_path = evidence_dir / f"{recorded_attempt_id}-command.json"

    exit_code = 1
    stdout = ""
    stderr = ""
    terminal_status = "failed"
    terminal_summary = run_summary
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
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
    finally:
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
        command_path.write_text(
            json.dumps(
                {
                    "command": list(command),
                    "workspace": str(workspace),
                    "timeout_seconds": timeout_seconds,
                    "exit_code": exit_code,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    recorded_artifacts = (
        str(command_path),
        str(stdout_path),
        str(stderr_path),
        *artifacts,
    )
    recorded_checks = (
        f"process exit code: {exit_code}",
        *checks,
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
        acceptance_results=acceptance_results,
        risks=risks,
        gaps=gaps,
        next_actions=next_actions,
        review_evidence=review_evidence,
    )
    return ProcessAttemptResult(
        command=command,
        workspace=str(workspace),
        exit_code=exit_code,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        transition=transition,
    )


def _command_summary(command: tuple[str, ...]) -> str:
    return "Run worker process: " + " ".join(command)


def _coerce_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
