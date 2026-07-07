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
    "acceptance_decisions",
    "attempts",
    "decisions",
    "evidence_bundles",
    "meta",
    "plans",
    "tasks",
}

REQUIRED_META = {
    "schema_name": "fresh_simplified_planning",
    "schema_version": "3",
}

VALID_PLAN_STATUSES = {"active", "blocked", "done", "dropped"}
VALID_TASK_STATUSES = {"ready", "running", "blocked", "done", "dropped"}
VALID_ATTEMPT_STATUSES = {"planned", "running", "succeeded", "failed", "blocked"}
VALID_ASSURANCE = {"low", "medium", "high"}
VALID_ACCEPTANCE_RESULTS = {"accepted", "rejected"}
VALID_TASK_LINEAGE_RELATIONS = {"retry_of", "repair_of", "review_of", "shipping_proof_of"}


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
        _check_values(
            connection,
            failures,
            table="acceptance_decisions",
            column="result",
            allowed=VALID_ACCEPTANCE_RESULTS,
        )

        active_plans = connection.execute(
            "select count(*) from plans where status = 'active'"
        ).fetchone()[0]
        done_plans = connection.execute(
            "select count(*) from plans where status = 'done'"
        ).fetchone()[0]
        blocked_plans = connection.execute(
            "select count(*) from plans where status = 'blocked'"
        ).fetchone()[0]
        if active_plans > 1:
            failures.append(f"expected at most one active plan, found {active_plans}")
        if active_plans == 0 and done_plans < 1 and blocked_plans < 1:
            failures.append("expected an active, blocked, or completed plan")

        nonactive_open_tasks = connection.execute(
            """select count(*)
               from tasks
               join plans on plans.plan_id = tasks.plan_id
               where plans.status != 'active'
                 and tasks.status in ('ready', 'running')"""
        ).fetchone()[0]
        if nonactive_open_tasks > 0:
            failures.append("non-active plans cannot have ready or running tasks")

        for row in connection.execute("pragma foreign_key_check"):
            failures.append(
                "foreign key violation: "
                f"table={row['table']} rowid={row['rowid']} parent={row['parent']}"
            )

        for table, column in (
            ("tasks", "acceptance_json"),
            ("evidence_bundles", "checks_json"),
            ("evidence_bundles", "artifacts_json"),
        ):
            for row in connection.execute(f"select rowid, {column} from {table}"):
                try:
                    value = json.loads(row[column])
                except json.JSONDecodeError as exc:
                    failures.append(f"{table}.{column} row {row['rowid']} is invalid JSON: {exc}")
                    continue
                if not isinstance(value, list):
                    failures.append(f"{table}.{column} row {row['rowid']} is not a JSON array")
                elif not all(isinstance(item, str) and item.strip() for item in value):
                    failures.append(
                        f"{table}.{column} row {row['rowid']} must contain non-empty strings"
                    )

        for row in connection.execute(
            "select rowid, evaluation_json from acceptance_decisions"
        ):
            try:
                value = json.loads(row["evaluation_json"])
            except json.JSONDecodeError as exc:
                failures.append(
                    "acceptance_decisions.evaluation_json "
                    f"row {row['rowid']} is invalid JSON: {exc}"
                )
                continue
            if not isinstance(value, dict):
                failures.append(
                    "acceptance_decisions.evaluation_json "
                    f"row {row['rowid']} is not a JSON object"
                )

        _check_attempt_timestamps(connection, failures)
        _check_attempt_relationships(connection, failures)
        _check_task_lineage(connection, failures)
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


