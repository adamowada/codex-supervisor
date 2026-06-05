"""Compact planning SQLite schema helpers."""

from __future__ import annotations

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
create table if not exists acceptance_decisions (
    decision_id text primary key,
    task_id text not null references tasks(task_id) on delete cascade,
    attempt_id text not null references attempts(attempt_id) on delete cascade,
    bundle_id text not null references evidence_bundles(bundle_id) on delete cascade,
    actor text not null,
    result text not null check (result in ('accepted', 'rejected')),
    rationale text not null,
    evaluation_json text not null,
    created_at text not null,
    unique(attempt_id)
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
    """Create the compact planning schema."""

    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute("pragma foreign_keys = on")
        connection.executescript(SCHEMA_SQL)
        connection.execute(
            "insert or replace into meta(key, value) values ('schema_name', ?)",
            ("fresh_simplified_planning",),
        )
        connection.execute(
            "insert or replace into meta(key, value) values ('schema_version', '2')"
        )
