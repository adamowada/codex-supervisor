from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from planning_db_factory import make_planning_db

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mcp_stdio_lists_and_calls_queue_tool(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)

    responses = _run_mcp_stdio(
        db_path,
        (
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-11-25"},
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "codex_supervisor.queue_next",
                    "arguments": {},
                },
            },
        ),
    )

    assert [response["id"] for response in responses] == [1, 2, 3]
    assert responses[0]["result"]["serverInfo"]["name"] == "codex-supervisor"
    assert responses[1]["result"]["tools"][0]["name"] == "codex_supervisor.queue_next"
    structured = responses[2]["result"]["structuredContent"]
    assert structured["ok"] is True
    assert structured["data"]["task"]["task_id"] == "task-1"
    assert structured["data"]["next_transition"] == "attempt-transition --status running"


def test_mcp_stdio_rejects_removed_queue_selector_axis(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)

    responses = _run_mcp_stdio(
        db_path,
        (
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "codex_supervisor.queue_next",
                    "arguments": {"task_status": "running"},
                },
            },
        ),
    )

    tool_result = responses[1]["result"]
    structured = tool_result["structuredContent"]
    assert tool_result["isError"] is True
    assert structured["ok"] is False
    assert structured["error"]["code"] == "validation_error"


def _run_mcp_stdio(
    db_path: Path,
    messages: tuple[dict[str, object], ...],
) -> list[dict[str, object]]:
    env = os.environ.copy()
    src_path = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = (
        src_path if not env.get("PYTHONPATH") else src_path + os.pathsep + env["PYTHONPATH"]
    )
    completed = subprocess.run(
        (
            sys.executable,
            "-B",
            "-m",
            "codex_supervisor.mcp_stdio",
            "--planning-path",
            str(db_path),
        ),
        cwd=REPO_ROOT,
        input="".join(json.dumps(message) + "\n" for message in messages),
        text=True,
        capture_output=True,
        timeout=10,
        env=env,
        check=True,
    )
    return [json.loads(line) for line in completed.stdout.splitlines()]
