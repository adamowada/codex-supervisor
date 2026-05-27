import json
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


def test_list_mcp_tools_exposes_read_and_default_on_mutating_schemas(tmp_path: Path) -> None:
    context = McpServerContext(repo_root=tmp_path)

    tools = list_mcp_tools(context=context)

    names = {tool["name"] for tool in tools}
    assert "codex_supervisor.project_list" in names
    assert "codex_supervisor.runtime_preflight" in names
    assert "codex_supervisor.story_loop_status" in names
    assert "codex_supervisor.task_show" in names
    assert "codex_supervisor.task_upsert" in names
    assert "codex_supervisor.task_claim" in names
    assert "codex_supervisor.progress_add" in names
    assert "codex_supervisor.artifact_link_add" in names
    assert "codex_supervisor.story_loop_run_once" in names
    runtime_preflight = next(
        tool for tool in tools if tool["name"] == "codex_supervisor.runtime_preflight"
    )
    assert "Desktop full-AFK canary and runtime preflight" in runtime_preflight["description"]
    assert "codex_supervisor.runtime_preflight" in runtime_preflight["description"]
    read_tools = [tool for tool in tools if tool["name"] == "codex_supervisor.task_show"]
    assert all(tool["annotations"]["readOnlyHint"] is True for tool in read_tools)
    mutating_tool = next(tool for tool in tools if tool["name"] == "codex_supervisor.task_upsert")
    assert "annotations" not in mutating_tool
    assert mutating_tool["inputSchema"]["required"] == [
        "task_id",
        "plan_id",
        "title",
        "goal",
        "task_type",
        "status",
    ]
    worker_run_upsert = next(
        tool for tool in tools if tool["name"] == "codex_supervisor.worker_run_upsert"
    )
    assert worker_run_upsert["inputSchema"]["required"] == [
        "worker_run_id",
        "task_id",
        "backend",
        "status",
    ]
    task_show = next(tool for tool in tools if tool["name"] == "codex_supervisor.task_show")
    assert task_show["inputSchema"]["required"] == ["task_id"]
    task_current = next(tool for tool in tools if tool["name"] == "codex_supervisor.task_current")
    assert task_current["inputSchema"]["required"] == ["story_loop_status_checked"]
    task_next_afk = next(tool for tool in tools if tool["name"] == "codex_supervisor.task_next_afk")
    assert task_next_afk["inputSchema"]["required"] == ["story_loop_status_checked"]
    story_run_once = next(
        tool for tool in tools if tool["name"] == "codex_supervisor.story_loop_run_once"
    )
    story_advance = next(
        tool for tool in tools if tool["name"] == "codex_supervisor.story_loop_advance"
    )
    assert {"codex_executable", "codex_bin"} <= set(story_run_once["inputSchema"]["properties"])
    assert {"codex_executable", "codex_bin"} <= set(story_advance["inputSchema"]["properties"])


def test_runtime_preflight_tool_blocks_hidden_full_afk_mode_switch(tmp_path: Path) -> None:
    db_path = tmp_path / "plans" / "planning.sqlite3"
    initialize_planning_database(db_path)
    context = McpServerContext(repo_root=tmp_path, planning_path=db_path)

    result = dispatch_mcp_tool(
        "codex_supervisor.runtime_preflight",
        {
            "full_afk": True,
            "plugin_invocation": True,
            "supervisor_backend": "skill_only",
            "mcp_tools": [],
            "cli_available": False,
            "worker_execution": "current_thread",
            "native_goal_mode": True,
            "task_current_requested": True,
            "database_mode": "memory_mongodb",
        },
        context=context,
    )

    assert result["ok"] is True
    assert result["data"]["ok"] is False
    issue_codes = {issue["code"] for issue in result["data"]["issues"]}
    assert "supervisor_backend_unavailable" in issue_codes
    assert "mcp_and_cli_unavailable" in issue_codes
    assert "current_thread_fallback_blocked" in issue_codes
    assert "native_goal_unlinked" in issue_codes
    assert "memory_database_fallback_forbidden" in issue_codes
    assert "story_loop_status_required" in issue_codes


def test_runtime_preflight_tool_accepts_desktop_tool_name_aliases(tmp_path: Path) -> None:
    db_path = tmp_path / "plans" / "planning.sqlite3"
    initialize_planning_database(db_path)
    context = McpServerContext(repo_root=tmp_path, planning_path=db_path)

    result = dispatch_mcp_tool(
        "codex_supervisor.runtime_preflight",
        {
            "full_afk": True,
            "plugin_invocation": True,
            "plugin_full_afk": True,
            "supervisor_backend": "mcp",
            "mcp_tools": [
                "mcp__codex_supervisor__.codex_supervisor_runtime_preflight",
                "codex_supervisor_story_loop_status",
                "codex_supervisor_task_current",
                "codex_supervisor_task_next_afk",
                "codex_supervisor_task_claim",
                "codex_supervisor_story_loop_run_once",
            ],
            "worker_execution": "codex_exec",
            "story_loop_status_checked": True,
            "task_current_requested": True,
        },
        context=context,
    )

    assert result["ok"] is True
    assert result["data"]["ok"] is True
    assert result["data"]["ledger"]["decision_source"] == "live_mcp"
    assert result["data"]["diagnostics"]["missing_mcp_tools"] == []
    assert (
        result["data"]["diagnostics"]["mcp_tool_aliases"]["codex_supervisor_task_claim"]
        == "codex_supervisor.task_claim"
    )


