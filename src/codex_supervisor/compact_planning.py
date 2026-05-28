"""Compact planning SQLite schema and read helpers."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
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


def list_compact_plans(
    database_path: Path,
    *,
    status: str | None = None,
) -> tuple[dict[str, object], ...]:
    """List compact plan records."""

    where = ""
    parameters: tuple[object, ...] = ()
    if status is not None:
        where = "where status = ?"
        parameters = (status,)
    with _connect_read(database_path) as connection:
        rows = connection.execute(
            f"""select plan_id, title, status, priority, goal, created_at, updated_at
                from plans
                {where}
                order by priority desc, created_at asc, plan_id asc""",
            parameters,
        ).fetchall()
    return tuple(dict(row) for row in rows)


def compact_plan_summaries(
    database_path: Path,
    *,
    plan_id: str | None = None,
    active_only: bool = False,
    current_queue: bool = False,
) -> tuple[dict[str, object], ...]:
    """Return compact plan summaries with tasks, attempts, evidence, and decisions."""

    plans = list_compact_plans(database_path)
    if plan_id is not None:
        plans = tuple(plan for plan in plans if plan["plan_id"] == plan_id)
    elif current_queue:
        plans = tuple(plan for plan in plans if plan["status"] in {"active", "blocked"})
    elif active_only:
        plans = tuple(plan for plan in plans if plan["status"] == "active")

    with _connect_read(database_path) as connection:
        return tuple(_summary_for_plan(connection, plan) for plan in plans)


def list_compact_tasks(
    database_path: Path,
    *,
    status: str | None = None,
    active_plans_only: bool = False,
    current_queue_plans_only: bool = False,
) -> tuple[dict[str, object], ...]:
    """List compact task records with plan status attached."""

    clauses: list[str] = []
    parameters: list[object] = []
    if status is not None:
        clauses.append("tasks.status = ?")
        parameters.append(status)
    if active_plans_only:
        clauses.append("plans.status = 'active'")
    if current_queue_plans_only:
        clauses.append("plans.status in ('active', 'blocked')")
    where = f"where {' and '.join(clauses)}" if clauses else ""
    with _connect_read(database_path) as connection:
        rows = connection.execute(
            f"""select tasks.task_id, tasks.plan_id, plans.status as plan_status, tasks.title,
                       tasks.status, tasks.assurance, tasks.intent, tasks.acceptance_json,
                       tasks.created_at, tasks.updated_at
                from tasks
                join plans on plans.plan_id = tasks.plan_id
                {where}
                order by plans.priority desc, tasks.created_at asc, tasks.task_id asc""",
            tuple(parameters),
        ).fetchall()
    return tuple(_task_from_row(row) for row in rows)


def read_compact_task(database_path: Path, task_id: str) -> dict[str, object] | None:
    """Read one compact task record."""

    tasks = list_compact_tasks(database_path)
    return next((task for task in tasks if task["task_id"] == task_id), None)


def _summary_for_plan(connection: sqlite3.Connection, plan: dict[str, object]) -> dict[str, object]:
    plan_id = str(plan["plan_id"])
    tasks = tuple(_task_from_row(row) for row in connection.execute(
        """select tasks.task_id, tasks.plan_id, plans.status as plan_status, tasks.title,
                  tasks.status, tasks.assurance, tasks.intent, tasks.acceptance_json,
                  tasks.created_at, tasks.updated_at
           from tasks
           join plans on plans.plan_id = tasks.plan_id
           where tasks.plan_id = ?
           order by tasks.created_at asc, tasks.task_id asc""",
        (plan_id,),
    ))
    task_ids = tuple(str(task["task_id"]) for task in tasks)
    return {
        "plan": plan,
        "tasks": tasks,
        "attempts": _rows_for_task_ids(connection, "attempts", task_ids),
        "evidence_bundles": _rows_for_task_ids(connection, "evidence_bundles", task_ids),
        "decisions": tuple(
            dict(row)
            for row in connection.execute(
                """select decision_id, plan_id, decision, rationale, created_at
                   from decisions
                   where plan_id = ?
                   order by created_at asc, decision_id asc""",
                (plan_id,),
            )
        ),
    }


def _rows_for_task_ids(
    connection: sqlite3.Connection,
    table: str,
    task_ids: tuple[str, ...],
) -> tuple[dict[str, object], ...]:
    if not task_ids:
        return ()
    placeholders = ", ".join("?" for _ in task_ids)
    return tuple(
        dict(row)
        for row in connection.execute(
            f"select * from {table} where task_id in ({placeholders}) order by task_id",
            task_ids,
        )
    )


def _task_from_row(row: sqlite3.Row) -> dict[str, object]:
    return {
        "task_id": row["task_id"],
        "plan_id": row["plan_id"],
        "plan_status": row["plan_status"],
        "title": row["title"],
        "status": row["status"],
        "assurance": row["assurance"],
        "intent": row["intent"],
        "acceptance_criteria": json.loads(row["acceptance_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@contextmanager
def _connect_read(database_path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("pragma foreign_keys = on")
    try:
        yield connection
    finally:
        connection.close()
