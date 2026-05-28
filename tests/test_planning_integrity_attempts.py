from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from planning_db_factory import make_planning_db

from scripts.check_planning_integrity import check_planning_integrity

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "plans" / "planning.sqlite3"


def test_planning_integrity_accepts_current_attempt_relationships(tmp_path: Path) -> None:
    db_path = _copy_current_db(tmp_path)

    assert check_planning_integrity(db_path) == ()


def test_planning_integrity_rejects_evidence_for_another_attempt_task(tmp_path: Path) -> None:
    db_path = _copy_current_db(tmp_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """insert into evidence_bundles(
                   bundle_id, task_id, attempt_id, assurance, summary,
                   checks_json, artifacts_json, created_at
               ) values (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "evidence-task-mismatch",
                "task-rebuild-policy-core-20260528",
                "attempt-rebuild-execution-attempts-20260528",
                "medium",
                "Invalid relationship.",
                '["check"]',
                '["artifact"]',
                "2026-05-28T17:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    failures = check_planning_integrity(db_path)

    assert any("does not match attempt task" in failure for failure in failures)


def test_planning_integrity_rejects_invalid_attempt_timestamps(tmp_path: Path) -> None:
    db_path = _copy_current_db(tmp_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """update attempts
               set status = 'running', finished_at = '2026-05-28T17:01:00Z'
               where attempt_id = 'attempt-rebuild-execution-attempts-20260528'"""
        )
        connection.commit()
    finally:
        connection.close()

    failures = check_planning_integrity(db_path)

    assert any(
        "running attempt" in failure and "cannot have finished_at" in failure
        for failure in failures
    )


def test_planning_integrity_checks_open_tasks_per_active_plan(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("update tasks set status = 'done' where task_id = 'task-1'")
        connection.execute(
            """insert into plans(plan_id, title, status, priority, goal, created_at, updated_at)
               values (?, ?, ?, ?, ?, ?, ?)""",
            (
                "plan-done-with-ready-task",
                "Done plan",
                "done",
                1,
                "Should not hold open work.",
                "2026-05-28T17:00:00Z",
                "2026-05-28T17:00:00Z",
            ),
        )
        connection.execute(
            """insert into tasks(
                   task_id, plan_id, title, status, assurance, intent,
                   acceptance_json, created_at, updated_at
               ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "task-nonactive-ready",
                "plan-done-with-ready-task",
                "Ready task on done plan",
                "ready",
                "medium",
                "This should fail integrity.",
                '["criterion"]',
                "2026-05-28T17:00:00Z",
                "2026-05-28T17:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    failures = check_planning_integrity(db_path)

    assert "expected at least one ready or running task for the active plan" in failures
    assert "non-active plans cannot have ready or running tasks" in failures


def _copy_current_db(tmp_path: Path) -> Path:
    copied = tmp_path / "planning.sqlite3"
    shutil.copyfile(DB_PATH, copied)
    return copied
