"""Worker evidence parsing, validation, and persistence adapters."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from codex_supervisor.planning import PlanningSQLiteStore, WorkerRunEventRecord
from codex_supervisor.worker_results import WorkerResult

JsonObject = dict[str, Any]


class WorkerRunEventSink(Protocol):
    """Adapter seam for persisting semantic worker-run events."""

    def record_stream_event(
        self,
        *,
        worker_run_id: str,
        event_index: int,
        event_type: str,
        summary: str,
        details: JsonObject,
        artifact_path: str,
    ) -> None: ...


@dataclass(frozen=True)
class PlanningWorkerRunEventSink:
    """Persist worker-run stream events into planning SQLite."""

    planning_path: Path

    def record_stream_event(
        self,
        *,
        worker_run_id: str,
        event_index: int,
        event_type: str,
        summary: str,
        details: JsonObject,
        artifact_path: str,
    ) -> None:
        record = WorkerRunEventRecord(
            event_id=f"{worker_run_id}-codex-stream-{event_index:06d}",
            worker_run_id=worker_run_id,
            event_type=event_type,
            summary=summary,
            details=details,
            artifact_path=artifact_path,
            metadata={"source": "codex_exec_stdout_stream"},
        )
        PlanningSQLiteStore(self.planning_path).add_worker_run_event(record)


def summarize_codex_exec_stream_event(
    payload: JsonObject,
) -> tuple[str, str, JsonObject] | None:
    """Return a compact semantic event tuple for one Codex Exec JSONL payload."""

    raw_type = payload.get("type")
    if not isinstance(raw_type, str) or not raw_type:
        return None
    event_type = f"codex_exec_{raw_type.replace('.', '_')}"
    details: JsonObject = {"codex_event_type": raw_type}
    if raw_type in {"thread.started", "turn.started"}:
        return event_type, f"Codex Exec {raw_type.replace('.', ' ')}.", details
    if raw_type == "turn.completed":
        usage = payload.get("usage")
        if isinstance(usage, dict):
            details["usage"] = _compact_json_object(usage)
        return event_type, "Codex Exec turn completed.", details
    if raw_type == "turn.failed":
        error = payload.get("error")
        if isinstance(error, dict):
            details["error"] = _compact_json_object(error)
        return event_type, "Codex Exec turn failed.", details
    if raw_type == "error":
        details["error"] = _compact_json_object(payload)
        return event_type, "Codex Exec emitted an error event.", details
    item = payload.get("item")
    if raw_type in {"item.started", "item.updated", "item.completed"} and isinstance(item, dict):
        return _summarize_codex_exec_item_event(raw_type, item)
    return event_type, f"Codex Exec emitted {raw_type}.", details


def jsonl_validation_failure(
    *,
    repo_root: Path,
    jsonl_path: str,
    allow_degraded_jsonl: bool = False,
) -> JsonObject | None:
    """Return a structured JSONL validation failure, or ``None`` when evidence is valid."""

    if allow_degraded_jsonl:
        return None
    path = repo_root / jsonl_path
    if not path.exists():
        return {
            "failure_class": "jsonl_missing",
            "path": jsonl_path,
            "reason": "Codex JSONL evidence file is missing.",
        }
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return {
            "failure_class": "jsonl_unreadable",
            "path": jsonl_path,
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
                "path": jsonl_path,
                "line": line_number,
                "reason": exc.msg,
            }
        if not isinstance(parsed, dict):
            return {
                "failure_class": "jsonl_malformed",
                "path": jsonl_path,
                "line": line_number,
                "reason": "JSONL event must be an object.",
            }
        parsed_count += 1
    if parsed_count == 0:
        return {
            "failure_class": "jsonl_empty",
            "path": jsonl_path,
            "reason": "Codex JSONL evidence file has no events.",
        }
    return None


def worker_result_evidence_validation_failure(
    *,
    repo_root: Path,
    jsonl_path: str,
    worker_result: WorkerResult,
    allow_degraded_jsonl: bool = False,
) -> JsonObject | None:
    """Return a failure when Worker Result claims are unsupported by JSONL evidence."""

    if allow_degraded_jsonl or worker_result.status not in {"completed", "needs_review"}:
        return None
    reported_tests = _worker_result_tests_run_commands(worker_result.payload)
    if not reported_tests:
        return None
    observed_commands = _observed_completed_command_events(repo_root / jsonl_path)
    missing_commands = [
        command
        for command, exit_code in reported_tests
        if not _reported_test_was_observed(command, exit_code, observed_commands)
    ]
    if not missing_commands:
        return None
    return {
        "failure_class": "worker_result_evidence_mismatch",
        "missing_tests_run_commands": missing_commands,
        "path": jsonl_path,
        "reason": (
            "Worker Result tests_run commands were not observed in Codex JSONL command events."
        ),
    }


def _summarize_codex_exec_item_event(
    raw_type: str,
    item: JsonObject,
) -> tuple[str, str, JsonObject]:
    item_type = item.get("type") if isinstance(item.get("type"), str) else "unknown"
    event_type = f"codex_exec_{raw_type.replace('.', '_')}_{item_type}"
    details: JsonObject = {
        "codex_event_type": raw_type,
        "item_id": item.get("id"),
        "item_type": item_type,
    }
    verb = {
        "item.started": "started",
        "item.updated": "updated",
        "item.completed": "completed",
    }.get(raw_type, "reported")
    if item_type == "command_execution":
        command = _truncate_event_text(item.get("command"), limit=300)
        details.update(
            {
                "command": command,
                "status": item.get("status"),
                "exit_code": item.get("exit_code"),
            }
        )
        output = _truncate_event_text(item.get("aggregated_output"), limit=500)
        if output:
            details["aggregated_output_preview"] = output
        return event_type, f"Codex Exec {verb} command: {command}", details
    if item_type == "file_change":
        raw_changes = item.get("changes")
        changes = raw_changes if isinstance(raw_changes, list) else []
        compact_changes = [
            _compact_json_object(change) for change in changes[:20] if isinstance(change, dict)
        ]
        details.update(
            {
                "change_count": len(changes),
                "changes": compact_changes,
                "status": item.get("status"),
            }
        )
        return event_type, f"Codex Exec reported {len(changes)} file change(s).", details
    if item_type == "mcp_tool_call":
        server = _truncate_event_text(item.get("server"), limit=120)
        tool = _truncate_event_text(item.get("tool"), limit=120)
        details.update({"server": server, "tool": tool, "status": item.get("status")})
        return event_type, f"Codex Exec {verb} MCP tool call: {server}.{tool}", details
    if item_type == "todo_list":
        raw_items = item.get("items")
        items = raw_items if isinstance(raw_items, list) else []
        details["item_count"] = len(items)
        details["items"] = [
            _compact_json_object(value) for value in items[:20] if isinstance(value, dict)
        ]
        return event_type, f"Codex Exec {verb} plan/todo list with {len(items)} item(s).", details
    if item_type == "reasoning":
        text = _truncate_event_text(item.get("text"), limit=500)
        details["text_preview"] = text
        return event_type, f"Codex Exec reasoning summary: {text}", details
    if item_type == "agent_message":
        text = _truncate_event_text(item.get("text"), limit=500)
        details["text_preview"] = text
        return event_type, f"Codex Exec agent message: {text}", details
    details["item"] = _compact_json_object(item)
    return event_type, f"Codex Exec {verb} {item_type} item.", details


def _compact_json_object(value: Mapping[str, object]) -> JsonObject:
    compact: JsonObject = {}
    for key, item in value.items():
        if isinstance(item, str):
            compact[str(key)] = _truncate_event_text(item, limit=500)
        elif isinstance(item, (int, float, bool)) or item is None:
            compact[str(key)] = item
        elif isinstance(item, list):
            compact[str(key)] = [
                _compact_json_object(child)
                if isinstance(child, dict)
                else _truncate_event_text(child)
                for child in item[:20]
            ]
        elif isinstance(item, dict):
            compact[str(key)] = _compact_json_object(item)
        else:
            compact[str(key)] = _truncate_event_text(item)
    return compact


def _truncate_event_text(value: object, *, limit: int = 200) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}..."


def _worker_result_tests_run_commands(payload: JsonObject) -> tuple[tuple[str, int], ...]:
    commands: list[tuple[str, int]] = []
    tests_run = payload.get("tests_run")
    if not isinstance(tests_run, list):
        return ()
    for item in tests_run:
        if not isinstance(item, dict):
            continue
        command = item.get("command")
        exit_code = item.get("exit_code")
        if isinstance(command, str) and command.strip() and isinstance(exit_code, int):
            commands.append((command, exit_code))
    return tuple(commands)


def _observed_completed_command_events(path: Path) -> tuple[tuple[str, int], ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    commands: list[tuple[str, int]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        item = payload.get("item")
        if not isinstance(item, dict):
            continue
        if payload.get("type") != "item.completed" or item.get("type") != "command_execution":
            continue
        command = item.get("command")
        exit_code = item.get("exit_code")
        if isinstance(command, str) and command.strip() and isinstance(exit_code, int):
            commands.append((command, exit_code))
    return tuple(commands)


def _reported_test_was_observed(
    reported_command: str,
    reported_exit_code: int,
    observed_commands: tuple[tuple[str, int], ...],
) -> bool:
    for observed_command, observed_exit_code in observed_commands:
        if observed_exit_code != reported_exit_code:
            continue
        if _command_text_matches_reported_test(reported_command, observed_command):
            return True
    return False


def _command_text_matches_reported_test(reported_command: str, observed_command: str) -> bool:
    reported = _normalize_command_text(reported_command)
    if not reported:
        return False
    return reported in _observed_command_variants(observed_command)


def _observed_command_variants(command: str) -> tuple[str, ...]:
    normalized = _normalize_command_text(command)
    variants = [normalized]
    for marker in ("-command", "/c"):
        suffix = _split_after_case_insensitive(normalized, marker)
        if suffix is not None:
            variants.append(_normalize_command_text(suffix))
    return tuple(dict.fromkeys(variant for variant in variants if variant))


def _split_after_case_insensitive(value: str, marker: str) -> str | None:
    index = value.lower().find(marker)
    if index == -1:
        return None
    return value[index + len(marker) :].strip()


def _normalize_command_text(command: str) -> str:
    normalized = " ".join(command.strip().split())
    normalized = normalized.replace("\\", "/")
    while (
        len(normalized) >= 2
        and normalized[0] == normalized[-1]
        and normalized[0] in "'\""
        and normalized.count(normalized[0]) == 2
    ):
        normalized = normalized[1:-1].strip()
    return normalized
