from __future__ import annotations

from pathlib import Path

from planning_db_factory import make_planning_db

from codex_supervisor.mcp_server import McpServerContext, dispatch_mcp_tool, list_mcp_tools


def test_mcp_queue_next_is_listed_as_read_only(tmp_path: Path) -> None:
    context = McpServerContext(planning_path=make_planning_db(tmp_path))

    tools = {tool["name"]: tool for tool in list_mcp_tools(context=context)}

    assert list(tools) == ["codex_supervisor.queue_next"]
    assert "codex_supervisor.queue_next" in tools
    assert tools["codex_supervisor.queue_next"]["annotations"] == {"readOnlyHint": True}


def test_mcp_queue_next_dispatches_to_compact_queue(tmp_path: Path) -> None:
    context = McpServerContext(planning_path=make_planning_db(tmp_path))

    result = dispatch_mcp_tool(
        "codex_supervisor.queue_next",
        {},
        context=context,
    )

    assert result["ok"] is True
    assert result["data"]["task"]["task_id"] == "task-1"
    assert result["data"]["recovery_state"]["active_task_id"] == "task-1"
    assert "git_summary" in result["data"]["recovery_state"]
    assert result["data"]["next_transition"] == "attempt-transition --status running"


def test_mcp_queue_next_rejects_relative_tool_path() -> None:
    result = dispatch_mcp_tool(
        "codex_supervisor.queue_next",
        {"path": ".codex-supervisor/planning.sqlite3"},
        context=McpServerContext(),
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "planning_path_must_be_absolute"


def test_mcp_queue_next_rejects_relative_context_path() -> None:
    result = dispatch_mcp_tool(
        "codex_supervisor.queue_next",
        {},
        context=McpServerContext(planning_path=Path("relative.sqlite3")),
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "planning_path_must_be_absolute"