def _check_attempt_timestamps(
    connection: sqlite3.Connection,
    failures: list[str],
) -> None:
    for row in connection.execute(
        "select attempt_id, status, started_at, finished_at from attempts order by attempt_id"
    ):
        attempt_id = row["attempt_id"]
        status = row["status"]
        started_at = row["started_at"]
        finished_at = row["finished_at"]
        if status == "planned":
            if started_at is not None or finished_at is not None:
                failures.append(f"planned attempt {attempt_id} cannot have timestamps")
        elif status == "running":
            if started_at is None:
                failures.append(f"running attempt {attempt_id} requires started_at")
            if finished_at is not None:
                failures.append(f"running attempt {attempt_id} cannot have finished_at")
        elif status in {"succeeded", "failed", "blocked"}:
            if started_at is None:
                failures.append(f"terminal attempt {attempt_id} requires started_at")
            if finished_at is None:
                failures.append(f"terminal attempt {attempt_id} requires finished_at")
            if started_at is not None and finished_at is not None and finished_at < started_at:
                failures.append(f"attempt {attempt_id} finished_at cannot precede started_at")


def _check_attempt_relationships(
    connection: sqlite3.Connection,
    failures: list[str],
) -> None:
    for row in connection.execute(
        """select attempts.attempt_id
           from attempts
           left join tasks on tasks.task_id = attempts.task_id
           where tasks.task_id is null"""
    ):
        failures.append(f"attempt {row['attempt_id']} references a missing task")

    for row in connection.execute(
        """select evidence_bundles.bundle_id
           from evidence_bundles
           left join tasks on tasks.task_id = evidence_bundles.task_id
           where tasks.task_id is null"""
    ):
        failures.append(f"evidence bundle {row['bundle_id']} references a missing task")

    for row in connection.execute(
        """select evidence_bundles.bundle_id
           from evidence_bundles
           left join attempts on attempts.attempt_id = evidence_bundles.attempt_id
           where evidence_bundles.attempt_id is not null
             and attempts.attempt_id is null"""
    ):
        failures.append(f"evidence bundle {row['bundle_id']} references a missing attempt")

    for row in connection.execute(
        """select evidence_bundles.bundle_id,
                  evidence_bundles.task_id,
                  attempts.task_id as attempt_task_id
           from evidence_bundles
           join attempts on attempts.attempt_id = evidence_bundles.attempt_id
           where evidence_bundles.attempt_id is not null
             and evidence_bundles.task_id != attempts.task_id"""
    ):
        failures.append(
            f"evidence bundle {row['bundle_id']} task {row['task_id']} does not match "
            f"attempt task {row['attempt_task_id']}"
        )

    for row in connection.execute(
        """select acceptance_decisions.decision_id,
                  acceptance_decisions.task_id,
                  attempts.task_id as attempt_task_id
           from acceptance_decisions
           join attempts on attempts.attempt_id = acceptance_decisions.attempt_id
           where acceptance_decisions.task_id != attempts.task_id"""
    ):
        failures.append(
            f"acceptance decision {row['decision_id']} task {row['task_id']} does not match "
            f"attempt task {row['attempt_task_id']}"
        )

    for row in connection.execute(
        """select acceptance_decisions.decision_id,
                  acceptance_decisions.task_id,
                  evidence_bundles.task_id as bundle_task_id,
                  acceptance_decisions.attempt_id,
                  evidence_bundles.attempt_id as bundle_attempt_id
           from acceptance_decisions
           join evidence_bundles on evidence_bundles.bundle_id = acceptance_decisions.bundle_id
           where acceptance_decisions.task_id != evidence_bundles.task_id
              or acceptance_decisions.attempt_id != evidence_bundles.attempt_id"""
    ):
        failures.append(
            f"acceptance decision {row['decision_id']} does not match evidence bundle "
            f"task/attempt ({row['bundle_task_id']}, {row['bundle_attempt_id']})"
        )

    for row in connection.execute(
        """select attempts.attempt_id
           from attempts
           where attempts.status in ('succeeded', 'failed', 'blocked')
             and exists (
                 select 1 from evidence_bundles
                 where evidence_bundles.attempt_id = attempts.attempt_id
             )
             and not exists (
                 select 1 from acceptance_decisions
                 where acceptance_decisions.attempt_id = attempts.attempt_id
             )"""
    ):
        failures.append(f"terminal attempt {row['attempt_id']} has no acceptance decision")

    for row in connection.execute(
        """select task_id, count(*) as active_attempts
           from attempts
           where status in ('planned', 'running')
           group by task_id
           having count(*) > 1"""
    ):
        failures.append(
            f"task {row['task_id']} has {row['active_attempts']} non-terminal attempts"
        )

    for row in connection.execute(
        """select tasks.task_id
           from tasks
           where tasks.status = 'running'
             and not exists (
                 select 1 from attempts
                 where attempts.task_id = tasks.task_id
                   and attempts.status in ('planned', 'running')
             )"""
    ):
        failures.append(f"running task {row['task_id']} has no non-terminal attempt")

    for row in connection.execute(
        """select tasks.task_id
           from tasks
           where tasks.status = 'done'
             and not exists (
                 select 1
                 from attempts
                 join evidence_bundles
                   on evidence_bundles.attempt_id = attempts.attempt_id
                  and evidence_bundles.task_id = tasks.task_id
                 join acceptance_decisions
                   on acceptance_decisions.attempt_id = attempts.attempt_id
                  and acceptance_decisions.bundle_id = evidence_bundles.bundle_id
                  and acceptance_decisions.result = 'accepted'
                 where attempts.task_id = tasks.task_id
                   and attempts.status = 'succeeded'
             )"""
    ):
        failures.append(
            f"done task {row['task_id']} has no succeeded attempt with evidence "
            "and accepted decision"
        )

    for row in connection.execute(
        """select tasks.task_id
           from tasks
           where tasks.status = 'blocked'
             and not exists (
                 select 1
                 from attempts
                 join evidence_bundles
                   on evidence_bundles.attempt_id = attempts.attempt_id
                  and evidence_bundles.task_id = tasks.task_id
                 join acceptance_decisions
                   on acceptance_decisions.attempt_id = attempts.attempt_id
                  and acceptance_decisions.bundle_id = evidence_bundles.bundle_id
                  and acceptance_decisions.result = 'rejected'
                 where attempts.task_id = tasks.task_id
                   and attempts.status in ('failed', 'blocked', 'succeeded')
             )"""
    ):
        failures.append(
            f"blocked task {row['task_id']} has no terminal attempt with evidence "
            "and rejected decision"
        )


