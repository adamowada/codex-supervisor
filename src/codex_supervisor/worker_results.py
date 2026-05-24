"""Worker Result Contract loading and validation."""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

JsonObject = dict[str, Any]


class WorkerResultError(ValueError):
    """Raised when worker result evidence cannot advance a worker run."""


@dataclass(frozen=True)
class WorkerResult:
    """Validated worker result evidence."""

    payload: JsonObject
    status: str
    worker_run_ids: tuple[str, ...]
    changed_files: tuple[str, ...]
    artifacts: tuple[str, ...]


def load_worker_result(path: Path) -> JsonObject:
    """Load a worker result JSON file as an object."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = f"worker result is not valid JSON: {exc.msg}"
        raise WorkerResultError(msg) from exc
    except FileNotFoundError as exc:
        msg = f"worker result does not exist: {path}"
        raise WorkerResultError(msg) from exc
    if not isinstance(payload, dict):
        msg = "worker result must be a JSON object"
        raise WorkerResultError(msg)
    return payload


def validate_worker_result_file(
    path: Path,
    *,
    repo_root: Path,
    result_path: str,
    worker_run_id: str,
    allowed_paths: tuple[str, ...],
    verification_commands: tuple[str, ...],
    acceptance_criteria: tuple[str, ...],
) -> WorkerResult:
    """Load and validate a Worker Result Contract artifact."""

    return validate_worker_result_payload(
        load_worker_result(path),
        repo_root=repo_root,
        result_path=result_path,
        worker_run_id=worker_run_id,
        allowed_paths=allowed_paths,
        verification_commands=verification_commands,
        acceptance_criteria=acceptance_criteria,
    )


def validate_worker_result_payload(
    payload: JsonObject,
    *,
    repo_root: Path,
    result_path: str,
    worker_run_id: str,
    allowed_paths: tuple[str, ...],
    verification_commands: tuple[str, ...],
    acceptance_criteria: tuple[str, ...],
) -> WorkerResult:
    """Validate a Worker Result Contract object against a task contract."""

    status = _result_status(payload)
    worker_run_ids = _worker_run_ids(payload, worker_run_id)
    completed = status == "completed"
    changed_files = _string_list(payload, "changed_files", require_nonempty=completed)
    artifacts = _string_list(payload, "artifacts", require_nonempty=completed)
    _require_nonblank(payload, "summary")
    _require_nonblank(payload, "handoff_notes")
    _require_list(payload, "risks")
    _require_nonempty_list(payload, "follow_up_tasks", allow_empty=True)
    _validate_tests_run(payload, verification_commands, require_success=completed)
    _validate_acceptance_results(payload, acceptance_criteria, require_passed=completed)
    _validate_artifacts(repo_root, artifacts, result_path, require_durable=completed)
    _validate_changed_files(repo_root, changed_files, allowed_paths)
    return WorkerResult(
        payload=payload,
        status=status,
        worker_run_ids=worker_run_ids,
        changed_files=changed_files,
        artifacts=artifacts,
    )


def _result_status(payload: JsonObject) -> str:
    value = payload.get("status")
    if value not in {"completed", "blocked", "failed", "needs_review"}:
        msg = "worker result status must be completed, blocked, failed, or needs_review"
        raise WorkerResultError(msg)
    return str(value)


def _worker_run_ids(payload: JsonObject, worker_run_id: str) -> tuple[str, ...]:
    if "worker_run_id" in payload:
        value = payload["worker_run_id"]
        if value != worker_run_id:
            msg = f"worker result points at {value!r}, not {worker_run_id!r}"
            raise WorkerResultError(msg)
        return (worker_run_id,)
    value = payload.get("worker_run_ids")
    if not isinstance(value, list) or not value:
        msg = "worker result must declare worker_run_id or nonempty worker_run_ids"
        raise WorkerResultError(msg)
    worker_run_ids = tuple(item for item in value if isinstance(item, str) and item.strip())
    if len(worker_run_ids) != len(value) or worker_run_id not in worker_run_ids:
        msg = "worker_run_ids must be nonblank strings and include this worker run"
        raise WorkerResultError(msg)
    return worker_run_ids


def _string_list(
    payload: JsonObject,
    key: str,
    *,
    require_nonempty: bool,
) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or (require_nonempty and not value):
        msg = f"{key} must be a list"
        raise WorkerResultError(msg)
    strings = tuple(item for item in value if isinstance(item, str) and item.strip())
    if len(strings) != len(value):
        msg = f"{key} entries must be nonblank strings"
        raise WorkerResultError(msg)
    return strings


def _require_nonblank(payload: JsonObject, key: str) -> None:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        msg = f"{key} must be nonblank"
        raise WorkerResultError(msg)


def _require_list(payload: JsonObject, key: str) -> None:
    value = payload.get(key)
    if not isinstance(value, list):
        msg = f"{key} must be a list"
        raise WorkerResultError(msg)


def _require_nonempty_list(payload: JsonObject, key: str, *, allow_empty: bool = False) -> None:
    value = payload.get(key)
    if not isinstance(value, list) or (not value and not allow_empty):
        msg = f"{key} must be a list"
        raise WorkerResultError(msg)


def _validate_tests_run(
    payload: JsonObject,
    verification_commands: tuple[str, ...],
    *,
    require_success: bool,
) -> None:
    value = payload.get("tests_run")
    if not isinstance(value, list) or (require_success and not value):
        msg = "tests_run must be a list"
        raise WorkerResultError(msg)
    commands: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            msg = "tests_run entries must be objects"
            raise WorkerResultError(msg)
        command = item.get("command")
        exit_code = item.get("exit_code")
        summary = item.get("summary")
        if not isinstance(command, str) or not command.strip():
            msg = "tests_run command must be nonblank"
            raise WorkerResultError(msg)
        if require_success and exit_code != 0:
            msg = f"tests_run command {command!r} did not pass"
            raise WorkerResultError(msg)
        if not isinstance(summary, str) or not summary.strip():
            msg = "tests_run summary must be nonblank"
            raise WorkerResultError(msg)
        commands.add(command)
    missing = [command for command in verification_commands if command not in commands]
    if require_success and missing:
        msg = f"tests_run missing task verification command: {missing[0]}"
        raise WorkerResultError(msg)


def _validate_acceptance_results(
    payload: JsonObject,
    acceptance_criteria: tuple[str, ...],
    *,
    require_passed: bool,
) -> None:
    value = payload.get("acceptance_results")
    if not isinstance(value, dict) or (require_passed and not value):
        msg = "acceptance_results must be an object"
        raise WorkerResultError(msg)
    if not require_passed:
        return
    for criterion in acceptance_criteria:
        result = value.get(criterion)
        if not isinstance(result, dict) or result.get("status") != "passed":
            msg = f"acceptance_results missing passing evidence for {criterion!r}"
            raise WorkerResultError(msg)
        evidence = result.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            msg = f"acceptance_results evidence is missing for {criterion!r}"
            raise WorkerResultError(msg)


def _validate_artifacts(
    repo_root: Path,
    artifacts: tuple[str, ...],
    result_path: str,
    *,
    require_durable: bool,
) -> None:
    normalized_result_path = _normalize(result_path)
    normalized_artifacts = tuple(_normalize(path) for path in artifacts)
    if require_durable and _is_ignored_run_output(normalized_result_path):
        msg = (
            "completed worker result_path must be durable tracked evidence: "
            f"{normalized_result_path}"
        )
        raise WorkerResultError(msg)
    if require_durable and normalized_result_path not in normalized_artifacts:
        msg = f"artifacts must include result_path {normalized_result_path}"
        raise WorkerResultError(msg)
    for artifact in normalized_artifacts:
        _validate_repo_relative_path(repo_root, artifact, "artifacts")


def _validate_changed_files(
    repo_root: Path,
    changed_files: tuple[str, ...],
    allowed_paths: tuple[str, ...],
) -> None:
    normalized_allowed = tuple(_normalize(path) for path in allowed_paths)
    for changed_file in tuple(_normalize(path) for path in changed_files):
        _validate_repo_relative_path(repo_root, changed_file, "changed_files")
        if not any(_matches_allowed_path(changed_file, allowed) for allowed in normalized_allowed):
            msg = f"{changed_file} is not covered by allowed_paths"
            raise WorkerResultError(msg)


def _is_ignored_run_output(path: str) -> bool:
    return path.split("/", 1)[0] in {"artifacts", "logs", "runs", "worktrees"}


def _validate_repo_relative_path(repo_root: Path, value: str, field_name: str) -> None:
    if Path(value).is_absolute() or ":" in Path(value).parts[0]:
        msg = f"{field_name} entry is not repo-relative: {value}"
        raise WorkerResultError(msg)
    if ".." in Path(value).parts:
        msg = f"{field_name} entry uses parent traversal: {value}"
        raise WorkerResultError(msg)
    if not (repo_root / value).exists():
        msg = f"{field_name} entry does not exist: {value}"
        raise WorkerResultError(msg)


def _matches_allowed_path(path: str, allowed: str) -> bool:
    if allowed.endswith("/**"):
        prefix = allowed[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return path == allowed or fnmatch.fnmatchcase(path, allowed)


def _normalize(value: str) -> str:
    return value.strip().replace("\\", "/")
