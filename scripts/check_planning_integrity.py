#!/usr/bin/env python3
"""Validate the fresh simplified planning database."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "plans" / "planning.sqlite3"

EXPECTED_TABLES = {
    "attempts",
    "decisions",
    "evidence_bundles",
    "meta",
    "plans",
    "tasks",
}

REQUIRED_META = {
    "schema_name": "fresh_simplified_planning",
    "schema_version": "1",
}

VALID_PLAN_STATUSES = {"active", "blocked", "done", "dropped"}
VALID_TASK_STATUSES = {"ready", "running", "blocked", "done", "dropped"}
VALID_ATTEMPT_STATUSES = {"planned", "running", "succeeded", "failed", "blocked"}
VALID_ASSURANCE = {"low", "medium", "high"}


def main() -> int:
    failures = check_planning_integrity(DB_PATH)
    if failures:
        print("Fresh planning integrity checks failed.", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Fresh planning integrity checks passed.")
    return 0


def check_planning_integrity(database_path: Path) -> tuple[str, ...]:
    if not database_path.exists():
        return (f"{database_path.relative_to(REPO_ROOT).as_posix()} is missing",)

    failures: list[str] = []
    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        tables = {
            row["name"]
            for row in connection.execute(
                "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
            )
        }
        if tables != EXPECTED_TABLES:
            failures.append(
                f"tables are {sorted(tables)}, expected exactly {sorted(EXPECTED_TABLES)}"
            )
            return tuple(failures)

        meta = {
            row["key"]: row["value"]
            for row in connection.execute("select key, value from meta order by key")
        }
        for key, expected in REQUIRED_META.items():
            if meta.get(key) != expected:
                failures.append(f"meta[{key!r}] is {meta.get(key)!r}, expected {expected!r}")

        _check_values(
            connection,
            failures,
            table="plans",
            column="status",
            allowed=VALID_PLAN_STATUSES,
        )
        _check_values(
            connection,
            failures,
            table="tasks",
            column="status",
            allowed=VALID_TASK_STATUSES,
        )
        _check_values(
            connection,
            failures,
            table="tasks",
            column="assurance",
            allowed=VALID_ASSURANCE,
        )
        _check_values(
            connection,
            failures,
            table="attempts",
            column="status",
            allowed=VALID_ATTEMPT_STATUSES,
        )
        _check_values(
            connection,
            failures,
            table="evidence_bundles",
            column="assurance",
            allowed=VALID_ASSURANCE,
        )

        active_plans = connection.execute(
            "select count(*) from plans where status = 'active'"
        ).fetchone()[0]
        if active_plans != 1:
            failures.append(f"expected exactly one active plan, found {active_plans}")

        ready_tasks = connection.execute(
            "select count(*) from tasks where status = 'ready'"
        ).fetchone()[0]
        if ready_tasks < 1:
            failures.append("expected at least one ready task")

        for table, column in (
            ("tasks", "acceptance_json"),
            ("evidence_bundles", "checks_json"),
            ("evidence_bundles", "artifacts_json"),
        ):
            for row in connection.execute(f"select rowid, {column} from {table}"):
                try:
                    json.loads(row[column])
                except json.JSONDecodeError as exc:
                    failures.append(f"{table}.{column} row {row['rowid']} is invalid JSON: {exc}")
    finally:
        connection.close()

    return tuple(failures)


def _check_values(
    connection: sqlite3.Connection,
    failures: list[str],
    *,
    table: str,
    column: str,
    allowed: set[str],
) -> None:
    rows = connection.execute(f"select distinct {column} as value from {table}").fetchall()
    invalid = sorted(row["value"] for row in rows if row["value"] not in allowed)
    if invalid:
        failures.append(f"{table}.{column} has invalid values {invalid}")


if __name__ == "__main__":
    raise SystemExit(main())
