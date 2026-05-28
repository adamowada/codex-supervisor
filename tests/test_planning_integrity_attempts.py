from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

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


def _copy_current_db(tmp_path: Path) -> Path:
    copied = tmp_path / "planning.sqlite3"
    shutil.copyfile(DB_PATH, copied)
    return copied
