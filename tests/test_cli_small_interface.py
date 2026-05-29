from __future__ import annotations

import json
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
