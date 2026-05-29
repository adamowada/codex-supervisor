"""Compact MCP tool registry and dispatcher."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any

from codex_supervisor.paths import default_planning_database_path
from codex_supervisor.small_interface import queue_next

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class McpServerContext:
    """Runtime context for compact MCP dispatch."""

    planning_path: Path | None = None
    enabled: bool = True


@dataclass(frozen=True)
class McpToolDefinition:
    """One MCP tool definition."""

    name: str
    description: str
    input_schema: JsonObject

    def to_payload(self) -> JsonObject:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {"readOnlyHint": True},
        }


class McpDispatchError(Exception):
    """Structured MCP dispatch failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


TOOL_DEFINITIONS: dict[str, McpToolDefinition] = {
    "codex_supervisor.queue_next": McpToolDefinition(
        name="codex_supervisor.queue_next",
        description="Inspect the next compact queue task without mutating planning state.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "additionalProperties": False,
        },
    ),
}


def list_mcp_tools(*, context: McpServerContext | None = None) -> tuple[JsonObject, ...]:
    """Return the compact MCP tool surface."""

    active_context = context or McpServerContext()
    if not active_context.enabled:
        return ()
    return tuple(tool.to_payload() for tool in TOOL_DEFINITIONS.values())


def dispatch_mcp_tool(
    tool_name: str,
    arguments: object | None = None,
    *,
    context: McpServerContext | None = None,
) -> JsonObject:
    """Dispatch one compact MCP tool."""

    active_context = context or McpServerContext()
    if not active_context.enabled:
        return _error_result(tool_name, "mcp_disabled", "MCP dispatch is disabled.")
    definition = TOOL_DEFINITIONS.get(tool_name)
    if definition is None:
        return _error_result(tool_name, "unknown_tool", f"Unknown MCP tool: {tool_name}")
    try:
        parsed = _validate_arguments(definition, arguments)
        result = _handle_queue_next(parsed, active_context)
    except McpDispatchError as exc:
        return _error_result(tool_name, exc.code, exc.message)
    except Exception as exc:
        return _error_result(tool_name, "dispatch_failed", str(exc))
    return {"ok": True, "tool": tool_name, "data": _jsonable(result)}


def _handle_queue_next(arguments: JsonObject, context: McpServerContext) -> object:
    return queue_next(_database_path(arguments, context))


def _database_path(arguments: JsonObject, context: McpServerContext) -> Path:
    raw_path = _optional_string(arguments.get("path"))
    if raw_path is not None:
        return Path(raw_path)
    if context.planning_path is not None:
        return context.planning_path
    return default_planning_database_path()


def _validate_arguments(definition: McpToolDefinition, arguments: object | None) -> JsonObject:
    if arguments is None:
        return {}
    if not isinstance(arguments, dict):
        raise McpDispatchError("validation_error", "MCP tool arguments must be an object.")
    allowed = set(definition.input_schema.get("properties", {}))
    unknown = sorted(str(key) for key in arguments if key not in allowed)
    if unknown:
        raise McpDispatchError(
            "validation_error",
            f"Unexpected MCP tool argument(s): {', '.join(unknown)}",
        )
    return dict(arguments)


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise McpDispatchError("validation_error", "Expected string argument.")
    stripped = value.strip()
    return stripped or None


def _jsonable(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    return value


def _error_result(tool_name: str, code: str, message: str) -> JsonObject:
    return {
        "ok": False,
        "tool": tool_name,
        "error": {"code": code, "message": message},
    }
