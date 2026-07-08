"""Run a worker process as one durable attempt."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from codex_supervisor.evidence_artifacts import (
    RAW_LOG_RETENTION_BYTES,
    raw_log_truncation_notice,
)
from codex_supervisor.evidence_codec import (
    GIT_CHANGED_PRODUCT_PATH_PREFIX,
    LAUNCH_PACKET_SHA256_CHECK_PREFIX,
    MISSING_ARTIFACT_CHECK_PREFIX,
    PROCESS_EXIT_CHECK_PREFIX,
    TELEMETRY_WARNING_CHECK_PREFIX,
    VERIFIER_EXIT_CHECK_PREFIX,
    VERIFIER_INTENT_SHA256_CHECK_PREFIX,
    VERIFIER_SKIPPED_CHECK_PREFIX,
)
from codex_supervisor.small_interface import AttemptTransitionResult, attempt_transition
from codex_supervisor.target_workspace import (
    artifact_to_workspace_relative,
    changed_product_paths_or_none,
    is_product_path,
    product_artifact_state_checks,
)

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
    command_path: str
    liveness_path: str
    stdout_path: str
    stderr_path: str
    launch_packet_path: str | None
    launch_packet_sha256: str | None
    verifier_intent_path: str | None
    verifier_intent_sha256: str | None
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


@dataclass(frozen=True)
class _EvidencePaths:
    assignment: Path
    command: Path
    liveness: Path
    stdout: Path
    stderr: Path
    verifier_command: Path | None = None
    verifier_stdout: Path | None = None
    verifier_stderr: Path | None = None


@dataclass(frozen=True)
class _CapturedReferences:
    launch_packet: dict[str, str] | None
    verifier_intent: dict[str, str] | None


@dataclass(frozen=True)
class _VerifierOutcome:
    exit_code: int | None
    stdout: str
    stderr: str
    skipped_reason: str | None
    terminal_status: str
    terminal_summary: str


def run_process_attempt(
    database_path: Path,
    *,
    task_id: str,
    workspace: Path,
    command: tuple[str, ...],
    verifier_command: str | None = None,
    launch_packet_path: Path | None = None,
    verifier_intent_path: Path | None = None,
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
    preexisting_product_paths = set(changed_product_paths_or_none(workspace) or ())
    launch_packet_path = _resolve_reference_file(
        launch_packet_path,
        workspace=workspace,
        label="launch_packet",
    )
    verifier_intent_path = _resolve_reference_file(
        verifier_intent_path,
        workspace=workspace,
        label="verifier_intent",
    )
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
    evidence_paths = _evidence_paths(
        evidence_dir,
        attempt_id=recorded_attempt_id,
        include_verifier=verifier_command is not None,
    )
    assignment_path = evidence_paths.assignment
    liveness_path = evidence_paths.liveness
    stdout_path = evidence_paths.stdout
    stderr_path = evidence_paths.stderr
    command_path = evidence_paths.command
    verifier_command_path = evidence_paths.verifier_command
    verifier_stdout_path = evidence_paths.verifier_stdout
    verifier_stderr_path = evidence_paths.verifier_stderr
    try:
        references = _capture_reference_files(
            launch_packet_path=launch_packet_path,
            verifier_intent_path=verifier_intent_path,
            evidence_dir=evidence_dir,
            workspace=workspace,
            attempt_id=recorded_attempt_id,
        )
    except OSError as exc:
        telemetry_error = f"could not prepare attempt telemetry: {exc}"
        transition = _terminalize_setup_failure(
            database_path,
            task_id=task_id,
            attempt_id=recorded_attempt_id,
            executor=executor,
            summary=f"{run_summary} Could not prepare attempt telemetry: {exc}.",
            checks=checks,
            acceptance_results=acceptance_results,
            risks=risks,
            gaps=(telemetry_error, *gaps),
            next_actions=next_actions,
            review_evidence=review_evidence,
            telemetry_error=telemetry_error,
        )
        return ProcessAttemptResult(
            command=command,
            workspace=str(workspace),
            exit_code=1,
            assignment_path=str(assignment_path),
            command_path=str(command_path),
            liveness_path=str(liveness_path),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            launch_packet_path=None,
            launch_packet_sha256=None,
            verifier_intent_path=None,
            verifier_intent_sha256=None,
            verifier_command=verifier_command,
            verifier_exit_code=None,
            verifier_stdout_path=(
                str(verifier_stdout_path) if verifier_stdout_path is not None else None
            ),
            verifier_stderr_path=(
                str(verifier_stderr_path) if verifier_stderr_path is not None else None
            ),
            transition=transition,
        )
    launch_packet = references.launch_packet
    verifier_intent = references.verifier_intent
    assignment_error = _write_assignment_metadata(
        assignment_path,
        task=running.task,
        attempt=running.attempt,
        workspace=workspace,
        references=references,
    )
    if assignment_error is not None:
        telemetry_errors.append(f"could not write assignment metadata: {assignment_error}")

    exit_code = 1
    worker_timed_out = False
    terminal_status = "failed"
    terminal_summary = run_summary
    verifier_exit_code: int | None = None
    verifier_skipped_reason: str | None = None
    env = _worker_environment(
        task_id=task_id,
        attempt_id=recorded_attempt_id,
        assignment_path=assignment_path,
        workspace=workspace,
        references=references,
    )
    command_error = _write_text(
        command_path,
        json.dumps(
            _command_metadata(
                command=command,
                workspace=workspace,
                timeout_seconds=timeout_seconds,
                task_id=task_id,
                attempt_id=recorded_attempt_id,
                executor=executor,
                started_at=str(running.attempt["started_at"]),
                assignment_path=assignment_path,
                liveness_path=liveness_path,
                launch_packet=launch_packet,
                verifier_intent=verifier_intent,
                exit_code=None,
                timed_out=None,
            ),
            indent=2,
            sort_keys=True,
        ),
    )
    if command_error is not None:
        telemetry_errors.append(f"could not write launch command metadata: {command_error}")
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
                _command_metadata(
                    command=command,
                    workspace=workspace,
                    timeout_seconds=timeout_seconds,
                    task_id=task_id,
                    attempt_id=recorded_attempt_id,
                    executor=executor,
                    started_at=str(running.attempt["started_at"]),
                    assignment_path=assignment_path,
                    liveness_path=liveness_path,
                    launch_packet=launch_packet,
                    verifier_intent=verifier_intent,
                    exit_code=exit_code,
                    timed_out=worker_timed_out,
                ),
                indent=2,
                sort_keys=True,
            ),
        )
        if command_error is not None:
            telemetry_errors.append(f"could not write command metadata: {command_error}")

    if verifier_command is not None:
        verifier_outcome = _run_verifier_phase(
            verifier_command,
            workspace=workspace,
            environment=env,
            timeout_seconds=timeout_seconds,
            worker_exit_code=exit_code,
            worker_timed_out=worker_timed_out,
            terminal_status=terminal_status,
            terminal_summary=terminal_summary,
            evidence_paths=evidence_paths,
            telemetry_errors=telemetry_errors,
        )
        verifier_exit_code = verifier_outcome.exit_code
        verifier_skipped_reason = verifier_outcome.skipped_reason
        terminal_status = verifier_outcome.terminal_status
        terminal_summary = verifier_outcome.terminal_summary

    missing_artifacts = _missing_declared_artifacts(artifacts, workspace=workspace)
    if missing_artifacts:
        terminal_summary = (
            f"{terminal_summary} Missing declared artifact(s): "
            f"{', '.join(missing_artifacts)}."
        )
    if telemetry_errors:
        telemetry_summary = "; ".join(telemetry_errors)
        terminal_summary = f"{terminal_summary} Telemetry warning(s): {telemetry_summary}."

    inspected_product_artifacts = changed_product_paths_or_none(workspace)
    git_product_artifacts = tuple(
        path
        for path in (inspected_product_artifacts or ())
        if path not in preexisting_product_paths
    )
    preexisting_product_warnings = tuple(
        sorted(preexisting_product_paths.intersection(inspected_product_artifacts or ()))
    )
    if inspected_product_artifacts is None:
        telemetry_errors.append("could not inspect git product changes after worker")
    attributed_declared_artifacts = _worker_attributed_declared_artifacts(
        artifacts,
        workspace=workspace,
        preexisting_product_paths=preexisting_product_paths,
    )
    worker_product_paths = _worker_attributed_product_paths(
        attributed_declared_artifacts,
        workspace=workspace,
    )
    product_state_paths = _unique_strings((*worker_product_paths, *git_product_artifacts))
    recorded_artifacts = _unique_strings(
        (
            str(command_path),
            str(assignment_path),
            str(liveness_path),
            str(stdout_path),
            str(stderr_path),
            *(
                str(captured["stored_path"])
                for captured in (launch_packet,)
                if captured
            ),
            *(
                str(captured["stored_path"])
                for captured in (verifier_intent,)
                if captured
            ),
            *(
                str(path)
                for path in (verifier_command_path, verifier_stdout_path, verifier_stderr_path)
                if path is not None
            ),
            *attributed_declared_artifacts,
            *git_product_artifacts,
        )
    )
    recorded_checks = (
        f"{PROCESS_EXIT_CHECK_PREFIX}{exit_code}",
        *(
            (f"{VERIFIER_EXIT_CHECK_PREFIX}{verifier_exit_code}",)
            if verifier_exit_code is not None
            else ()
        ),
        *(
            (f"{VERIFIER_SKIPPED_CHECK_PREFIX}{verifier_skipped_reason}",)
            if verifier_skipped_reason is not None
            else ()
        ),
        *(f"{GIT_CHANGED_PRODUCT_PATH_PREFIX}{artifact}" for artifact in git_product_artifacts),
        *product_artifact_state_checks(workspace, product_state_paths),
        *(
            f"preexisting product path not attributed to worker: {artifact}"
            for artifact in preexisting_product_warnings
        ),
        *(f"{MISSING_ARTIFACT_CHECK_PREFIX}{artifact}" for artifact in missing_artifacts),
        *(f"{TELEMETRY_WARNING_CHECK_PREFIX}{error}" for error in telemetry_errors),
        *(
            (f"{LAUNCH_PACKET_SHA256_CHECK_PREFIX}{launch_packet['sha256']}",)
            if launch_packet is not None
            else ()
        ),
        *(
            (f"{VERIFIER_INTENT_SHA256_CHECK_PREFIX}{verifier_intent['sha256']}",)
            if verifier_intent is not None
            else ()
        ),
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
        command_path=str(command_path),
        liveness_path=str(liveness_path),
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        launch_packet_path=(
            str(launch_packet["stored_path"]) if launch_packet is not None else None
        ),
        launch_packet_sha256=(
            str(launch_packet["sha256"]) if launch_packet is not None else None
        ),
        verifier_intent_path=(
            str(verifier_intent["stored_path"]) if verifier_intent is not None else None
        ),
        verifier_intent_sha256=(
            str(verifier_intent["sha256"]) if verifier_intent is not None else None
        ),
        verifier_command=verifier_command,
        verifier_exit_code=verifier_exit_code,
        verifier_stdout_path=verifier_stdout_path_string,
        verifier_stderr_path=verifier_stderr_path_string,
        transition=transition,
    )


def _command_summary(command: tuple[str, ...]) -> str:
    return "Run worker process: " + " ".join(command)


def _terminalize_setup_failure(
    database_path: Path,
    *,
    task_id: str,
    attempt_id: str,
    executor: str,
    summary: str,
    checks: tuple[str, ...],
    acceptance_results: dict[str, bool] | None,
    risks: tuple[str, ...],
    gaps: tuple[str, ...],
    next_actions: tuple[str, ...],
    review_evidence: tuple[str, ...],
    telemetry_error: str,
) -> AttemptTransitionResult:
    return attempt_transition(
        database_path,
        task_id=task_id,
        attempt_id=attempt_id,
        executor=executor,
        status="failed",
        summary=summary,
        checks=(
            f"{PROCESS_EXIT_CHECK_PREFIX}1",
            f"{TELEMETRY_WARNING_CHECK_PREFIX}{telemetry_error}",
            *checks,
        ),
        artifacts=(),
        acceptance_results=_acceptance_results_for_terminal_status(
            acceptance_results,
            terminal_status="failed",
        ),
        risks=risks,
        gaps=gaps,
        next_actions=next_actions,
        review_evidence=review_evidence,
    )


def _evidence_paths(
    evidence_dir: Path,
    *,
    attempt_id: str,
    include_verifier: bool,
) -> _EvidencePaths:
    verifier_command_path: Path | None = None
    verifier_stdout_path: Path | None = None
    verifier_stderr_path: Path | None = None
    if include_verifier:
        verifier_command_path = evidence_dir / f"{attempt_id}-verifier-command.json"
        verifier_stdout_path = evidence_dir / f"{attempt_id}-verifier-stdout.txt"
        verifier_stderr_path = evidence_dir / f"{attempt_id}-verifier-stderr.txt"
    return _EvidencePaths(
        assignment=evidence_dir / f"{attempt_id}-assignment.json",
        command=evidence_dir / f"{attempt_id}-command.json",
        liveness=evidence_dir / f"{attempt_id}-liveness.json",
        stdout=evidence_dir / f"{attempt_id}-stdout.txt",
        stderr=evidence_dir / f"{attempt_id}-stderr.txt",
        verifier_command=verifier_command_path,
        verifier_stdout=verifier_stdout_path,
        verifier_stderr=verifier_stderr_path,
    )


def _capture_reference_files(
    *,
    launch_packet_path: Path | None,
    verifier_intent_path: Path | None,
    evidence_dir: Path,
    workspace: Path,
    attempt_id: str,
) -> _CapturedReferences:
    return _CapturedReferences(
        launch_packet=_capture_reference_file(
            launch_packet_path,
            workspace=workspace,
            destination=evidence_dir / f"{attempt_id}-launch-packet.txt",
            label="launch_packet",
        ),
        verifier_intent=_capture_reference_file(
            verifier_intent_path,
            workspace=workspace,
            destination=evidence_dir / f"{attempt_id}-verifier-intent.txt",
            label="verifier_intent",
        ),
    )


def _write_assignment_metadata(
    path: Path,
    *,
    task: dict[str, object],
    attempt: dict[str, object],
    workspace: Path,
    references: _CapturedReferences,
) -> str | None:
    payload = {
        "recorded_by": "codex-supervisor.attempt-run",
        "task": task,
        "attempt": attempt,
        "workspace": str(workspace),
        "launch_packet": references.launch_packet,
        "verifier_intent": references.verifier_intent,
    }
    return _write_text(path, json.dumps(payload, indent=2, sort_keys=True))


def _worker_environment(
    *,
    task_id: str,
    attempt_id: str,
    assignment_path: Path,
    workspace: Path,
    references: _CapturedReferences,
) -> dict[str, str]:
    environment = os.environ.copy()
    environment.setdefault("PYTHONUTF8", "1")
    environment.setdefault("PYTHONIOENCODING", "utf-8")
    environment.update(
        {
            "CODEX_SUPERVISOR_TASK_ID": task_id,
            "CODEX_SUPERVISOR_ATTEMPT_ID": attempt_id,
            "CODEX_SUPERVISOR_TASK_JSON": str(assignment_path),
            "CODEX_SUPERVISOR_WORKSPACE": str(workspace),
        }
    )
    if references.launch_packet is not None:
        environment.update(
            {
                "CODEX_SUPERVISOR_LAUNCH_PACKET": str(
                    references.launch_packet["stored_path"]
                ),
                "CODEX_SUPERVISOR_LAUNCH_PACKET_SHA256": str(
                    references.launch_packet["sha256"]
                ),
            }
        )
    if references.verifier_intent is not None:
        environment.update(
            {
                "CODEX_SUPERVISOR_VERIFIER_INTENT": str(
                    references.verifier_intent["stored_path"]
                ),
                "CODEX_SUPERVISOR_VERIFIER_INTENT_SHA256": str(
                    references.verifier_intent["sha256"]
                ),
            }
        )
    return environment


def _run_verifier_phase(
    verifier_command: str,
    *,
    workspace: Path,
    environment: dict[str, str],
    timeout_seconds: int,
    worker_exit_code: int,
    worker_timed_out: bool,
    terminal_status: str,
    terminal_summary: str,
    evidence_paths: _EvidencePaths,
    telemetry_errors: list[str],
) -> _VerifierOutcome:
    verifier_exit_code: int | None = None
    verifier_stdout = ""
    verifier_stderr = ""
    verifier_skipped_reason: str | None = None
    next_terminal_status = terminal_status
    next_terminal_summary = terminal_summary

    if worker_exit_code != 0 and not worker_timed_out:
        verifier_skipped_reason = f"worker exit code was {worker_exit_code}"
        next_terminal_summary = (
            f"{next_terminal_summary} Verifier skipped because "
            f"{verifier_skipped_reason}."
        )
    else:
        try:
            verifier = _run_verifier_command(
                verifier_command,
                workspace=workspace,
                environment=environment,
                timeout_seconds=timeout_seconds,
            )
            verifier_exit_code = verifier.returncode
            verifier_stdout = _coerce_output(verifier.stdout)
            verifier_stderr = _coerce_output(verifier.stderr)
            if verifier_exit_code != 0:
                next_terminal_status = "failed"
            elif worker_timed_out:
                next_terminal_status = "succeeded"
            next_terminal_summary = (
                f"{next_terminal_summary} Verifier exit code: {verifier_exit_code}."
            )
        except subprocess.TimeoutExpired as exc:
            verifier_exit_code = 1
            verifier_stdout = _coerce_output(exc.stdout)
            verifier_stderr = _coerce_output(exc.stderr)
            next_terminal_status = "failed"
            next_terminal_summary = (
                f"{next_terminal_summary} Verifier timed out after "
                f"{timeout_seconds} seconds."
            )
        except OSError as exc:
            verifier_exit_code = 1
            verifier_stderr = str(exc)
            next_terminal_status = "failed"
            next_terminal_summary = f"{next_terminal_summary} Could not start verifier: {exc}."

    _record_verifier_outputs(
        verifier_command,
        workspace=workspace,
        timeout_seconds=timeout_seconds,
        evidence_paths=evidence_paths,
        exit_code=verifier_exit_code,
        skipped_reason=verifier_skipped_reason,
        stdout=verifier_stdout,
        stderr=verifier_stderr,
        telemetry_errors=telemetry_errors,
    )
    return _VerifierOutcome(
        exit_code=verifier_exit_code,
        stdout=verifier_stdout,
        stderr=verifier_stderr,
        skipped_reason=verifier_skipped_reason,
        terminal_status=next_terminal_status,
        terminal_summary=next_terminal_summary,
    )


def _record_verifier_outputs(
    verifier_command: str,
    *,
    workspace: Path,
    timeout_seconds: int,
    evidence_paths: _EvidencePaths,
    exit_code: int | None,
    skipped_reason: str | None,
    stdout: str,
    stderr: str,
    telemetry_errors: list[str],
) -> None:
    if evidence_paths.verifier_stdout is not None:
        verifier_stdout_error = _write_retained_text_output(
            evidence_paths.verifier_stdout,
            stdout,
        )
        if verifier_stdout_error is not None:
            telemetry_errors.append(
                f"could not write verifier stdout metadata: {verifier_stdout_error}"
            )
    if evidence_paths.verifier_stderr is not None:
        verifier_stderr_error = _write_retained_text_output(
            evidence_paths.verifier_stderr,
            stderr,
        )
        if verifier_stderr_error is not None:
            telemetry_errors.append(
                f"could not write verifier stderr metadata: {verifier_stderr_error}"
            )
    if evidence_paths.verifier_command is None:
        return
    verifier_command_error = _write_text(
        evidence_paths.verifier_command,
        json.dumps(
            {
                "command": verifier_command,
                "workspace": str(workspace),
                "timeout_seconds": timeout_seconds,
                "exit_code": exit_code,
                "skipped_reason": skipped_reason,
            },
            indent=2,
            sort_keys=True,
        ),
    )
    if verifier_command_error is not None:
        telemetry_errors.append(
            f"could not write verifier command metadata: {verifier_command_error}"
        )


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


def _capture_reference_file(
    source_path: Path | None,
    *,
    workspace: Path,
    destination: Path,
    label: str,
) -> dict[str, str] | None:
    if source_path is None:
        return None
    source = _resolve_reference_file(source_path, workspace=workspace, label=label)
    if source is None:
        return None
    content = source.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    digest = sha256(content).hexdigest()
    return {
        "source_path": str(source),
        "stored_path": str(destination),
        "sha256": digest,
    }


def _resolve_reference_file(
    source_path: Path | None,
    *,
    workspace: Path,
    label: str,
) -> Path | None:
    if source_path is None:
        return source_path
    candidates = (source_path, workspace / source_path) if not source_path.is_absolute() else (
        source_path,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"{label} file does not exist: {source_path}")


def _command_metadata(
    *,
    command: tuple[str, ...],
    workspace: Path,
    timeout_seconds: int,
    task_id: str,
    attempt_id: str,
    executor: str,
    started_at: str,
    assignment_path: Path,
    liveness_path: Path,
    launch_packet: dict[str, str] | None,
    verifier_intent: dict[str, str] | None,
    exit_code: int | None,
    timed_out: bool | None,
) -> dict[str, object]:
    reasoning = _model_reasoning_metadata(command)
    return {
        "command": list(command),
        "recorded_by": "codex-supervisor.attempt-run",
        "workspace": str(workspace),
        "cwd": str(workspace),
        "timeout_seconds": timeout_seconds,
        "task_id": task_id,
        "attempt_id": attempt_id,
        "executor": executor,
        "launcher": command[0],
        "model_reasoning_effort": reasoning["effort"],
        "model_reasoning_effort_source": reasoning["source"],
        "git_head": _git_head(workspace),
        "started_at": started_at,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "assignment_path": str(assignment_path),
        "liveness_path": str(liveness_path),
        "launch_packet": launch_packet,
        "verifier_intent": verifier_intent,
    }


def _model_reasoning_effort(command: tuple[str, ...]) -> str | None:
    return _model_reasoning_metadata(command)["effort"]


def _model_reasoning_metadata(command: tuple[str, ...]) -> dict[str, str | None]:
    prefix = "model_reasoning_effort="
    for item in command:
        normalized = item.strip().strip("'\"")
        if normalized.startswith(prefix):
            return {
                "effort": normalized.removeprefix(prefix).strip("'\""),
                "source": "command_config",
            }
    if not _uses_packaged_worker_launcher(command):
        return {"effort": None, "source": None}
    explicit = _packaged_worker_launcher_reasoning_arg(command)
    if explicit is not None:
        return {"effort": explicit, "source": "launcher_argument"}
    return {"effort": "xhigh", "source": "launcher_default"}


def _uses_packaged_worker_launcher(command: tuple[str, ...]) -> bool:
    return any(Path(item).name == "codex_worker_launcher.py" for item in command)


def _packaged_worker_launcher_reasoning_arg(command: tuple[str, ...]) -> str | None:
    for index, item in enumerate(command):
        if item == "--reasoning-effort" and index + 1 < len(command):
            return command[index + 1]
        if item.startswith("--reasoning-effort="):
            return item.removeprefix("--reasoning-effort=")
    return None


def _git_head(workspace: Path) -> str | None:
    try:
        completed = subprocess.run(
            ("git", "-C", str(workspace), "rev-parse", "HEAD"),
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
    except FileNotFoundError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


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
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _kill_process_tree(process)
            process.wait()
    stdout_thread.join()
    stderr_thread.join()
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


def _run_verifier_command(
    command: str,
    *,
    workspace: Path,
    environment: dict[str, str],
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    creationflags = (
        int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) if os.name == "nt" else 0
    )
    process = subprocess.Popen(
        command,
        cwd=workspace,
        env=environment,
        shell=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
        start_new_session=os.name != "nt",
        **_TEXT_CAPTURE,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_tree(process)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            _kill_process_tree(process)
            stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(
            cmd=command,
            timeout=timeout_seconds,
            output=stdout if stdout is not None else exc.stdout,
            stderr=stderr if stderr is not None else exc.stderr,
        ) from exc
    return subprocess.CompletedProcess(
        command,
        process.returncode if process.returncode is not None else 1,
        stdout=stdout,
        stderr=stderr,
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
            read_chunk = getattr(pipe, "read1", None)
            chunk = (
                read_chunk(64 * 1024)
                if callable(read_chunk)
                else pipe.read(64 * 1024)  # type: ignore[attr-defined]
            )
            if not chunk:
                break
            _append_retained_output(output_parts, chunk)
            _append_output(output_path, chunk)
            liveness.mark_output()
    finally:
        pipe.close()  # type: ignore[attr-defined]


def _append_output(path: Path, chunk: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    current_size = path.stat().st_size if path.exists() else 0
    if current_size >= RAW_LOG_RETENTION_BYTES:
        return
    remaining = RAW_LOG_RETENTION_BYTES - current_size
    notice = raw_log_truncation_notice(stream_name=path.name)
    normalized_chunk = chunk.decode("utf-8", errors="replace").encode("utf-8")
    will_reach_cap = len(normalized_chunk) >= remaining
    retained_limit = max(0, remaining - len(notice)) if will_reach_cap else remaining
    retained = normalized_chunk[:retained_limit]
    with path.open("ab") as handle:
        handle.write(retained)
        if will_reach_cap:
            handle.write(raw_log_truncation_notice(stream_name=path.name))


def _append_retained_output(output_parts: list[bytes], chunk: bytes) -> None:
    retained = sum(len(part) for part in output_parts)
    remaining = RAW_LOG_RETENTION_BYTES - retained
    if remaining <= 0:
        return
    output_parts.append(chunk[:remaining])


def _terminate_process_tree(
    process: subprocess.Popen[bytes] | subprocess.Popen[str],
) -> None:
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
            kill_process_group(process.pid, signal.SIGTERM)
            return
        except OSError:
            pass
    process.terminate()


def _kill_process_tree(
    process: subprocess.Popen[bytes] | subprocess.Popen[str],
) -> None:
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
            kill_process_group(process.pid, signal.SIGKILL)
            return
        except OSError:
            pass
    process.kill()


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


def _write_retained_text_output(path: Path, content: str) -> str | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = content.encode("utf-8", errors="replace")
        if len(encoded) <= RAW_LOG_RETENTION_BYTES:
            path.write_bytes(encoded)
            return None
        notice = raw_log_truncation_notice(stream_name=path.name)
        retained_limit = max(0, RAW_LOG_RETENTION_BYTES - len(notice))
        path.write_bytes(encoded[:retained_limit] + notice)
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
        relative = artifact_to_workspace_relative(workspace, artifact)
        if relative is None:
            missing.append(artifact)
            continue
        candidate = workspace / relative
        if not candidate.exists():
            missing.append(artifact)
    return tuple(missing)


def _worker_attributed_declared_artifacts(
    artifacts: tuple[str, ...],
    *,
    workspace: Path,
    preexisting_product_paths: set[str],
) -> tuple[str, ...]:
    attributed: list[str] = []
    for artifact in artifacts:
        relative = artifact_to_workspace_relative(workspace, artifact)
        if relative is None:
            continue
        if (
            is_product_path(relative)
            and relative in preexisting_product_paths
        ):
            continue
        attributed.append(artifact)
    return tuple(attributed)


def _worker_attributed_product_paths(
    artifacts: tuple[str, ...],
    *,
    workspace: Path,
) -> tuple[str, ...]:
    product_paths: list[str] = []
    for artifact in artifacts:
        relative = artifact_to_workspace_relative(workspace, artifact)
        if relative is not None and is_product_path(relative):
            product_paths.append(relative)
    return tuple(product_paths)


def _unique_strings(items: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return tuple(unique)
