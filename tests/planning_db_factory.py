from __future__ import annotations

import sqlite3
from pathlib import Path


def make_planning_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "planning.sqlite3"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            create table meta (
                key text primary key,
                value text not null
            );
            create table plans (
                plan_id text primary key,
                title text not null,
                status text not null check (status in ('active', 'blocked', 'done', 'dropped')),
                priority integer not null,
                goal text not null,
                created_at text not null,
                updated_at text not null
            );
            create table tasks (
                task_id text primary key,
                plan_id text not null references plans(plan_id) on delete cascade,
                title text not null,
                status text not null check (
                    status in ('ready', 'running', 'blocked', 'done', 'dropped')
                ),
                assurance text not null check (assurance in ('low', 'medium', 'high')),
                intent text not null,
                acceptance_json text not null,
                created_at text not null,
                updated_at text not null
            );
            create table attempts (
                attempt_id text primary key,
                task_id text not null references tasks(task_id) on delete cascade,
                executor text not null,
                status text not null check (
                    status in ('planned', 'running', 'succeeded', 'failed', 'blocked')
                ),
                summary text not null,
                started_at text,
                finished_at text
            );
            create unique index attempts_one_nonterminal_per_task
                on attempts(task_id)
                where status in ('planned', 'running');
            create table evidence_bundles (
                bundle_id text primary key,
                task_id text not null references tasks(task_id) on delete cascade,
                attempt_id text references attempts(attempt_id) on delete set null,
                assurance text not null check (assurance in ('low', 'medium', 'high')),
                summary text not null,
                checks_json text not null,
                artifacts_json text not null,
                created_at text not null
            );
            create table decisions (
                decision_id text primary key,
                plan_id text references plans(plan_id) on delete set null,
                decision text not null,
                rationale text not null,
                created_at text not null
            );
            """
        )
        connection.execute(
            "insert into meta(key, value) values ('schema_name', 'fresh_simplified_planning')"
        )
        connection.execute("insert into meta(key, value) values ('schema_version', '1')")
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
