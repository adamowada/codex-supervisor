from __future__ import annotations

from pathlib import Path

from planning_db_factory import make_planning_db

from codex_supervisor.mcp_server import McpServerContext, dispatch_mcp_tool, list_mcp_tools


def test_mcp_queue_next_is_listed_as_read_only(tmp_path: Path) -> None:
    context = McpServerContext(planning_path=make_planning_db(tmp_path))

    tools = {tool["name"]: tool for tool in list_mcp_tools(context=context)}

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
    assert result["data"]["next_transition"] == "attempt-transition --status running"
