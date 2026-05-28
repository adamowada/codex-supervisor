"""Worker Result Contract loading and validation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_supervisor.worktree_artifacts import ChangedPathViolation, validate_changed_files

JsonObject = dict[str, Any]
MAX_WORKER_RESULT_BYTES = 256 * 1024
WORKER_RESULT_PAYLOAD_KEYS = frozenset(
    {
        "acceptance_results",
        "artifacts",
        "browser_smoke_results",
        "changed_files",
        "completion_notes",
        "follow_up_tasks",
        "handoff_notes",
        "risks",
        "status",
        "summary",
        "tests_run",
        "worker_run_id",
        "worker_run_ids",
    }
)

STALE_COMPLETED_RESULT_BLOCKER_PHRASES = (
    "remains blocked",
    "still blocked",
    "is blocked by",
    "broad supervisor gate is blocked",
    "verification remains blocked",
    "should repair planning",
    "create the required separate afk review task",
)
UNBOUNDED_BROWSER_SMOKE_COMMAND_PATTERNS = (
    re.compile(r"(^|[;&|]\s*)(npm|pnpm|yarn)\s+(run\s+)?dev\b", re.IGNORECASE),
    re.compile(r"(^|[;&|]\s*)vite\b", re.IGNORECASE),
    re.compile(r"(^|[;&|]\s*)docker\s+compose\s+up\b(?!.*\s(-d|--detach)\b)", re.IGNORECASE),
    re.compile(r"(^|[;&|]\s*)docker-compose\s+up\b(?!.*\s(-d|--detach)\b)", re.IGNORECASE),
    re.compile(r"(^|[;&|]\s*)flask\s+run\b", re.IGNORECASE),
    re.compile(r"(^|[;&|]\s*)uvicorn\s+\S+", re.IGNORECASE),
    re.compile(r"(^|[;&|]\s*)node\s+(.*/)?(server|index|app)(\.[cm]?[jt]s)?\b", re.IGNORECASE),
)


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
    redacted_payload_keys: tuple[str, ...] = ()


def load_worker_result(path: Path) -> JsonObject:
    """Load a worker result JSON file as an object."""

    try:
        raw_bytes = path.read_bytes()
        if len(raw_bytes) > MAX_WORKER_RESULT_BYTES:
            msg = (
                "worker result is too large: "
                f"{len(raw_bytes)} bytes exceeds {MAX_WORKER_RESULT_BYTES}"
            )
            raise WorkerResultError(msg)
        payload = json.loads(raw_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        msg = f"worker result is not valid JSON: {exc.msg}"
        raise WorkerResultError(msg) from exc
    except UnicodeDecodeError as exc:
        msg = f"worker result is not valid UTF-8: {exc.reason}"
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
    changed_files_root: Path | None = None,
    artifact_root: Path | None = None,
    result_path: str,
    worker_run_id: str,
    allowed_paths: tuple[str, ...],
    verification_commands: tuple[str, ...],
    acceptance_criteria: tuple[str, ...],
    browser_smoke_required: bool = False,
) -> WorkerResult:
    """Load and validate a Worker Result Contract artifact."""

    return validate_worker_result_payload(
        load_worker_result(path),
        repo_root=repo_root,
        changed_files_root=changed_files_root,
        artifact_root=artifact_root,
        result_path=result_path,
        worker_run_id=worker_run_id,
        allowed_paths=allowed_paths,
        verification_commands=verification_commands,
        acceptance_criteria=acceptance_criteria,
        browser_smoke_required=browser_smoke_required,
    )


def validate_worker_result_payload(
    payload: JsonObject,
    *,
    repo_root: Path,
    changed_files_root: Path | None = None,
    artifact_root: Path | None = None,
    result_path: str,
    worker_run_id: str,
    allowed_paths: tuple[str, ...],
    verification_commands: tuple[str, ...],
    acceptance_criteria: tuple[str, ...],
    browser_smoke_required: bool = False,
) -> WorkerResult:
    """Validate a Worker Result Contract object against a task contract."""

    redacted_payload_keys = worker_result_unknown_payload_keys(payload)
    payload = sanitize_worker_result_payload(payload)
    status = _result_status(payload)
    worker_run_ids = _worker_run_ids(payload, worker_run_id)
    completed = status == "completed"
    changed_files = _string_list(payload, "changed_files", require_nonempty=completed)
    artifacts = _string_list(payload, "artifacts", require_nonempty=False)
    _require_nonblank(payload, "summary")
    _require_completion_notes(payload)
    _require_list(payload, "risks")
    _require_nonempty_list(payload, "follow_up_tasks", allow_empty=True)
    if completed:
        _validate_completed_result_narrative(payload)
    _validate_tests_run(payload, verification_commands, require_success=completed)
    support_root = artifact_root or repo_root
    _validate_browser_smoke_results(
        payload,
        repo_root,
        support_root,
        require_success=completed,
        require_present=completed and browser_smoke_required,
    )
    _validate_acceptance_results(payload, acceptance_criteria, require_passed=completed)
    _validate_artifacts(repo_root, support_root, artifacts, result_path=result_path)
    _validate_changed_files(changed_files_root or repo_root, changed_files, allowed_paths)
    return WorkerResult(
        payload=payload,
        status=status,
        worker_run_ids=worker_run_ids,
        changed_files=changed_files,
        artifacts=artifacts,
        redacted_payload_keys=redacted_payload_keys,
    )


def sanitize_worker_result_payload(payload: JsonObject) -> JsonObject:
    """Return only Worker Result Contract fields safe to persist in tracked SQLite."""

    sanitized = {key: payload[key] for key in sorted(WORKER_RESULT_PAYLOAD_KEYS) if key in payload}
    if "completion_notes" not in sanitized:
        handoff_notes = sanitized.get("handoff_notes")
        if isinstance(handoff_notes, str) and handoff_notes.strip():
            sanitized["completion_notes"] = handoff_notes.strip()
    sanitized.pop("handoff_notes", None)
    return sanitized


def worker_result_unknown_payload_keys(payload: JsonObject) -> tuple[str, ...]:
    """List non-contract keys omitted from persisted raw worker-result payloads."""

    return tuple(sorted(key for key in payload if key not in WORKER_RESULT_PAYLOAD_KEYS))


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
    if not isinstance(value, list):
        msg = f"{key} must be a list"
        raise WorkerResultError(msg)
    if require_nonempty and not value:
        msg = f"{key} must be a nonempty list"
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


def _require_completion_notes(payload: JsonObject) -> None:
    for key in ("completion_notes", "handoff_notes"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return
    msg = "completion_notes or handoff_notes must be nonblank"
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


def _validate_completed_result_narrative(payload: JsonObject) -> None:
    for key in ("risks", "follow_up_tasks"):
        value = payload.get(key)
        if not isinstance(value, list):
            continue
        for index, item in enumerate(value):
            if not isinstance(item, str):
                continue
            phrase = _stale_completed_result_blocker_phrase(item)
            if phrase is None:
                continue
            msg = f"{key}[{index}] contains stale blocker phrase for completed result: {phrase}"
            raise WorkerResultError(msg)


def _stale_completed_result_blocker_phrase(value: str) -> str | None:
    normalized = value.lower()
    return next(
        (phrase for phrase in STALE_COMPLETED_RESULT_BLOCKER_PHRASES if phrase in normalized),
        None,
    )


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
        _validate_bounded_smoke_command(command, field_name="tests_run command")
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


def _validate_browser_smoke_results(
    payload: JsonObject,
    repo_root: Path,
    artifact_root: Path,
    *,
    require_success: bool,
    require_present: bool,
) -> None:
    value = payload.get("browser_smoke_results")
    if value is None:
        if require_present:
            msg = "browser_smoke_results are required for this task"
            raise WorkerResultError(msg)
        return
    if not isinstance(value, list):
        msg = "browser_smoke_results must be a list"
        raise WorkerResultError(msg)
    if require_present and not value:
        msg = "browser_smoke_results must include a passed browser smoke entry"
        raise WorkerResultError(msg)
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            msg = "browser_smoke_results entries must be objects"
            raise WorkerResultError(msg)
        status = item.get("status")
        if status not in {"passed", "failed", "blocked"}:
            msg = f"browser_smoke_results[{index}].status must be passed, failed, or blocked"
            raise WorkerResultError(msg)
        if require_success and status != "passed":
            msg = f"browser_smoke_results[{index}] did not pass"
            raise WorkerResultError(msg)
        summary = item.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            msg = f"browser_smoke_results[{index}].summary must be nonblank"
            raise WorkerResultError(msg)
        exit_code = item.get("exit_code")
        if exit_code is not None:
            if not isinstance(exit_code, int):
                msg = f"browser_smoke_results[{index}].exit_code must be an integer"
                raise WorkerResultError(msg)
            if require_success and exit_code != 0:
                msg = f"browser_smoke_results[{index}] exit_code is {exit_code}"
                raise WorkerResultError(msg)
        for string_key in ("tool", "command", "url"):
            string_value = item.get(string_key)
            if string_value is not None and (
                not isinstance(string_value, str) or not string_value.strip()
            ):
                msg = f"browser_smoke_results[{index}].{string_key} must be nonblank"
                raise WorkerResultError(msg)
            if string_key == "command" and isinstance(string_value, str):
                _validate_bounded_smoke_command(
                    string_value,
                    field_name=f"browser_smoke_results[{index}].command",
                )
        for artifact in _browser_smoke_artifact_paths(item, index):
            _validate_existing_repo_relative_path(
                (artifact_root, repo_root),
                _normalize(artifact),
                "browser_smoke_results",
            )


def _validate_bounded_smoke_command(command: str, *, field_name: str) -> None:
    normalized = command.strip()
    for pattern in UNBOUNDED_BROWSER_SMOKE_COMMAND_PATTERNS:
        if pattern.search(normalized):
            msg = (
                f"{field_name} starts an unbounded dev server; use a bounded smoke harness "
                "that starts child servers with a timeout and always cleans them up"
            )
            raise WorkerResultError(msg)


def _browser_smoke_artifact_paths(item: JsonObject, index: int) -> tuple[str, ...]:
    paths: list[str] = []
    artifact = item.get("artifact")
    if artifact is not None:
        paths.append(
            _browser_smoke_artifact_path(
                artifact,
                f"browser_smoke_results[{index}].artifact",
            )
        )
    artifacts = item.get("artifacts")
    if artifacts is not None:
        if not isinstance(artifacts, list):
            msg = f"browser_smoke_results[{index}].artifacts must be a list"
            raise WorkerResultError(msg)
        for artifact_index, value in enumerate(artifacts):
            paths.append(
                _browser_smoke_artifact_path(
                    value,
                    f"browser_smoke_results[{index}].artifacts[{artifact_index}]",
                )
            )
    return tuple(dict.fromkeys(paths))


def _browser_smoke_artifact_path(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        msg = f"{field_name} must be nonblank"
        raise WorkerResultError(msg)
    normalized = value.strip()
    if ";" in normalized or "\n" in normalized or "\r" in normalized:
        msg = (
            f"{field_name} must be one artifact path; use artifacts[] for multiple browser "
            "smoke files"
        )
        raise WorkerResultError(msg)
    return normalized


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
    artifact_root: Path,
    artifacts: tuple[str, ...],
    *,
    result_path: str,
) -> None:
    normalized_artifacts = tuple(_normalize(path) for path in artifacts)
    normalized_result_path = _normalize(result_path)
    for artifact in normalized_artifacts:
        if artifact == normalized_result_path:
            _validate_repo_relative_path_shape(artifact, "artifacts")
            continue
        _validate_existing_repo_relative_path((artifact_root, repo_root), artifact, "artifacts")


def _validate_changed_files(
    repo_root: Path,
    changed_files: tuple[str, ...],
    allowed_paths: tuple[str, ...],
) -> None:
    normalized_changed_files = tuple(_normalize(path) for path in changed_files)
    for changed_file in normalized_changed_files:
        _validate_repo_relative_path(repo_root, changed_file, "changed_files")
    violations = validate_changed_files(
        normalized_changed_files,
        tuple(_normalize(path) for path in allowed_paths),
    )
    if violations:
        raise WorkerResultError(_changed_path_violation_message(violations[0]))


def _changed_path_violation_message(violation: ChangedPathViolation) -> str:
    if violation.reason == "outside_allowed_paths":
        return f"{violation.path} is not covered by allowed_paths"
    if violation.reason.startswith("unsafe_allowed_path:"):
        return f"allowed_paths entry is unsafe: {violation.path}"
    if violation.reason.startswith("unsafe_changed_file:"):
        return f"changed_files entry is unsafe: {violation.path}"
    return f"{violation.path} is invalid: {violation.reason}"


def _validate_repo_relative_path(repo_root: Path, value: str, field_name: str) -> None:
    _validate_repo_relative_path_shape(value, field_name)
    if not (repo_root / value).exists():
        msg = f"{field_name} entry does not exist: {value}"
        raise WorkerResultError(msg)


def _validate_existing_repo_relative_path(
    roots: tuple[Path, ...],
    value: str,
    field_name: str,
) -> None:
    _validate_repo_relative_path_shape(value, field_name)
    if not any((root / value).exists() for root in roots):
        msg = f"{field_name} entry does not exist: {value}"
        raise WorkerResultError(msg)


def _validate_repo_relative_path_shape(value: str, field_name: str) -> None:
    if Path(value).is_absolute() or ":" in Path(value).parts[0]:
        msg = f"{field_name} entry is not repo-relative: {value}"
        raise WorkerResultError(msg)
    if ".." in Path(value).parts:
        msg = f"{field_name} entry uses parent traversal: {value}"
        raise WorkerResultError(msg)


def _normalize(value: str) -> str:
    return value.strip().replace("\\", "/")
