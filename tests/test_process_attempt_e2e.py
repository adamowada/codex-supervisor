from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_full_afk_process_attempt_starts_tiny_project(tmp_path: Path) -> None:
    db_path = tmp_path / "planning.sqlite3"
    workspace = tmp_path / "tiny-project"
    project_file = workspace / "README.md"

    _run_cli("plan-init", "--path", str(db_path))
    _run_cli(
        "task-create",
        "--path",
        str(db_path),
        "--plan-id",
        "plan-afk",
        "--plan-title",
        "AFK project",
        "--plan-goal",
        "Start a tiny project through a generic task intent.",
        "--task-id",
        "task-afk",
        "--title",
        "Create README",
        "--intent",
        "Create a tiny project by writing README.md in the workspace.",
        "--assurance",
        "high",
        "--acceptance",
        "README.md exists",
        "--json",
    )

    completed = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        "task-afk",
        "--attempt-id",
        "attempt-afk",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "10",
        "--check",
        "README.md exists in workspace",
        "--artifact",
        str(project_file),
        "--acceptance-result",
        "README.md exists=pass",
        "--risk",
        "Worker ran inside an isolated temporary workspace.",
        "--json",
        "--",
        sys.executable,
        "-c",
        (
            "from pathlib import Path; "
            "Path('README.md').write_text('# Tiny Project\\n', encoding='utf-8')"
        ),
    )

    payload = json.loads(completed.stdout)
    assert payload["exit_code"] == 0
    assert payload["transition"]["task_status"] == "done"
    assert payload["transition"]["attempt"]["status"] == "succeeded"
    assert payload["transition"]["acceptance"]["accepted"] is True
    assert project_file.read_text(encoding="utf-8") == "# Tiny Project\n"
    assert Path(payload["stdout_path"]).exists()
    assert Path(payload["stderr_path"]).exists()

    queued = json.loads(
        _run_cli("queue-next", "--path", str(db_path), "--json").stdout
    )
    assert queued["task"] is None
    assert queued["next_transition"] == "none"


def test_failed_process_attempt_records_terminal_state(tmp_path: Path) -> None:
    db_path = tmp_path / "planning.sqlite3"
    workspace = tmp_path / "failed-project"

    _run_cli("plan-init", "--path", str(db_path))
    _run_cli(
        "task-create",
        "--path",
        str(db_path),
        "--plan-id",
        "plan-afk",
        "--plan-title",
        "AFK project",
        "--plan-goal",
        "Record failed process attempts durably.",
        "--task-id",
        "task-failed",
        "--title",
        "Fail command",
        "--intent",
        "Run a worker command that fails.",
        "--assurance",
        "medium",
        "--acceptance",
        "Command succeeds",
        "--json",
    )

    completed = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        "task-failed",
        "--attempt-id",
        "attempt-failed",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "10",
        "--json",
        "--",
        sys.executable,
        "-c",
        "raise SystemExit(7)",
    )

    payload = json.loads(completed.stdout)
    assert payload["exit_code"] == 7
    assert payload["transition"]["task_status"] == "blocked"
    assert payload["transition"]["attempt"]["status"] == "failed"
    assert payload["transition"]["acceptance"]["accepted"] is False
    assert Path(payload["stdout_path"]).exists()
    assert Path(payload["stderr_path"]).exists()


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = (
        src_path if not env.get("PYTHONPATH") else src_path + os.pathsep + env["PYTHONPATH"]
    )
    return subprocess.run(
        (sys.executable, "-B", "-m", "codex_supervisor.cli", *args),
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=15,
        env=env,
        check=True,
    )
