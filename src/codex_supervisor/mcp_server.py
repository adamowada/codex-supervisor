"""Read-only MCP tool registry and dispatcher."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from typing import Any

from codex_supervisor.paths import default_planning_database_path, find_repo_root
from codex_supervisor.planning import (
    PLAN_STATUSES,
    PlanningSQLiteStore,
    SupervisorTaskSummaryRecord,
    WorkerRunRecord,
    open_existing_planning_database,
)
from codex_supervisor.projects import discover_projects
from codex_supervisor.story_loop import build_story_loop_status

JsonObject = dict[str, Any]
McpHandler = Callable[[JsonObject, "McpServerContext"], Any]


@dataclass(frozen=True)
class McpToolDefinition:
    """Thin MCP tool definition compatible with JSON-schema-style inputs."""

    name: str
    description: str
    input_schema: JsonObject
    read_only: bool = True

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }
        if self.read_only:
            payload["annotations"] = {"readOnlyHint": True}
        return payload


@dataclass(frozen=True)
class McpServerContext:
    """Runtime context for in-process MCP tool dispatch."""

    repo_root: Path | None = None
    planning_path: Path | None = None
    project_roots: tuple[Path, ...] = ()
    trust_policy: str = "local_trusted"
    enabled: bool = True

    def resolved_repo_root(self) -> Path:
        return (self.repo_root or find_repo_root()).resolve()

    def resolved_planning_path(self) -> Path:
        if self.planning_path is not None:
            return self.planning_path.resolve()
        return default_planning_database_path(self.resolved_repo_root())

    def resolved_project_roots(self) -> tuple[Path, ...]:
        if self.project_roots:
            return tuple(path.resolve() for path in self.project_roots)
        return (self.resolved_repo_root(),)


class McpDispatchError(ValueError):
    """Tool dispatch error rendered into a structured MCP error envelope."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def list_mcp_tools(*, context: McpServerContext | None = None) -> tuple[JsonObject, ...]:
    """Return the read-only MCP tools exposed by this slice."""

    dispatch_context = context or McpServerContext()
    if not dispatch_context.enabled:
        return ()
    return tuple(tool.to_payload() for tool in TOOL_DEFINITIONS.values())


def dispatch_mcp_tool(
    tool_name: str,
    arguments: object | None = None,
    *,
    context: McpServerContext | None = None,
) -> JsonObject:
    """Dispatch one read-only MCP tool and return a normalized result envelope."""

    dispatch_context = context or McpServerContext()
    if not dispatch_context.enabled:
        return _error_result(tool_name, "mcp_disabled", "MCP dispatch is disabled.")
    definition = TOOL_DEFINITIONS.get(tool_name)
    handler = TOOL_HANDLERS.get(tool_name)
    if definition is None or handler is None:
        return _error_result(tool_name, "unknown_tool", f"Unknown MCP tool: {tool_name}")
    try:
        validated_arguments = _validate_arguments(definition, arguments)
        data = handler(validated_arguments, dispatch_context)
    except McpDispatchError as exc:
        return _error_result(tool_name, exc.code, exc.message)
    except (OSError, sqlite3.Error, ValueError) as exc:
        return _error_result(tool_name, "read_failed", str(exc))
    return {
        "ok": True,
        "tool": tool_name,
        "data": _to_jsonable(data),
    }


def _handle_project_list(arguments: JsonObject, context: McpServerContext) -> tuple[object, ...]:
    root_paths = arguments.get("root_paths")
    trust_policy = str(arguments.get("trust_policy") or context.trust_policy)
    roots = (
        tuple(Path(path) for path in root_paths)
        if isinstance(root_paths, list)
        else context.resolved_project_roots()
    )
    return discover_projects(roots, trust_policy=trust_policy)


def _handle_story_loop_status(arguments: JsonObject, context: McpServerContext) -> object:
    store = _open_store(context)
    plan_id = _optional_string(arguments.get("plan_id"))
    if plan_id is not None:
        _require_plan_visible(store, plan_id=plan_id, include_all=bool(arguments.get("all")))
    return build_story_loop_status(
        store,
        active_only=not bool(arguments.get("all")),
        plan_id=plan_id,
    )