def _check_task_lineage(
    connection: sqlite3.Connection,
    failures: list[str],
) -> None:
    task_rows = connection.execute(
        "select task_id, plan_id, lineage_json from tasks order by task_id"
    ).fetchall()
    task_plans = {row["task_id"]: row["plan_id"] for row in task_rows}
    for row in task_rows:
        task_id = row["task_id"]
        try:
            lineage = json.loads(row["lineage_json"])
        except json.JSONDecodeError as exc:
            failures.append(f"tasks.lineage_json task {task_id} is invalid JSON: {exc}")
            continue
        if not isinstance(lineage, list):
            failures.append(f"tasks.lineage_json task {task_id} is not a JSON array")
            continue
        seen: set[tuple[str, str]] = set()
        for index, item in enumerate(lineage):
            prefix = f"tasks.lineage_json task {task_id} item {index}"
            if not isinstance(item, dict):
                failures.append(f"{prefix} is not a JSON object")
                continue
            relation = item.get("relation")
            target_task_id = item.get("task_id")
            if relation not in VALID_TASK_LINEAGE_RELATIONS:
                failures.append(f"{prefix} has invalid relation {relation!r}")
            if not isinstance(target_task_id, str) or not target_task_id.strip():
                failures.append(f"{prefix} has invalid target task_id {target_task_id!r}")
                continue
            if target_task_id == task_id:
                failures.append(f"{prefix} cannot reference the task itself")
            target_plan_id = task_plans.get(target_task_id)
            if target_plan_id is None:
                failures.append(f"{prefix} references missing task {target_task_id!r}")
            elif target_plan_id != row["plan_id"]:
                failures.append(
                    f"{prefix} references task {target_task_id!r} in plan "
                    f"{target_plan_id!r}, not {row['plan_id']!r}"
                )
            key = (str(relation), target_task_id)
            if key in seen:
                failures.append(f"{prefix} duplicates relation {relation!r} to {target_task_id!r}")
            seen.add(key)


if __name__ == "__main__":
    raise SystemExit(main())
