from pathlib import Path

from codex_supervisor.mcp_server import (
    McpServerContext,
    dispatch_mcp_tool,
    list_mcp_tools,
)
from codex_supervisor.planning import (
    PlanRecord,
    SupervisorTaskRecord,
    WorkerRunRecord,
    initialize_planning_database,
)


def test_list_mcp_tools_exposes_read_only_tool_schemas(tmp_path: Path) -> None:
    context = McpServerContext(repo_root=tmp_path)

    tools = list_mcp_tools(context=context)

    names = {tool["name"] for tool in tools}
    assert "codex_supervisor.project_list" in names
    assert "codex_supervisor.story_loop_status" in names
    assert "codex_supervisor.task_show" in names
    assert all(tool["annotations"]["readOnlyHint"] is True for tool in tools)
    task_show = next(tool for tool in tools if tool["name"] == "codex_supervisor.task_show")
    assert task_show["inputSchema"]["required"] == ["task_id"]


def test_project_list_tool_delegates_to_project_registry(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (repo / "PLANS.md").write_text("# Plans\n", encoding="utf-8")
    context = McpServerContext(repo_root=tmp_path)

    result = dispatch_mcp_tool(
        "codex_supervisor.project_list",
        {"root_paths": [str(repo)]},
        context=context,
    )

    assert result["ok"] is True
    project = result["data"][0]
    assert project["adapter_type"] == "generic_repo"
    assert project["status"] == "ready"
    assert project["facts"]["authority_markers"] == ["AGENTS.md", "PLANS.md"]


def test_planning_read_tools_delegate_without_mutating_or_launching(tmp_path: Path) -> None:
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-mcp",
            slug="mcp",
            title="MCP",
            goal="Expose read-only MCP data.",
            status="active",
            priority=10,
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-mcp",
            plan_id="plan-mcp",
            title="Add MCP",
            goal="Expose task data.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["Tool works."],
            verification_commands=["uv run --no-sync python -B scripts/verify.py"],
            allowed_paths=["src/codex_supervisor/mcp_server.py"],
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-mcp-done",
            plan_id="plan-mcp",
            title="Completed MCP fixture",
            goal="Provide worker-run fixture data.",
            task_type="AFK",
            status="completed",
            acceptance_criteria=["Done."],
            verification_commands=["uv run --no-sync python -B scripts/verify.py"],
            allowed_paths=["src/codex_supervisor/mcp_server.py"],
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="worker-run-mcp",
            task_id="task-mcp-done",
            backend="codex_exec",
            status="completed",
            result_path="worker-results/run-mcp-worker-result.json",
        )
    )
    context = McpServerContext(repo_root=tmp_path, planning_path=db_path)

    plans = dispatch_mcp_tool("codex_supervisor.plan_list", {"status": "active"}, context=context)
    status = dispatch_mcp_tool("codex_supervisor.story_loop_status", {}, context=context)
    current = dispatch_mcp_tool("codex_supervisor.task_current", {}, context=context)
    shown_task = dispatch_mcp_tool(
        "codex_supervisor.task_show",
        {"task_id": "task-mcp"},
        context=context,
    )
    runs = dispatch_mcp_tool(
        "codex_supervisor.worker_run_list",
        {"task_id": "task-mcp-done"},
        context=context,
    )
    shown_run = dispatch_mcp_tool(
        "codex_supervisor.worker_run_show",
        {"worker_run_id": "worker-run-mcp"},
        context=context,
    )

    assert plans["data"][0]["plan_id"] == "plan-mcp"
    assert status["data"]["queue_state"] == "ready"
    assert status["data"]["current_task_id"] == "task-mcp"
    assert current["data"]["task_id"] == "task-mcp"
    assert shown_task["data"]["plan_id"] == "plan-mcp"
    assert runs["data"][0]["worker_run_id"] == "worker-run-mcp"
    assert shown_run["data"]["status"] == "completed"
    assert not (tmp_path / "worktrees").exists()
    assert store.list_supervisor_tasks()[0].status == "ready"


def test_dispatch_reports_validation_unknown_and_missing_errors(tmp_path: Path) -> None:
    db_path = tmp_path / "plans" / "planning.sqlite3"
    initialize_planning_database(db_path)
    context = McpServerContext(repo_root=tmp_path, planning_path=db_path)

    missing_argument = dispatch_mcp_tool(
        "codex_supervisor.task_show",
        {},
        context=context,
    )
    unknown_tool = dispatch_mcp_tool(
        "codex_supervisor.worker_launch",
        {},
        context=context,
    )
    not_found = dispatch_mcp_tool(
        "codex_supervisor.worker_run_show",
        {"worker_run_id": "missing"},
        context=context,
    )
    invalid_status = dispatch_mcp_tool(
        "codex_supervisor.plan_list",
        {"status": "wat"},
        context=context,
    )

    assert missing_argument["error"]["code"] == "validation_error"
    assert unknown_tool["error"]["code"] == "unknown_tool"
    assert not_found["error"]["code"] == "not_found"
    assert invalid_status["error"]["code"] == "validation_error"


def test_disabled_mcp_context_hides_tools_and_rejects_dispatch(tmp_path: Path) -> None:
    context = McpServerContext(repo_root=tmp_path, enabled=False)

    tools = list_mcp_tools(context=context)
    result = dispatch_mcp_tool("codex_supervisor.project_list", {}, context=context)

    assert tools == ()
    assert result == {
        "ok": False,
        "tool": "codex_supervisor.project_list",
        "error": {
            "code": "mcp_disabled",
            "message": "MCP dispatch is disabled.",
        },
    }