def _handle_plan_list(arguments: JsonObject, context: McpServerContext) -> tuple[object, ...]:
    store = _open_store(context)
    return store.list_plans(status=_optional_string(arguments.get("status")))


def _handle_task_current(arguments: JsonObject, context: McpServerContext) -> object | None:
    _reject_unexpected_arguments(arguments)
    return _open_store(context).next_ready_afk_task()


def _handle_task_show(arguments: JsonObject, context: McpServerContext) -> object:
    task_id = _required_string(arguments, "task_id")
    task = _find_task(_open_store(context), task_id)
    if task is None:
        raise McpDispatchError("not_found", f"No supervisor task found: {task_id}")
    return task


def _handle_worker_run_list(arguments: JsonObject, context: McpServerContext) -> tuple[object, ...]:
    task_id = _optional_string(arguments.get("task_id"))
    return _open_store(context).list_worker_runs(task_id=task_id)


def _handle_worker_run_show(arguments: JsonObject, context: McpServerContext) -> object:
    worker_run_id = _required_string(arguments, "worker_run_id")
    run = _find_worker_run(_open_store(context), worker_run_id)
    if run is None:
        raise McpDispatchError("not_found", f"No worker run found: {worker_run_id}")
    return run


def _handle_worker_result_list(
    arguments: JsonObject,
    context: McpServerContext,
) -> tuple[object, ...]:
    _reject_unexpected_arguments(arguments)
    return _open_store(context).list_worker_results()


def _handle_worker_result_show(arguments: JsonObject, context: McpServerContext) -> object:
    result_id = _required_string(arguments, "result_id")
    result = next(
        (
            candidate
            for candidate in _open_store(context).list_worker_results()
            if candidate.result_id == result_id
        ),
        None,
    )
    if result is None:
        raise McpDispatchError("not_found", f"No worker result found: {result_id}")
    return result


def _open_store(context: McpServerContext) -> PlanningSQLiteStore:
    return open_existing_planning_database(context.resolved_planning_path(), read_only=True)


def _require_plan_visible(
    store: PlanningSQLiteStore,
    *,
    plan_id: str,
    include_all: bool,
) -> None:
    plan = next(
        (candidate for candidate in store.list_plans() if candidate.plan_id == plan_id),
        None,
    )
    if plan is None:
        raise McpDispatchError("not_found", f"No plan found: {plan_id}")
    if not include_all and plan.status not in {"active", "blocked"}:
        raise McpDispatchError(
            "historical_plan",
            f"Plan {plan_id} is {plan.status}; pass all=true to inspect historical plans.",
        )


def _find_task(
    store: PlanningSQLiteStore,
    task_id: str,
) -> SupervisorTaskSummaryRecord | None:
    return next((task for task in store.list_supervisor_tasks() if task.task_id == task_id), None)


def _find_worker_run(
    store: PlanningSQLiteStore,
    worker_run_id: str,
) -> WorkerRunRecord | None:
    return next(
        (run for run in store.list_worker_runs() if run.worker_run_id == worker_run_id),
        None,
    )


def _validate_arguments(definition: McpToolDefinition, arguments: object | None) -> JsonObject:
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise McpDispatchError("validation_error", "MCP tool arguments must be an object.")
    schema = definition.input_schema
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        properties = {}
    required = schema.get("required", ())
    required_names = tuple(str(name) for name in required) if isinstance(required, list) else ()
    if schema.get("additionalProperties") is False:
        unknown = sorted(set(arguments) - set(properties))
        if unknown:
            raise McpDispatchError(
                "validation_error",
                f"Unexpected MCP tool argument(s): {', '.join(unknown)}",
            )
    for required_name in required_names:
        if _optional_string(arguments.get(required_name)) is None:
            raise McpDispatchError(
                "validation_error",
                f"Missing required MCP tool argument: {required_name}",
            )
    for key, value in arguments.items():
        property_schema = properties.get(key)
        if isinstance(property_schema, dict):
            _validate_argument_type(key, value, property_schema)
    return dict(arguments)


