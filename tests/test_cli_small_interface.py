from __future__ import annotations

import json
import subprocess
from pathlib import Path

from planning_db_factory import make_planning_db

from codex_supervisor.cli import main


def test_cli_plan_init_creates_compact_schema_for_queue_next(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "planning.sqlite3"

    init_exit = main(["plan-init", "--path", str(db_path)])
    capsys.readouterr()
    queue_exit = main(["queue-next", "--path", str(db_path), "--json"])

    assert init_exit == 0
    assert queue_exit == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["task"] is None
    assert payload["next_transition"] == "none"


def test_cli_plan_init_json_reports_compact_schema(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "planning.sqlite3"

    exit_code = main(["plan-init", "--path", str(db_path), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "initialized": True,
        "path": str(db_path),
        "schema_name": "fresh_simplified_planning",
        "schema_version": "2",
    }


def test_cli_plan_init_ignores_workspace_supervisor_dir_in_git_repo(
    tmp_path: Path,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init")
    db_path = workspace / ".codex-supervisor" / "planning.sqlite3"

    exit_code = main(["plan-init", "--path", str(db_path), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["path"] == str(db_path)
    assert (workspace / ".gitignore").read_text(encoding="utf-8") == ".codex-supervisor/\n"
    assert _git(workspace, "check-ignore", "-q", "--", ".codex-supervisor/planning.sqlite3")
    status = _git(workspace, "status", "--short", "--untracked-files=all").stdout
    assert ".codex-supervisor" not in status


def test_cli_plan_init_appends_supervisor_ignore_rule(
    tmp_path: Path,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init")
    (workspace / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    db_path = workspace / ".codex-supervisor" / "planning.sqlite3"

    assert main(["plan-init", "--path", str(db_path)]) == 0
    capsys.readouterr()

    assert (workspace / ".gitignore").read_text(encoding="utf-8") == (
        "node_modules/\n.codex-supervisor/\n"
    )


def test_cli_plan_init_rejects_tracked_supervisor_dir(
    tmp_path: Path,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init")
    tracked_file = workspace / ".codex-supervisor" / "old-ledger.txt"
    tracked_file.parent.mkdir()
    tracked_file.write_text("tracked\n", encoding="utf-8")
    _git(workspace, "add", ".codex-supervisor/old-ledger.txt")
    db_path = workspace / ".codex-supervisor" / "planning.sqlite3"

    exit_code = main(["plan-init", "--path", str(db_path), "--json"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert ".codex-supervisor is already tracked by git" in captured.err


def test_cli_queue_next_json(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    db_path = make_planning_db(tmp_path)

    exit_code = main(["queue-next", "--path", str(db_path), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["task"]["task_id"] == "task-1"
    assert payload["next_transition"] == "attempt-transition --status running"


def test_cli_task_create_json(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "planning.sqlite3"
    assert main(["plan-init", "--path", str(db_path)]) == 0
    capsys.readouterr()

    exit_code = main(
        [
            "task-create",
            "--path",
            str(db_path),
            "--plan-id",
            "plan-factory",
            "--plan-title",
            "Factory",
            "--plan-goal",
            "Create small projects through generic tasks.",
            "--task-id",
            "task-factory",
            "--title",
            "Create tiny project",
            "--intent",
            "Create a tiny project from a generic task intent.",
            "--assurance",
            "high",
            "--acceptance",
            "Project file exists",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["plan"]["plan_id"] == "plan-factory"
    assert payload["task"]["task_id"] == "task-factory"
    assert payload["task"]["assurance"] == "high"


def test_cli_attempt_transition_json(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    db_path = make_planning_db(tmp_path)

    running_exit = main(
        [
            "attempt-transition",
            "--path",
            str(db_path),
            "--task-id",
            "task-1",
            "--attempt-id",
            "attempt-1",
            "--status",
            "running",
            "--summary",
            "Running task.",
            "--json",
        ]
    )
    capsys.readouterr()
    completed_exit = main(
        [
            "attempt-transition",
            "--path",
            str(db_path),
            "--task-id",
            "task-1",
            "--attempt-id",
            "attempt-1",
            "--status",
            "succeeded",
            "--summary",
            "Task satisfied.",
            "--check",
            "pytest tests/test_cli_small_interface.py",
            "--artifact",
            "src/codex_supervisor/small_interface.py",
            "--acceptance-result",
            "Acceptance criterion=pass",
            "--json",
        ]
    )

    assert running_exit == 0
    assert completed_exit == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["task_status"] == "done"
    assert payload["acceptance"]["accepted"] is True


def test_cli_plain_acceptance_result_is_only_for_single_criterion(
    tmp_path: Path,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    db_path = tmp_path / "planning.sqlite3"
    assert main(["plan-init", "--path", str(db_path)]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "task-create",
                "--path",
                str(db_path),
                "--plan-id",
                "plan-multi",
                "--plan-title",
                "Multi criterion",
                "--plan-goal",
                "Keep acceptance shortcuts unambiguous.",
                "--task-id",
                "task-multi",
                "--title",
                "Two criteria",
                "--intent",
                "Create evidence for a task with two acceptance criteria.",
                "--assurance",
                "high",
                "--acceptance",
                "First criterion",
                "--acceptance",
                "Second criterion",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "attempt-transition",
                "--path",
                str(db_path),
                "--task-id",
                "task-multi",
                "--attempt-id",
                "attempt-multi",
                "--status",
                "running",
                "--summary",
                "Running task.",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()

    exit_code = main(
        [
            "attempt-transition",
            "--path",
            str(db_path),
            "--task-id",
            "task-multi",
            "--attempt-id",
            "attempt-multi",
            "--status",
            "succeeded",
            "--summary",
            "Task satisfied.",
            "--check",
            "Focused check passed.",
            "--artifact",
            "artifact.txt",
            "--acceptance-result",
            "pass",
            "--risk",
            "No residual risk.",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "only valid when the task has exactly one acceptance criterion" in captured.err


def _git(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", str(workspace), *args),
        check=True,
        text=True,
        capture_output=True,
    )
