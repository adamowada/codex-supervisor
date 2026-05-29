from __future__ import annotations

import sqlite3
from pathlib import Path

from codex_supervisor.compact_planning import initialize_compact_planning_database


def make_planning_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "planning.sqlite3"
    initialize_compact_planning_database(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """insert into plans(plan_id, title, status, priority, goal, created_at, updated_at)
               values ('plan-1', 'Plan', 'active', 1, 'Goal', ?, ?)""",
            ("2026-05-28T17:00:00Z", "2026-05-28T17:00:00Z"),
        )
        connection.commit()
    finally:
        connection.close()
    insert_task(db_path, task_id="task-1", status="ready")
    return db_path


def insert_task(
    db_path: Path,
    *,
    task_id: str,
    status: str,
    assurance: str = "medium",
) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """insert into tasks(
                   task_id, plan_id, title, status, assurance, intent,
                   acceptance_json, created_at, updated_at
               ) values (?, 'plan-1', ?, ?, ?, 'Implement work', ?, ?, ?)""",
            (
                task_id,
                task_id,
                status,
                assurance,
                '["Acceptance criterion"]',
                "2026-05-28T17:00:00Z",
                "2026-05-28T17:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()