def _validate_argument_type(key: str, value: object, schema: Mapping[str, object]) -> None:
    expected_type = schema.get("type")
    if expected_type == "string" and not isinstance(value, str):
        raise McpDispatchError("validation_error", f"{key} must be a string.")
    if expected_type == "boolean" and not isinstance(value, bool):
        raise McpDispatchError("validation_error", f"{key} must be a boolean.")
    if expected_type == "array":
        if not isinstance(value, list):
            raise McpDispatchError("validation_error", f"{key} must be an array.")
        item_schema = schema.get("items")
        if (
            isinstance(item_schema, dict)
            and item_schema.get("type") == "string"
            and not all(isinstance(item, str) and item.strip() for item in value)
        ):
            raise McpDispatchError(
                "validation_error",
                f"{key} must contain only nonblank strings.",
            )
    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        allowed = ", ".join(str(item) for item in enum)
        raise McpDispatchError("validation_error", f"{key} must be one of: {allowed}.")


def _reject_unexpected_arguments(arguments: JsonObject) -> None:
    if arguments:
        names = ", ".join(sorted(arguments))
        raise McpDispatchError("validation_error", f"Unexpected MCP tool argument(s): {names}")


def _required_string(arguments: JsonObject, key: str) -> str:
    value = _optional_string(arguments.get(key))
    if value is None:
        raise McpDispatchError("validation_error", f"Missing required MCP tool argument: {key}")
    return value


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _error_result(tool_name: str, code: str, message: str) -> JsonObject:
    return {
        "ok": False,
        "tool": tool_name,
        "error": {
            "code": code,
            "message": message,
        },
    }


def _to_jsonable(value: object) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _to_jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple | list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    return value


TOOL_DEFINITIONS: dict[str, McpToolDefinition] = {
    "codex_supervisor.project_list": McpToolDefinition(
        name="codex_supervisor.project_list",
        description="List supervised project roots and adapter facts.",
        input_schema={
            "type": "object",
            "properties": {
                "root_paths": {"type": "array", "items": {"type": "string"}},
                "trust_policy": {"type": "string"},
            },
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.story_loop_status": McpToolDefinition(
        name="codex_supervisor.story_loop_status",
        description="Report Story Loop queue state from canonical planning state.",
        input_schema={
            "type": "object",
            "properties": {
                "all": {"type": "boolean"},
                "plan_id": {"type": "string"},
            },
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.plan_list": McpToolDefinition(
        name="codex_supervisor.plan_list",
        description="List planning records, optionally filtered by plan status.",
        input_schema={
            "type": "object",
            "properties": {"status": {"type": "string", "enum": sorted(PLAN_STATUSES)}},
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.task_current": McpToolDefinition(
        name="codex_supervisor.task_current",
        description="Return the current executable ready AFK task, if any.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    "codex_supervisor.task_show": McpToolDefinition(
        name="codex_supervisor.task_show",
        description="Show one supervisor task by task_id.",
        input_schema={
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.worker_run_list": McpToolDefinition(
        name="codex_supervisor.worker_run_list",
        description="List worker runs, optionally filtered by task_id.",
        input_schema={
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.worker_run_show": McpToolDefinition(
        name="codex_supervisor.worker_run_show",
        description="Show one worker run by worker_run_id.",
        input_schema={
            "type": "object",
            "properties": {"worker_run_id": {"type": "string"}},
            "required": ["worker_run_id"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.worker_result_list": McpToolDefinition(
        name="codex_supervisor.worker_result_list",
        description="List DB-backed worker result records.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    "codex_supervisor.worker_result_show": McpToolDefinition(
        name="codex_supervisor.worker_result_show",
        description="Show one DB-backed worker result by result_id.",
        input_schema={
            "type": "object",
            "properties": {"result_id": {"type": "string"}},
            "required": ["result_id"],
            "additionalProperties": False,
        },
    ),
}

TOOL_HANDLERS: dict[str, McpHandler] = {
    "codex_supervisor.project_list": _handle_project_list,
    "codex_supervisor.story_loop_status": _handle_story_loop_status,
    "codex_supervisor.plan_list": _handle_plan_list,
    "codex_supervisor.task_current": _handle_task_current,
    "codex_supervisor.task_show": _handle_task_show,
    "codex_supervisor.worker_run_list": _handle_worker_run_list,
    "codex_supervisor.worker_run_show": _handle_worker_run_show,
    "codex_supervisor.worker_result_list": _handle_worker_result_list,
    "codex_supervisor.worker_result_show": _handle_worker_result_show,
}
