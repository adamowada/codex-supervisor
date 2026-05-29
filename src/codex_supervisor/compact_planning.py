"""Compact planning SQLite schema and bootstrap helpers."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA_SQL = """
create table if not exists meta (
    key text primary key,
    value text not null
);
create table if not exists plans (
    plan_id text primary key,
    title text not null,
    status text not null check (status in ('active', 'blocked', 'done', 'dropped')),
    priority integer not null,
    goal text not null,
    created_at text not null,
    updated_at text not null
);
create table if not exists tasks (
    task_id text primary key,
    plan_id text not null references plans(plan_id) on delete cascade,
    title text not null,
    status text not null check (status in ('ready', 'running', 'blocked', 'done', 'dropped')),
    assurance text not null check (assurance in ('low', 'medium', 'high')),
    intent text not null,
    acceptance_json text not null,
    created_at text not null,
    updated_at text not null
);
create table if not exists attempts (
    attempt_id text primary key,
    task_id text not null references tasks(task_id) on delete cascade,
    executor text not null,
    status text not null check (status in ('planned', 'running', 'succeeded', 'failed', 'blocked')),
    summary text not null,
    started_at text,
    finished_at text
);
create unique index if not exists attempts_one_nonterminal_per_task
    on attempts(task_id)
    where status in ('planned', 'running');
create table if not exists evidence_bundles (
    bundle_id text primary key,
    task_id text not null references tasks(task_id) on delete cascade,
    attempt_id text references attempts(attempt_id) on delete set null,
    assurance text not null check (assurance in ('low', 'medium', 'high')),
    summary text not null,
    checks_json text not null,
    artifacts_json text not null,
    created_at text not null
);
create table if not exists decisions (
    decision_id text primary key,
    plan_id text references plans(plan_id) on delete set null,
    decision text not null,
    rationale text not null,
    created_at text not null
);
"""


def initialize_compact_planning_database(database_path: Path) -> None:
    """Create the compact six-table planning schema."""

    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute("pragma foreign_keys = on")
        connection.executescript(SCHEMA_SQL)
        connection.execute(
            "insert or replace into meta(key, value) values ('schema_name', ?)",
            ("fresh_simplified_planning",),
        )
        connection.execute(
            "insert or replace into meta(key, value) values ('schema_version', '1')"
        )


def seed_compact_bootstrap_plan(database_path: Path, *, created_at: str) -> None:
    """Seed one compact bootstrap plan and ready task."""

    with sqlite3.connect(database_path) as connection:
        connection.execute("pragma foreign_keys = on")
        connection.execute(
            """insert or ignore into plans(
                   plan_id, title, status, priority, goal, created_at, updated_at
               )
               values (?, ?, ?, ?, ?, ?, ?)""",
            (
                "plan-bootstrap-supervisor",
                "Bootstrap Codex Supervisor",
                "active",
                100,
                "Continue compact supervisor implementation through task, attempt, "
                "evidence, and acceptance.",
                created_at,
                created_at,
            ),
        )
        connection.execute(
            """insert or ignore into tasks(
                   task_id, plan_id, title, status, assurance, intent,
                   acceptance_json, created_at, updated_at
               ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "task-bootstrap-orient-and-plan",
                "plan-bootstrap-supervisor",
                "Orient and continue compact implementation",
                "ready",
                "medium",
                "Inspect compact planning state and continue the next implementation task.",
                json.dumps(["Compact planning commands work.", "Verification passes."], indent=2),
                created_at,
                created_at,
            ),
        )
