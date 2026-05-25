import io
import json
from pathlib import Path
from typing import Any

from codex_supervisor.mcp_server import JsonObject, McpServerContext
from codex_supervisor.mcp_stdio import MCP_PROTOCOL_VERSION, McpStdioServer, main, serve_stdio
from codex_supervisor.planning import (
    PlanRecord,
    SupervisorTaskRecord,
    WorkerRunRecord,
    initialize_planning_database,
)


def test_stdio_lifecycle_lists_tools_and_calls_read_only_dispatcher(tmp_path: Path) -> None:
    db_path = _planning_fixture(tmp_path)
    responses = _run_stdio(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1.0"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "ping"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "codex_supervisor.task_show",
                    "arguments": {"task_id": "task-mcp"},
                },
            },
        ],
        context=McpServerContext(repo_root=tmp_path, planning_path=db_path),
    )

    assert [response["id"] for response in responses] == [1, 2, 3, 4]
    assert responses[0]["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION
    assert responses[0]["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert responses[2]["result"]["tools"]
    assert "codex_supervisor.task_show" in {
        tool["name"] for tool in responses[2]["result"]["tools"]
    }
    call_result = responses[3]["result"]
    assert call_result["content"][0]["type"] == "text"
    assert call_result["structuredContent"]["ok"] is True
    assert call_result["structuredContent"]["data"]["task_id"] == "task-mcp"
    assert json.loads(call_result["content"][0]["text"]) == call_result["structuredContent"]
    assert not (tmp_path / "worktrees").exists()


def test_initialized_notification_has_no_response(tmp_path: Path) -> None:
    responses = _run_stdio(
        [
            {"jsonrpc": "2.0", "id": "init", "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
        ],
        context=McpServerContext(repo_root=tmp_path),
    )

    assert [response["id"] for response in responses] == ["init"]


def test_stdio_reports_parse_lifecycle_unknown_and_param_errors(tmp_path: Path) -> None:
    output = io.StringIO()
    serve_stdio(
        io.StringIO(
            "\n".join(
                [
                    "{not json",
                    json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
                    json.dumps({"jsonrpc": "2.0", "id": 2, "method": "initialize"}),
                    json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                    json.dumps({"jsonrpc": "2.0", "id": 3, "method": "unknown/method"}),
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 4,
                            "method": "tools/call",
                            "params": {"arguments": {}},
                        }
                    ),
                    json.dumps([]),
                    "",
                ]
            )
        ),
        output,
        context=McpServerContext(repo_root=tmp_path),
    )
    responses = _parse_output(output)

    assert responses[0]["error"]["code"] == -32700
    assert responses[0]["error"]["data"]["code"] == "parse_error"
    assert responses[1]["error"]["code"] == -32002
    assert responses[1]["error"]["data"]["code"] == "server_not_initialized"
    assert responses[3]["error"]["code"] == -32601
    assert responses[3]["error"]["data"]["code"] == "method_not_found"
    assert responses[4]["error"]["code"] == -32602
    assert responses[4]["error"]["data"]["code"] == "validation_error"
    assert responses[5]["error"]["code"] == -32600
    assert responses[5]["error"]["data"]["code"] == "invalid_request"


def test_disabled_context_returns_empty_tools_and_tool_error_result(tmp_path: Path) -> None:
    responses = _run_stdio(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "codex_supervisor.project_list", "arguments": {}},
            },
        ],
        context=McpServerContext(repo_root=tmp_path, enabled=False),
    )

    assert responses[0]["result"]["capabilities"] == {}
    assert responses[1]["result"] == {"tools": []}
    tool_result = responses[2]["result"]
    assert tool_result["isError"] is True
    assert tool_result["structuredContent"]["error"]["code"] == "mcp_disabled"


def test_disable_mutations_flag_hides_mutating_stdio_tools(tmp_path: Path) -> None:
    db_path = _planning_fixture(tmp_path)
    output = io.StringIO()

    exit_code = main(
        io.StringIO(
            "\n".join(
                [
                    json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
                    json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                    json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 3,
                            "method": "tools/call",
                            "params": {
                                "name": "codex_supervisor.task_upsert",
                                "arguments": {"task_id": "task-muted"},
                            },
                        }
                    ),
                    "",
                ]
            )
        ),
        output,
        argv=[
            "--repo-root",
            str(tmp_path),
            "--planning-path",
            str(db_path),
            "--disable-mutations",
        ],
    )
    responses = _parse_output(output)

    assert exit_code == 0
    tools = responses[1]["result"]["tools"]
    assert "codex_supervisor.task_show" in {tool["name"] for tool in tools}
    assert "codex_supervisor.task_upsert" not in {tool["name"] for tool in tools}
    tool_result = responses[2]["result"]
    assert tool_result["isError"] is True
    assert tool_result["structuredContent"]["error"]["code"] == "mcp_mutations_disabled"


def test_dispatcher_failure_is_mcp_tool_error_without_stdout_contamination(
    tmp_path: Path,
) -> None:
    def failing_dispatcher(
        tool_name: str,
        arguments: object | None,
        context: McpServerContext,
    ) -> JsonObject:
        raise RuntimeError("boom")

    output = io.StringIO()
    server = McpStdioServer(
        context=McpServerContext(repo_root=tmp_path),
        tool_dispatcher=failing_dispatcher,
    )
    exit_code = serve_stdio(
        io.StringIO(
            "\n".join(
                [
                    json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
                    json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 2,
                            "method": "tools/call",
                            "params": {"name": "codex_supervisor.project_list", "arguments": {}},
                        }
                    ),
                    "",
                ]
            )
        ),
        output,
        server=server,
    )
    responses = _parse_output(output)

    assert exit_code == 0
    assert len(responses) == 2
    tool_result = responses[1]["result"]
    assert tool_result["isError"] is True
    assert tool_result["structuredContent"]["error"] == {
        "code": "dispatcher_failed",
        "message": "boom",
    }
    assert all(
        set(json.loads(line)).issubset({"error", "id", "jsonrpc", "result"})
        for line in output.getvalue().splitlines()
    )


def test_main_entrypoint_accepts_injected_streams(tmp_path: Path) -> None:
    output = io.StringIO()

    exit_code = main(
        io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}) + "\n"),
        output,
        context=McpServerContext(repo_root=tmp_path),
    )

    assert exit_code == 0
    assert _parse_output(output)[0]["result"]["serverInfo"]["name"] == "codex-supervisor"


def _run_stdio(messages: list[dict[str, Any]], *, context: McpServerContext) -> list[JsonObject]:
    input_stream = io.StringIO("\n".join(json.dumps(message) for message in messages) + "\n")
    output_stream = io.StringIO()
    serve_stdio(input_stream, output_stream, context=context)
    return _parse_output(output_stream)


def _parse_output(output: io.StringIO) -> list[JsonObject]:
    return [json.loads(line) for line in output.getvalue().splitlines()]


def _planning_fixture(tmp_path: Path) -> Path:
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
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="worker-run-mcp",
            task_id="task-mcp",
            backend="codex_exec",
            status="queued",
        )
    )
    return db_path
