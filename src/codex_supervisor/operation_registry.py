"""Compact supervisor operation registry."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SupervisorOperation:
    """One active operation exposed by a public surface."""

    name: str
    cli_command: str | None = None
    mcp_tool: str | None = None
    read_only: bool = True


OPERATIONS: tuple[SupervisorOperation, ...] = (
    SupervisorOperation("plan_init", "plan-init", read_only=False),
    SupervisorOperation("plan_list", "plan-list"),
    SupervisorOperation("plan_summary", "plan-summary"),
    SupervisorOperation("task_list", "task-list"),
    SupervisorOperation("task_show", "task-show"),
    SupervisorOperation(
        "queue_next",
        "queue-next",
        "codex_supervisor.queue_next",
    ),
    SupervisorOperation("attempt_transition", "attempt-transition", read_only=False),
)

OPERATIONS_BY_NAME = {operation.name: operation for operation in OPERATIONS}
OPERATIONS_BY_CLI_COMMAND = {
    operation.cli_command: operation
    for operation in OPERATIONS
    if operation.cli_command is not None
}
OPERATIONS_BY_MCP_TOOL = {
    operation.mcp_tool: operation for operation in OPERATIONS if operation.mcp_tool is not None
}


def operation_by_name(name: str) -> SupervisorOperation:
    return OPERATIONS_BY_NAME[name]


def operation_by_cli_command(command: str) -> SupervisorOperation:
    return OPERATIONS_BY_CLI_COMMAND[command]


def operation_by_mcp_tool(tool_name: str) -> SupervisorOperation:
    return OPERATIONS_BY_MCP_TOOL[tool_name]


def cli_command_names() -> frozenset[str]:
    return frozenset(OPERATIONS_BY_CLI_COMMAND)


def mcp_tool_names() -> frozenset[str]:
    return frozenset(OPERATIONS_BY_MCP_TOOL)