def test_runtime_preflight_tool_uses_live_inventory_when_tool_search_snapshot_is_partial(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "plans" / "planning.sqlite3"
    initialize_planning_database(db_path)
    context = McpServerContext(repo_root=tmp_path, planning_path=db_path)

    result = dispatch_mcp_tool(
        "codex_supervisor.runtime_preflight",
        {
            "full_afk": True,
            "plugin_invocation": True,
            "plugin_full_afk": True,
            "supervisor_backend": "mcp",
            "mcp_tools": ["codex_supervisor.runtime_preflight"],
            "worker_execution": "codex_exec",
            "story_loop_status_checked": True,
            "task_current_requested": True,
        },
        context=context,
    )

    assert result["ok"] is True
    assert result["data"]["ok"] is True
    assert result["data"]["diagnostics"]["missing_mcp_tools"] == []
    normalized_tools = set(result["data"]["diagnostics"]["normalized_mcp_tools"])
    assert {
        "codex_supervisor.runtime_preflight",
        "codex_supervisor.story_loop_status",
        "codex_supervisor.task_current",
        "codex_supervisor.task_next_afk",
        "codex_supervisor.task_claim",
        "codex_supervisor.story_loop_run_once",
    } <= normalized_tools


def test_runtime_preflight_tool_ignores_tool_search_as_startup_diagnostic(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "plans" / "planning.sqlite3"
    initialize_planning_database(db_path)
    context = McpServerContext(repo_root=tmp_path, planning_path=db_path)

    result = dispatch_mcp_tool(
        "codex_supervisor.runtime_preflight",
        {
            "full_afk": True,
            "plugin_invocation": True,
            "plugin_full_afk": True,
            "supervisor_backend": "mcp",
            "worker_execution": "codex_exec",
            "story_loop_status_checked": True,
            "task_current_requested": True,
            "mcp_startup_diagnostic": "runtime_preflight tool discovered via tool_search",
        },
        context=context,
    )

    assert result["ok"] is True
    assert result["data"]["ok"] is True
    issue_codes = {issue["code"] for issue in result["data"]["issues"]}
    assert "mcp_startup_failed" not in issue_codes
    assert result["data"]["diagnostics"].get("mcp_startup_diagnostic") is None


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
    assert project["root_path"].startswith("<project-root:")
    assert str(repo.resolve()) not in json.dumps(result, sort_keys=True)


def test_project_list_tool_rejects_roots_outside_configured_scope(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    context = McpServerContext(repo_root=allowed, project_roots=(allowed,))

    result = dispatch_mcp_tool(
        "codex_supervisor.project_list",
        {"root_paths": [str(outside)]},
        context=context,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "out_of_scope_root"


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
    current = dispatch_mcp_tool(
        "codex_supervisor.task_current",
        {"story_loop_status_checked": True},
        context=context,
    )
    next_afk = dispatch_mcp_tool(
        "codex_supervisor.task_next_afk",
        {"story_loop_status_checked": True},
        context=context,
    )
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
    assert next_afk["data"]["task_id"] == "task-mcp"
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
    current_without_status = dispatch_mcp_tool(
        "codex_supervisor.task_current",
        {"story_loop_status_checked": False},
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
    assert current_without_status["error"]["code"] == "story_loop_status_required"
    assert not_found["error"]["code"] == "not_found"
    assert invalid_status["error"]["code"] == "validation_error"


def test_mutating_mcp_tools_update_planning_state_by_default(tmp_path: Path) -> None:
    db_path = tmp_path / "plans" / "planning.sqlite3"
    initialize_planning_database(db_path)
    context = McpServerContext(repo_root=tmp_path, planning_path=db_path)

    plan = dispatch_mcp_tool(
        "codex_supervisor.plan_upsert",
        {
            "plan_id": "plan-mutate",
            "slug": "mutate",
            "title": "Mutate",
            "goal": "Exercise MCP mutations.",
            "status": "active",
            "priority": 10,
        },
        context=context,
    )
    task = dispatch_mcp_tool(
        "codex_supervisor.task_upsert",
        {
            "task_id": "task-mutate",
            "plan_id": "plan-mutate",
            "title": "Mutate through MCP",
            "goal": "Create a production task through MCP.",
            "task_type": "AFK",
            "status": "ready",
            "acceptance_criteria": ["MCP mutation works."],
            "verification_commands": ["uv run --no-sync python -B scripts/verify.py"],
            "allowed_paths": ["src/codex_supervisor/mcp_server.py"],
            "review_required": False,
        },
        context=context,
    )
    progress = dispatch_mcp_tool(
        "codex_supervisor.progress_add",
        {
            "progress_id": "progress-mutate",
            "plan_id": "plan-mutate",
            "event_type": "verified",
            "summary": "MCP mutation path exercised.",
        },
        context=context,
    )
    artifact = dispatch_mcp_tool(
        "codex_supervisor.artifact_link_add",
        {
            "plan_id": "plan-mutate",
            "artifact_id": "insights/v1-hardening-review.md",
            "relationship": "evidence",
        },
        context=context,
    )
    claim = dispatch_mcp_tool(
        "codex_supervisor.task_claim",
        {"worker_run_id": "worker-run-mutate", "task_id": "task-mutate"},
        context=context,
    )

    assert plan["data"]["plan_id"] == "plan-mutate"
    assert task["data"]["task_id"] == "task-mutate"
    assert progress["data"]["progress_id"] == "progress-mutate"
    assert artifact["data"]["artifact_id"] == "insights/v1-hardening-review.md"
    assert claim["data"]["worker_run"]["worker_run_id"] == "worker-run-mutate"
    shown = dispatch_mcp_tool(
        "codex_supervisor.task_show",
        {"task_id": "task-mutate"},
        context=context,
    )
    assert shown["data"]["status"] == "running"


def test_disabled_mutations_hide_mutating_tools_and_reject_dispatch(tmp_path: Path) -> None:
    context = McpServerContext(repo_root=tmp_path, mutations_enabled=False)

    tools = list_mcp_tools(context=context)
    result = dispatch_mcp_tool(
        "codex_supervisor.task_upsert",
        {"task_id": "task-muted"},
        context=context,
    )

    names = {tool["name"] for tool in tools}
    assert "codex_supervisor.project_list" in names
    assert "codex_supervisor.task_upsert" not in names
    assert result["error"]["code"] == "mcp_mutations_disabled"


def test_story_loop_run_once_tool_routes_to_production_service(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "plans" / "planning.sqlite3"
    initialize_planning_database(db_path)
    captured: dict[str, object] = {}

    def fake_run_live_story_loop_once(store, **kwargs):
        captured["store_path"] = store.path
        captured.update(kwargs)
        return {"status": "completed", "worker_run_id": kwargs["worker_run_id"]}

    monkeypatch.setattr(
        "codex_supervisor.mcp_server.run_live_story_loop_once",
        fake_run_live_story_loop_once,
    )
    context = McpServerContext(repo_root=tmp_path, planning_path=db_path)

    result = dispatch_mcp_tool(
        "codex_supervisor.story_loop_run_once",
        {
            "worker_run_id": "worker-run-live",
            "codex_bin": "codex",
            "environment": {"CODEX_SUPERVISOR_TEST": "1"},
        },
        context=context,
    )

    assert result["ok"] is True
    assert result["data"] == {"status": "completed", "worker_run_id": "worker-run-live"}
    assert captured["store_path"] == db_path.resolve()
    assert captured["repo_root"] == tmp_path.resolve()
    assert captured["worker_run_id"] == "worker-run-live"
    assert captured["codex_executable"] == "codex"
    assert captured["environment"] == {"CODEX_SUPERVISOR_TEST": "1"}


def test_story_loop_run_once_tool_prefers_codex_executable_alias(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "plans" / "planning.sqlite3"
    initialize_planning_database(db_path)
    captured: dict[str, object] = {}

    def fake_run_live_story_loop_once(store, **kwargs):
        captured["store_path"] = store.path
        captured.update(kwargs)
        return {"status": "completed", "worker_run_id": kwargs["worker_run_id"]}

    monkeypatch.setattr(
        "codex_supervisor.mcp_server.run_live_story_loop_once",
        fake_run_live_story_loop_once,
    )
    context = McpServerContext(repo_root=tmp_path, planning_path=db_path)

    result = dispatch_mcp_tool(
        "codex_supervisor.story_loop_run_once",
        {
            "worker_run_id": "worker-run-live",
            "codex_executable": "preferred-codex",
            "codex_bin": "legacy-codex",
        },
        context=context,
    )

    assert result["ok"] is True
    assert captured["codex_executable"] == "preferred-codex"


def test_story_loop_run_once_tool_accepts_explicit_project_local_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plugin_cwd = tmp_path / "plugin-cache"
    project_root = tmp_path / "project"
    db_path = project_root / "plans" / "planning.sqlite3"
    project_root.mkdir()
    initialize_planning_database(db_path)
    captured: dict[str, object] = {}

    def fake_run_live_story_loop_once(store, **kwargs):
        captured["store_path"] = store.path
        captured.update(kwargs)
        return {"status": "completed", "worker_run_id": kwargs["worker_run_id"]}

    monkeypatch.setattr(
        "codex_supervisor.mcp_server.run_live_story_loop_once",
        fake_run_live_story_loop_once,
    )
    context = McpServerContext(repo_root=plugin_cwd)

    result = dispatch_mcp_tool(
        "codex_supervisor.story_loop_run_once",
        {
            "worker_run_id": "worker-run-project-local",
            "planning_path": str(db_path),
            "repo_root": str(project_root),
        },
        context=context,
    )

    assert result["ok"] is True
    assert captured["store_path"] == db_path.resolve()
    assert captured["repo_root"] == project_root.resolve()


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
