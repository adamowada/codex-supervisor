"""Run a worker process as one durable attempt."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from codex_supervisor.small_interface import AttemptTransitionResult, attempt_transition
from codex_supervisor.workspace_hygiene import SUPERVISOR_DIR

_TEXT_CAPTURE = {
    "text": True,
    "encoding": "utf-8",
    "errors": "replace",
}


@dataclass(frozen=True)
class ProcessAttemptResult:
    """Result for a process attempt and its recorded transition."""

    command: tuple[str, ...]
    workspace: str
    exit_code: int
    assignment_path: str
    liveness_path: str
    stdout_path: str
    stderr_path: str
    verifier_command: str | None
    verifier_exit_code: int | None
    verifier_stdout_path: str | None
    verifier_stderr_path: str | None
    transition: AttemptTransitionResult


@dataclass(frozen=True)
class _WorkerProcessResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


def run_process_attempt(
    database_path: Path,
    *,
    task_id: str,
    workspace: Path,
    command: tuple[str, ...],
    verifier_command: str | None = None,
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
    if verifier_command is not None and not verifier_command.strip():
        raise ValueError("verifier_command cannot be blank")
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
    liveness_path = evidence_dir / f"{recorded_attempt_id}-liveness.json"
    stdout_path = evidence_dir / f"{recorded_attempt_id}-stdout.txt"
    stderr_path = evidence_dir / f"{recorded_attempt_id}-stderr.txt"
    command_path = evidence_dir / f"{recorded_attempt_id}-command.json"
    verifier_command_path: Path | None = None
    verifier_stdout_path: Path | None = None
    verifier_stderr_path: Path | None = None
    if verifier_command is not None:
        verifier_command_path = evidence_dir / f"{recorded_attempt_id}-verifier-command.json"
        verifier_stdout_path = evidence_dir / f"{recorded_attempt_id}-verifier-stdout.txt"
        verifier_stderr_path = evidence_dir / f"{recorded_attempt_id}-verifier-stderr.txt"
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
    worker_timed_out = False
    terminal_status = "failed"
    terminal_summary = run_summary
    verifier_exit_code: int | None = None
    verifier_stdout = ""
    verifier_stderr = ""
    verifier_skipped_reason: str | None = None
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.update(
        {
            "CODEX_SUPERVISOR_TASK_ID": task_id,
            "CODEX_SUPERVISOR_ATTEMPT_ID": recorded_attempt_id,
            "CODEX_SUPERVISOR_TASK_JSON": str(assignment_path),
            "CODEX_SUPERVISOR_WORKSPACE": str(workspace),
        }
    )
    try:
        completed = _run_worker_process(
            command,
            workspace=workspace,
            environment=env,
            timeout_seconds=timeout_seconds,
            liveness_path=liveness_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )
        exit_code = completed.exit_code
        worker_timed_out = completed.timed_out
        terminal_status = "succeeded" if exit_code == 0 else "failed"
        if worker_timed_out:
            terminal_summary = f"{run_summary} Timed out after {timeout_seconds} seconds."
        else:
            terminal_summary = f"{run_summary} Exit code: {exit_code}."
    except OSError as exc:
        terminal_summary = f"{run_summary} Could not start worker process: {exc}."
    finally:
        command_error = _write_text(
            command_path,
            json.dumps(
                {
                    "command": list(command),
                    "workspace": str(workspace),
                    "timeout_seconds": timeout_seconds,
                    "exit_code": exit_code,
                    "timed_out": worker_timed_out,
                    "assignment_path": str(assignment_path),
                    "liveness_path": str(liveness_path),
                },
                indent=2,
                sort_keys=True,
            ),
        )
        if command_error is not None:
            telemetry_errors.append(f"could not write command metadata: {command_error}")

    if verifier_command is not None:
        if exit_code != 0 and not worker_timed_out:
            verifier_skipped_reason = f"worker exit code was {exit_code}"
            terminal_summary = (
                f"{terminal_summary} Verifier skipped because {verifier_skipped_reason}."
            )
        else:
            try:
                verifier = subprocess.run(
                    verifier_command,
                    cwd=workspace,
                    env=env,
                    capture_output=True,
                    timeout=timeout_seconds,
                    check=False,
                    shell=True,
                    **_TEXT_CAPTURE,
                )
                verifier_exit_code = verifier.returncode
                verifier_stdout = _coerce_output(verifier.stdout)
                verifier_stderr = _coerce_output(verifier.stderr)
                if verifier_exit_code != 0:
                    terminal_status = "failed"
                elif worker_timed_out:
                    terminal_status = "succeeded"
                terminal_summary = (
                    f"{terminal_summary} Verifier exit code: {verifier_exit_code}."
                )
            except subprocess.TimeoutExpired as exc:
                verifier_exit_code = 1
                verifier_stdout = _coerce_output(exc.stdout)
                verifier_stderr = _coerce_output(exc.stderr)
                terminal_status = "failed"
                terminal_summary = (
                    f"{terminal_summary} Verifier timed out after {timeout_seconds} seconds."
                )
            except OSError as exc:
                verifier_exit_code = 1
                verifier_stderr = str(exc)
                terminal_status = "failed"
                terminal_summary = f"{terminal_summary} Could not start verifier: {exc}."

        if verifier_stdout_path is not None:
            verifier_stdout_error = _write_text(verifier_stdout_path, verifier_stdout)
            if verifier_stdout_error is not None:
                telemetry_errors.append(
                    f"could not write verifier stdout metadata: {verifier_stdout_error}"
                )
        if verifier_stderr_path is not None:
            verifier_stderr_error = _write_text(verifier_stderr_path, verifier_stderr)
            if verifier_stderr_error is not None:
                telemetry_errors.append(
                    f"could not write verifier stderr metadata: {verifier_stderr_error}"
                )
        if verifier_command_path is not None:
            verifier_command_error = _write_text(
                verifier_command_path,
                json.dumps(
                    {
                        "command": verifier_command,
                        "workspace": str(workspace),
                        "timeout_seconds": timeout_seconds,
                        "exit_code": verifier_exit_code,
                        "skipped_reason": verifier_skipped_reason,
                    },
                    indent=2,
                    sort_keys=True,
                ),
            )
            if verifier_command_error is not None:
                telemetry_errors.append(
                    f"could not write verifier command metadata: {verifier_command_error}"
                )

    missing_artifacts = _missing_declared_artifacts(artifacts, workspace=workspace)
    if missing_artifacts:
        terminal_summary = (
            f"{terminal_summary} Missing declared artifact(s): "
            f"{', '.join(missing_artifacts)}."
        )
    if telemetry_errors:
        telemetry_summary = "; ".join(telemetry_errors)
        terminal_summary = f"{terminal_summary} Telemetry warning(s): {telemetry_summary}."

    git_product_artifacts = _changed_product_paths(workspace)
    recorded_artifacts = _unique_strings(
        (
            str(command_path),
            str(assignment_path),
            str(liveness_path),
            str(stdout_path),
            str(stderr_path),
            *(
                str(path)
                for path in (verifier_command_path, verifier_stdout_path, verifier_stderr_path)
                if path is not None
            ),
            *artifacts,
            *git_product_artifacts,
        )
    )
    recorded_checks = (
        f"process exit code: {exit_code}",
        *(
            (f"verifier exit code: {verifier_exit_code}",)
            if verifier_exit_code is not None
            else ()
        ),
        *(
            (f"verifier skipped: {verifier_skipped_reason}",)
            if verifier_skipped_reason is not None
            else ()
        ),
        *(f"git changed product path: {artifact}" for artifact in git_product_artifacts),
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
    verifier_stdout_path_string = (
        str(verifier_stdout_path) if verifier_stdout_path is not None else None
    )
    verifier_stderr_path_string = (
        str(verifier_stderr_path) if verifier_stderr_path is not None else None
    )
    return ProcessAttemptResult(
        command=command,
        workspace=str(workspace),
        exit_code=exit_code,
        assignment_path=str(assignment_path),
        liveness_path=str(liveness_path),
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        verifier_command=verifier_command,
        verifier_exit_code=verifier_exit_code,
        verifier_stdout_path=verifier_stdout_path_string,
        verifier_stderr_path=verifier_stderr_path_string,
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


def _run_worker_process(
    command: tuple[str, ...],
    *,
    workspace: Path,
    environment: dict[str, str],
    timeout_seconds: int,
    liveness_path: Path,
    stdout_path: Path,
    stderr_path: Path,
) -> _WorkerProcessResult:
    _write_text(stdout_path, "")
    _write_text(stderr_path, "")
    liveness = _LivenessRecorder(liveness_path)
    creationflags = (
        int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) if os.name == "nt" else 0
    )
    try:
        process = subprocess.Popen(
            command,
            cwd=workspace,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
    except OSError:
        liveness.finish(state="start_failed", exit_code=1)
        raise
    liveness.start(process.pid)
    stdout_parts: list[bytes] = []
    stderr_parts: list[bytes] = []
    stdout_thread = threading.Thread(
        target=_collect_process_pipe,
        args=(process.stdout, stdout_path, stdout_parts, liveness),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_collect_process_pipe,
        args=(process.stderr, stderr_path, stderr_parts, liveness),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_tree(process)
        process.wait()
    stdout_thread.join(timeout=5)
    stderr_thread.join(timeout=5)
    exit_code = 124 if timed_out else int(process.returncode or 0)
    liveness.finish(
        state="timed_out" if timed_out else ("succeeded" if exit_code == 0 else "failed"),
        exit_code=exit_code,
    )
    return _WorkerProcessResult(
        exit_code=exit_code,
        stdout=_coerce_output(b"".join(stdout_parts)),
        stderr=_coerce_output(b"".join(stderr_parts)),
        timed_out=timed_out,
    )


def _collect_process_pipe(
    pipe: object,
    output_path: Path,
    output_parts: list[bytes],
    liveness: _LivenessRecorder,
) -> None:
    if pipe is None:
        return
    try:
        while True:
            chunk = pipe.readline()  # type: ignore[attr-defined]
            if not chunk:
                break
            output_parts.append(chunk)
            _append_output(output_path, chunk)
            liveness.mark_output()
    finally:
        pipe.close()  # type: ignore[attr-defined]


def _append_output(path: Path, chunk: bytes) -> None:
    text = chunk.decode("utf-8", errors="replace")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)


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


class _LivenessRecorder:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.started_at = _utc_now()
        self.last_output_at: str | None = None
        self.ended_at: str | None = None
        self.state = "starting"
        self.pid: int | None = None
        self.exit_code: int | None = None
        self._lock = threading.Lock()
        self._write()

    def start(self, pid: int | None) -> None:
        with self._lock:
            self.pid = pid
            self.state = "running"
            self._write()

    def mark_output(self) -> None:
        with self._lock:
            self.last_output_at = _utc_now()
            self._write()

    def finish(self, *, state: str, exit_code: int) -> None:
        with self._lock:
            self.state = state
            self.exit_code = exit_code
            self.ended_at = _utc_now()
            self._write()

    def _write(self) -> None:
        payload = {
            "started_at": self.started_at,
            "last_output_at": self.last_output_at,
            "ended_at": self.ended_at,
            "state": self.state,
            "pid": self.pid,
            "exit_code": self.exit_code,
        }
        _write_text(self.path, json.dumps(payload, indent=2, sort_keys=True))


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


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


def _changed_product_paths(workspace: Path) -> tuple[str, ...]:
    try:
        completed = subprocess.run(
            (
                "git",
                "-C",
                str(workspace),
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
            ),
            check=False,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError:
        return ()
    if completed.returncode != 0:
        return ()

    paths: list[str] = []
    entries = [entry for entry in completed.stdout.split("\0") if entry]
    index = 0
    while index < len(entries):
        entry = entries[index]
        status = entry[:2]
        raw_path = entry[3:] if len(entry) > 3 else ""
        if "R" in status or "C" in status:
            index += 1
            if index < len(entries):
                raw_path = entries[index]
        index += 1
        normalized = _normalize_relative_path(raw_path)
        if _is_product_path(normalized):
            paths.append(normalized)
    return tuple(sorted(set(paths)))


def _is_product_path(relative_path: str) -> bool:
    return bool(relative_path) and relative_path != ".gitignore" and not (
        relative_path == SUPERVISOR_DIR or relative_path.startswith(f"{SUPERVISOR_DIR}/")
    )


def _normalize_relative_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _unique_strings(items: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return tuple(unique)
