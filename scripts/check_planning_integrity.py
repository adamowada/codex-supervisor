#!/usr/bin/env python3
"""Fail on planning SQLite drift that can mislead fresh Codex threads."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_supervisor.paths import default_planning_database_path  # noqa: E402
from codex_supervisor.planning import (  # noqa: E402
    CRITERION_STATUSES,
    CURRENT_QUEUE_PLAN_STATUSES,
    MILESTONE_STATUSES,
    NONTERMINAL_WORKER_RUN_STATUSES,
    OPEN_CRITERION_STATUSES,
    OPEN_TASK_STATUSES,
    PLAN_STATUSES,
    TASK_STATUSES,
    TASK_STATUSES_ALLOWED_WITH_NONTERMINAL_WORKER_RUN,
    WORKER_RUN_STATUSES,
    open_existing_planning_database,
    unsafe_repo_relative_path_patterns,
    unsafe_verification_command_reason,
    unsafe_worker_result_path_reason,
)

CONTRACT_PLAN_STATUSES = CURRENT_QUEUE_PLAN_STATUSES
CONTRACT_TASK_STATUSES = ("ready", "running", "blocked", "reviewing")
JSON_OBJECT_COLUMNS = (
    ("plans", "non_goals_json"),
    ("plans", "context_json"),
    ("plan_milestones", "details_json"),
    ("supervisor_tasks", "scope_json"),
    ("supervisor_tasks", "out_of_scope_json"),
    ("worker_runs", "metadata_json"),
)
JSON_ARRAY_COLUMNS = (
    ("supervisor_tasks", "acceptance_criteria_json"),
    ("supervisor_tasks", "verification_commands_json"),
    ("supervisor_tasks", "allowed_paths_json"),
    ("supervisor_tasks", "blocked_by_json"),
)
WORKER_RESULT_REQUIRED_KEYS = frozenset(
    {
        "status",
        "summary",
        "changed_files",
        "tests_run",
        "acceptance_results",
        "risks",
        "follow_up_tasks",
        "artifacts",
        "handoff_notes",
    }
)
WORKER_RESULT_STATUSES = frozenset({"completed", "blocked", "failed", "needs_review"})
FULL_COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
STALE_TEST_SUMMARY_PHRASES = ("at the time", "previously passed", "passed previously")


@dataclass(frozen=True)
class PlanningIntegrityFailure:
    check_name: str
    reason: str


def check_planning_integrity(db_path: Path) -> tuple[PlanningIntegrityFailure, ...]:
    failures: list[PlanningIntegrityFailure] = []
    if not db_path.exists():
        return (PlanningIntegrityFailure("database_exists", f"missing database: {db_path}"),)

    try:
        open_existing_planning_database(db_path, validate=True)
    except (ValueError, sqlite3.Error) as exc:
        return (PlanningIntegrityFailure("planning_schema", str(exc)),)

    uri = f"file:{quote(db_path.resolve().as_posix(), safe='/:')}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        return (PlanningIntegrityFailure("database_open", str(exc)),)
    try:
        try:
            failures.extend(_check_sqlite_integrity(connection))
            failures.extend(
                _check_status_values(
                    connection,
                    table="plans",
                    allowed=PLAN_STATUSES,
                )
            )
            failures.extend(
                _check_status_values(
                    connection,
                    table="plan_milestones",
                    allowed=MILESTONE_STATUSES,
                )
            )
            failures.extend(
                _check_status_values(
                    connection,
                    table="plan_acceptance_criteria",
                    allowed=CRITERION_STATUSES,
                )
            )
            failures.extend(
                _check_status_values(
                    connection,
                    table="supervisor_tasks",
                    allowed=TASK_STATUSES,
                )
            )
            failures.extend(
                _check_status_values(
                    connection,
                    table="worker_runs",
                    allowed=WORKER_RUN_STATUSES,
                )
            )
            failures.extend(_check_current_queue_pending_criteria_have_open_tasks(connection))
            failures.extend(_check_json_columns(connection))
            failures.extend(_check_json_string_array_elements(connection))
            failures.extend(_check_acceptance_criterion_verification_commands(connection))
            repo_root = db_path.resolve().parent.parent
            failures.extend(_check_plan_artifact_paths_are_repo_local(connection, repo_root))
            failures.extend(_check_plan_commit_links_are_full_shas(connection))
            failures.extend(_check_plan_commit_links_exist_in_git(connection, repo_root))
            failures.extend(_check_current_queue_plans_have_operational_structure(connection))
            failures.extend(_check_completed_plans_have_completed_criteria(connection))
            failures.extend(_check_completed_plans_have_no_open_tasks(connection))
            failures.extend(_check_nonterminal_worker_runs_match_task_state(connection))
            failures.extend(_check_open_afk_tasks_have_execution_contracts(connection))
            failures.extend(_check_open_afk_task_contract_values(connection))
            failures.extend(_check_completed_worker_runs_have_result_paths(connection))
            failures.extend(_check_completed_afk_tasks_have_worker_evidence(connection))
            failures.extend(_check_completed_worker_result_paths_are_local_json(connection))
            failures.extend(_check_completed_worker_run_results_exist(connection, repo_root))
            failures.extend(_check_completed_worker_json_results(connection, repo_root))
            failures.extend(_check_completed_worker_runs_are_linked(connection))
            failures.extend(_check_progress_links_are_declared(connection))
            failures.extend(_check_plan_timestamps_cover_progress(connection))
        except sqlite3.Error as exc:
            failures.append(PlanningIntegrityFailure("planning_schema", str(exc)))
    finally:
        connection.close()

    return tuple(failures)


def _check_sqlite_integrity(connection: sqlite3.Connection) -> tuple[PlanningIntegrityFailure, ...]:
    failures: list[PlanningIntegrityFailure] = []
    integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    if integrity != "ok":
        failures.append(PlanningIntegrityFailure("integrity_check", integrity))
    foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_rows:
        failures.append(
            PlanningIntegrityFailure("foreign_key_check", f"{len(foreign_key_rows)} violation(s)")
        )
    return tuple(failures)


def _check_status_values(
    connection: sqlite3.Connection,
    *,
    table: str,
    allowed: frozenset[str],
) -> tuple[PlanningIntegrityFailure, ...]:
    placeholders = ", ".join("?" for _ in allowed)
    rows = connection.execute(
        f"""
        SELECT status, COUNT(*)
        FROM {table}
        WHERE status NOT IN ({placeholders})
        GROUP BY status
        """,
        tuple(sorted(allowed)),
    ).fetchall()
    return tuple(
        PlanningIntegrityFailure(
            f"{table}_status",
            f"unexpected status {status!r} appears {count} time(s)",
        )
        for status, count in rows
    )


def _check_current_queue_pending_criteria_have_open_tasks(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    plan_placeholders = ", ".join("?" for _ in CURRENT_QUEUE_PLAN_STATUSES)
    rows = connection.execute(
        f"""
        SELECT ac.criterion_id, ac.plan_id
        FROM plan_acceptance_criteria ac
        JOIN plans p ON p.plan_id = ac.plan_id
        WHERE p.status IN ({plan_placeholders})
          AND ac.status = 'pending'
          AND NOT EXISTS (
              SELECT 1 FROM supervisor_tasks st
              WHERE st.plan_id = p.plan_id
                AND st.status IN ({", ".join("?" for _ in OPEN_TASK_STATUSES)})
          )
        """,
        (*CURRENT_QUEUE_PLAN_STATUSES, *OPEN_TASK_STATUSES),
    ).fetchall()
    return tuple(
        PlanningIntegrityFailure(
            "current_queue_pending_criterion_without_open_task",
            f"{criterion_id} on {plan_id}",
        )
        for criterion_id, plan_id in rows
    )


def _check_completed_plans_have_no_open_tasks(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        f"""
        SELECT st.task_id, st.plan_id, st.status
        FROM supervisor_tasks st
        JOIN plans p ON p.plan_id = st.plan_id
        WHERE p.status IN ('completed', 'abandoned', 'superseded')
          AND st.status IN ({", ".join("?" for _ in OPEN_TASK_STATUSES)})
        ORDER BY st.plan_id, st.task_id
        """,
        tuple(sorted(OPEN_TASK_STATUSES)),
    ).fetchall()
    return tuple(
        PlanningIntegrityFailure(
            "open_task_on_inactive_plan",
            f"{task_id} on {plan_id} is {status}",
        )
        for task_id, plan_id, status in rows
    )


def _check_nonterminal_worker_runs_match_task_state(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    run_placeholders = ", ".join("?" for _ in NONTERMINAL_WORKER_RUN_STATUSES)
    task_placeholders = ", ".join("?" for _ in TASK_STATUSES_ALLOWED_WITH_NONTERMINAL_WORKER_RUN)
    rows = connection.execute(
        f"""
        SELECT wr.worker_run_id, wr.status, st.task_id, st.status
        FROM worker_runs wr
        JOIN supervisor_tasks st ON st.task_id = wr.task_id
        WHERE wr.status IN ({run_placeholders})
          AND st.status NOT IN ({task_placeholders})
        ORDER BY st.task_id, wr.worker_run_id
        """,
        (
            *sorted(NONTERMINAL_WORKER_RUN_STATUSES),
            *sorted(TASK_STATUSES_ALLOWED_WITH_NONTERMINAL_WORKER_RUN),
        ),
    ).fetchall()
    return tuple(
        PlanningIntegrityFailure(
            "nonterminal_worker_run_hidden_by_task_status",
            f"{worker_run_id} is {worker_status} but {task_id} is {task_status}",
        )
        for worker_run_id, worker_status, task_id, task_status in rows
    )


def _check_json_columns(connection: sqlite3.Connection) -> tuple[PlanningIntegrityFailure, ...]:
    failures: list[PlanningIntegrityFailure] = []
    for table, column in JSON_OBJECT_COLUMNS:
        failures.extend(_check_json_column_type(connection, table, column, dict))
    for table, column in JSON_ARRAY_COLUMNS:
        failures.extend(_check_json_column_type(connection, table, column, list))
    return tuple(failures)


def _check_json_string_array_elements(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    failures: list[PlanningIntegrityFailure] = []
    for table, column in JSON_ARRAY_COLUMNS:
        rowid_column = _rowid_column(table)
        rows = connection.execute(f"SELECT {rowid_column}, {column} FROM {table}").fetchall()
        for row_id, raw_value in rows:
            try:
                values = json.loads(str(raw_value))
            except json.JSONDecodeError:
                continue
            if not isinstance(values, list):
                continue
            for index, value in enumerate(values):
                if isinstance(value, str) and value.strip():
                    continue
                failures.append(
                    PlanningIntegrityFailure(
                        "invalid_json_string_array_value",
                        f"{table}.{column} on {row_id}[{index}] must be a nonblank string",
                    )
                )
    return tuple(failures)


def _check_acceptance_criterion_verification_commands(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT criterion_id, verification_command
        FROM plan_acceptance_criteria
        WHERE verification_command IS NOT NULL
          AND trim(verification_command) != ''
        ORDER BY criterion_id
        """
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    for criterion_id, verification_command in rows:
        reason = unsafe_verification_command_reason(verification_command)
        if reason is not None:
            failures.append(
                PlanningIntegrityFailure(
                    "acceptance_criterion_verification_command",
                    (
                        f"{criterion_id}.verification_command is unsafe: "
                        f"{verification_command} ({reason})"
                    ),
                )
            )
    return tuple(failures)


def _check_plan_artifact_paths_are_repo_local(
    connection: sqlite3.Connection,
    repo_root: Path,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT 'plan_artifact_links' AS source, artifact_id AS artifact_id
        FROM plan_artifact_links
        UNION ALL
        SELECT 'plan_progress_events' AS source, linked_artifact_id AS artifact_id
        FROM plan_progress_events
        WHERE linked_artifact_id IS NOT NULL
        ORDER BY source, artifact_id
        """
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    for source, artifact_id in rows:
        reason = unsafe_repo_relative_path_patterns((artifact_id,))
        if reason:
            failures.append(
                PlanningIntegrityFailure(
                    "planning_artifact_path",
                    f"{source} uses unsafe artifact path {artifact_id}: {reason[0]}",
                )
            )
            continue
        if _artifact_path(repo_root, str(artifact_id)) is None:
            failures.append(
                PlanningIntegrityFailure(
                    "planning_artifact_path",
                    f"{source} uses non-local artifact path {artifact_id}",
                )
            )
    return tuple(failures)


def _check_json_column_type(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    expected_type: type[object],
) -> tuple[PlanningIntegrityFailure, ...]:
    failures: list[PlanningIntegrityFailure] = []
    rowid_column = _rowid_column(table)
    rows = connection.execute(f"SELECT {rowid_column}, {column} FROM {table}").fetchall()
    for row_id, raw_value in rows:
        try:
            value = json.loads(str(raw_value))
        except json.JSONDecodeError as exc:
            failures.append(
                PlanningIntegrityFailure(
                    "invalid_json",
                    f"{table}.{column} on {row_id}: {exc.msg}",
                )
            )
            continue
        if not isinstance(value, expected_type):
            failures.append(
                PlanningIntegrityFailure(
                    "unexpected_json_type",
                    f"{table}.{column} on {row_id}: expected {expected_type.__name__}",
                )
            )
    return tuple(failures)


def _check_plan_commit_links_are_full_shas(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT plan_id, commit_sha, relationship
        FROM plan_commit_links
        ORDER BY plan_id, commit_sha, relationship
        """
    ).fetchall()
    return tuple(
        PlanningIntegrityFailure(
            "plan_commit_link_not_full_sha",
            f"{plan_id} {relationship}: {commit_sha}",
        )
        for plan_id, commit_sha, relationship in rows
        if FULL_COMMIT_SHA_PATTERN.fullmatch(str(commit_sha)) is None
    )


def _check_plan_commit_links_exist_in_git(
    connection: sqlite3.Connection,
    repo_root: Path,
) -> tuple[PlanningIntegrityFailure, ...]:
    if not _repo_has_git_metadata(repo_root):
        return ()
    rows = connection.execute(
        """
        SELECT plan_id, commit_sha, relationship
        FROM plan_commit_links
        ORDER BY plan_id, commit_sha, relationship
        """
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    for plan_id, commit_sha, relationship in rows:
        sha = str(commit_sha)
        if FULL_COMMIT_SHA_PATTERN.fullmatch(sha) is None:
            continue
        completed = subprocess.run(
            ("git", "-C", str(repo_root), "cat-file", "-e", f"{sha}^{{commit}}"),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if completed.returncode != 0:
            failures.append(
                PlanningIntegrityFailure(
                    "plan_commit_link_missing_git_commit",
                    f"{plan_id} {relationship}: {sha}",
                )
            )
    return tuple(failures)


def _repo_has_git_metadata(repo_root: Path) -> bool:
    return (repo_root / ".git").exists()


def _rowid_column(table: str) -> str:
    return {
        "plans": "plan_id",
        "plan_milestones": "milestone_id",
        "supervisor_tasks": "task_id",
        "worker_runs": "worker_run_id",
    }[table]


def _check_current_queue_plans_have_operational_structure(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    checks = (
        (
            "current_queue_plan_without_milestone",
            "plan_milestones",
        ),
        (
            "current_queue_plan_without_acceptance_criterion",
            "plan_acceptance_criteria",
        ),
        (
            "current_queue_plan_without_task",
            "supervisor_tasks",
        ),
    )
    placeholders = ", ".join("?" for _ in CURRENT_QUEUE_PLAN_STATUSES)
    failures: list[PlanningIntegrityFailure] = []
    for check_name, table in checks:
        rows = connection.execute(
            f"""
            SELECT p.plan_id
            FROM plans p
            WHERE p.status IN ({placeholders})
              AND NOT EXISTS (
                  SELECT 1 FROM {table} child
                  WHERE child.plan_id = p.plan_id
              )
            ORDER BY p.plan_id
            """,
            tuple(sorted(CURRENT_QUEUE_PLAN_STATUSES)),
        ).fetchall()
        failures.extend(PlanningIntegrityFailure(check_name, str(plan_id)) for (plan_id,) in rows)
    return tuple(failures)


def _check_completed_plans_have_completed_criteria(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    placeholders = ", ".join("?" for _ in OPEN_CRITERION_STATUSES)
    rows = connection.execute(
        f"""
        SELECT ac.criterion_id, ac.plan_id, ac.status
        FROM plan_acceptance_criteria ac
        JOIN plans p ON p.plan_id = ac.plan_id
        WHERE p.status = 'completed'
          AND ac.status IN ({placeholders})
        ORDER BY ac.plan_id, ac.criterion_id
        """,
        tuple(sorted(OPEN_CRITERION_STATUSES)),
    ).fetchall()
    return tuple(
        PlanningIntegrityFailure(
            "completed_plan_has_incomplete_criterion",
            f"{criterion_id} on {plan_id} is {status}",
        )
        for criterion_id, plan_id, status in rows
    )


def _check_completed_worker_runs_have_result_paths(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT worker_run_id
        FROM worker_runs
        WHERE status = 'completed'
          AND (result_path IS NULL OR trim(result_path) = '')
        ORDER BY worker_run_id
        """
    ).fetchall()
    return tuple(
        PlanningIntegrityFailure(
            "completed_worker_run_without_result_path",
            str(worker_run_id),
        )
        for (worker_run_id,) in rows
    )


def _check_completed_afk_tasks_have_worker_evidence(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT st.task_id, st.plan_id
        FROM supervisor_tasks st
        JOIN plans p ON p.plan_id = st.plan_id
        WHERE st.task_type = 'AFK'
          AND st.status = 'completed'
          AND NOT EXISTS (
              SELECT 1
              FROM worker_runs wr
              WHERE wr.task_id = st.task_id
                AND wr.status = 'completed'
                AND wr.result_path IS NOT NULL
                AND trim(wr.result_path) != ''
        )
        ORDER BY st.task_id
        """
    ).fetchall()
    return tuple(
        PlanningIntegrityFailure(
            "completed_afk_task_without_worker_evidence",
            f"{task_id} on plan {plan_id}",
        )
        for task_id, plan_id in rows
    )


def _check_completed_worker_run_results_exist(
    connection: sqlite3.Connection,
    repo_root: Path,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT worker_run_id, result_path
        FROM worker_runs
        WHERE status = 'completed'
          AND result_path IS NOT NULL
          AND trim(result_path) != ''
        ORDER BY worker_run_id
        """
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    for worker_run_id, result_path in rows:
        path = _artifact_path(repo_root, str(result_path))
        if path is None:
            continue
        if not path.exists():
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_result_missing_on_disk",
                    f"{worker_run_id}: {result_path}",
                )
            )
    return tuple(failures)


def _check_completed_worker_result_paths_are_local_json(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT worker_run_id, result_path
        FROM worker_runs
        WHERE status = 'completed'
          AND result_path IS NOT NULL
          AND trim(result_path) != ''
        ORDER BY worker_run_id
        """
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    for worker_run_id, result_path in rows:
        reason = unsafe_worker_result_path_reason(result_path)
        if reason is not None:
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_result_not_repo_local_json",
                    f"{worker_run_id}: {reason}",
                )
            )
    return tuple(failures)


def _check_completed_worker_json_results(
    connection: sqlite3.Connection,
    repo_root: Path,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT
            wr.worker_run_id,
            wr.result_path,
            st.verification_commands_json,
            st.acceptance_criteria_json,
            st.allowed_paths_json
        FROM worker_runs wr
        JOIN supervisor_tasks st ON st.task_id = wr.task_id
        WHERE wr.status = 'completed'
          AND wr.result_path IS NOT NULL
          AND trim(wr.result_path) != ''
        ORDER BY wr.worker_run_id
        """
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    completed_worker_result_paths = {
        str(worker_run_id): _normalize_repo_path(str(result_path))
        for worker_run_id, result_path, *_ in rows
    }
    for worker_run_id, result_path, verification_json, acceptance_json, allowed_paths_json in rows:
        path = _artifact_path(repo_root, str(result_path))
        if path is None or path.suffix.lower() != ".json" or not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_json_result",
                    f"{worker_run_id}: {exc.msg}",
                )
            )
            continue
        if not isinstance(payload, dict):
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_json_result",
                    f"{worker_run_id}: expected JSON object",
                )
            )
            continue
        failures.extend(_worker_result_type_failures(str(worker_run_id), payload))
        missing = sorted(WORKER_RESULT_REQUIRED_KEYS - set(payload))
        if missing:
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: missing {', '.join(missing)}",
                )
            )
            continue
        if payload.get("status") != "completed":
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: completed worker run result status must be 'completed'",
                )
            )
        failures.extend(_completed_worker_result_identity_failures(str(worker_run_id), payload))
        failures.extend(
            _completed_worker_result_shared_identity_failures(
                str(worker_run_id),
                str(result_path),
                payload,
                completed_worker_result_paths,
            )
        )
        failures.extend(_completed_worker_result_evidence_failures(str(worker_run_id), payload))
        failures.extend(_completed_worker_result_test_run_failures(str(worker_run_id), payload))
        failures.extend(
            _completed_worker_result_artifact_reference_failures(
                str(worker_run_id),
                str(result_path),
                payload,
            )
        )
        failures.extend(
            _completed_worker_result_path_failures(str(worker_run_id), payload, repo_root)
        )
        failures.extend(
            _completed_worker_result_allowed_path_failures(
                str(worker_run_id),
                payload,
                str(allowed_paths_json),
            )
        )
        failures.extend(
            _completed_worker_result_task_alignment_failures(
                str(worker_run_id),
                payload,
                str(verification_json),
                str(acceptance_json),
            )
        )
    return tuple(failures)


def _worker_result_type_failures(
    worker_run_id: str,
    payload: dict[object, object],
) -> tuple[PlanningIntegrityFailure, ...]:
    expected_types: dict[str, type[object]] = {
        "worker_run_id": str,
        "worker_run_ids": list,
        "status": str,
        "summary": str,
        "changed_files": list,
        "tests_run": list,
        "acceptance_results": dict,
        "risks": list,
        "follow_up_tasks": list,
        "artifacts": list,
        "handoff_notes": str,
    }
    failures: list[PlanningIntegrityFailure] = []
    for key, expected_type in expected_types.items():
        if key not in payload:
            continue
        if not isinstance(payload[key], expected_type):
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: {key} must be {expected_type.__name__}",
                )
            )
    return tuple(failures)


def _completed_worker_result_identity_failures(
    worker_run_id: str,
    payload: dict[object, object],
) -> tuple[PlanningIntegrityFailure, ...]:
    if "worker_run_id" not in payload and "worker_run_ids" not in payload:
        return (
            PlanningIntegrityFailure(
                "completed_worker_run_invalid_result_schema",
                f"{worker_run_id}: result must declare worker_run_id or worker_run_ids",
            ),
        )

    failures: list[PlanningIntegrityFailure] = []
    single_worker_run_id = payload.get("worker_run_id")
    if single_worker_run_id is not None and single_worker_run_id != worker_run_id:
        failures.append(
            PlanningIntegrityFailure(
                "completed_worker_run_invalid_result_schema",
                f"{worker_run_id}: worker_run_id points at {single_worker_run_id!r}",
            )
        )

    worker_run_ids = payload.get("worker_run_ids")
    if worker_run_ids is not None:
        if not isinstance(worker_run_ids, list):
            return tuple(failures)
        if not worker_run_ids:
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: worker_run_ids must be nonempty",
                )
            )
        invalid_values = [
            value for value in worker_run_ids if not isinstance(value, str) or not value.strip()
        ]
        if invalid_values:
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: worker_run_ids entries must be nonblank strings",
                )
            )
        elif worker_run_id not in worker_run_ids:
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: worker_run_ids does not cover this run",
                )
            )

    return tuple(failures)


def _completed_worker_result_shared_identity_failures(
    worker_run_id: str,
    result_path: str,
    payload: dict[object, object],
    completed_worker_result_paths: dict[str, str],
) -> tuple[PlanningIntegrityFailure, ...]:
    worker_run_ids = payload.get("worker_run_ids")
    if not isinstance(worker_run_ids, list):
        return ()

    normalized_result_path = _normalize_repo_path(result_path)
    failures: list[PlanningIntegrityFailure] = []
    for value in worker_run_ids:
        if not isinstance(value, str) or not value.strip():
            continue
        declared_worker_run_id = value.strip()
        declared_result_path = completed_worker_result_paths.get(declared_worker_run_id)
        if declared_result_path == normalized_result_path:
            continue
        if declared_result_path is None:
            reason = (
                f"{worker_run_id}: worker_run_ids entry {declared_worker_run_id!r} does not "
                "match a completed worker run for this result_path"
            )
        else:
            reason = (
                f"{worker_run_id}: worker_run_ids entry {declared_worker_run_id!r} points at "
                f"{declared_result_path}, not {normalized_result_path}"
            )
        failures.append(
            PlanningIntegrityFailure(
                "completed_worker_run_invalid_result_schema",
                reason,
            )
        )
    return tuple(failures)


def _completed_worker_result_evidence_failures(
    worker_run_id: str,
    payload: dict[object, object],
) -> tuple[PlanningIntegrityFailure, ...]:
    if payload.get("status") != "completed":
        return ()
    evidence_fields = ("changed_files", "artifacts")
    failures: list[PlanningIntegrityFailure] = []
    for key in evidence_fields:
        value = payload.get(key)
        if not isinstance(value, list):
            continue
        if not _has_nonblank_string(value):
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: completed result requires nonempty {key}",
                )
            )
    tests_run = payload.get("tests_run")
    if isinstance(tests_run, list) and not tests_run:
        failures.append(
            PlanningIntegrityFailure(
                "completed_worker_run_invalid_result_schema",
                f"{worker_run_id}: completed result requires nonempty tests_run",
            )
        )
    acceptance_results = payload.get("acceptance_results")
    if isinstance(acceptance_results, dict) and not acceptance_results:
        failures.append(
            PlanningIntegrityFailure(
                "completed_worker_run_invalid_result_schema",
                f"{worker_run_id}: completed result requires acceptance_results evidence",
            )
        )
    for key in ("summary", "handoff_notes"):
        value = payload.get(key)
        if isinstance(value, str) and not value.strip():
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: {key} must be nonblank",
                )
            )
    return tuple(failures)


def _completed_worker_result_test_run_failures(
    worker_run_id: str,
    payload: dict[object, object],
) -> tuple[PlanningIntegrityFailure, ...]:
    tests_run = payload.get("tests_run")
    if not isinstance(tests_run, list):
        return ()
    failures: list[PlanningIntegrityFailure] = []
    if not tests_run:
        return ()
    for index, value in enumerate(tests_run):
        if not isinstance(value, dict):
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: tests_run[{index}] must be an object",
                )
            )
            continue
        command = value.get("command")
        exit_code = value.get("exit_code")
        summary = value.get("summary")
        if not isinstance(command, str) or not command.strip():
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: tests_run[{index}].command must be nonblank",
                )
            )
        else:
            reason = unsafe_verification_command_reason(command)
            if reason is not None:
                failures.append(
                    PlanningIntegrityFailure(
                        "completed_worker_run_invalid_result_schema",
                        f"{worker_run_id}: tests_run[{index}].command is unsafe: {reason}",
                    )
                )
        if not isinstance(exit_code, int):
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: tests_run[{index}].exit_code must be an integer",
                )
            )
        elif exit_code != 0:
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: tests_run[{index}] exit_code is {exit_code}",
                )
            )
        if not isinstance(summary, str) or not summary.strip():
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: tests_run[{index}].summary must be nonblank",
                )
            )
        elif _contains_stale_test_summary_phrase(summary):
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: tests_run[{index}].summary uses stale evidence phrasing",
                )
            )
    return tuple(failures)


def _contains_stale_test_summary_phrase(value: str) -> bool:
    normalized = value.lower()
    return any(phrase in normalized for phrase in STALE_TEST_SUMMARY_PHRASES)


def _completed_worker_result_artifact_reference_failures(
    worker_run_id: str,
    result_path: str,
    payload: dict[object, object],
) -> tuple[PlanningIntegrityFailure, ...]:
    normalized_result_path = _normalize_repo_path(result_path)
    failures: list[PlanningIntegrityFailure] = []
    values = payload.get("artifacts")
    if isinstance(values, list):
        normalized_values = {
            value.strip().replace("\\", "/")
            for value in values
            if isinstance(value, str) and value.strip()
        }
        if normalized_result_path not in normalized_values:
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: artifacts must include result_path {normalized_result_path}",
                )
            )
    return tuple(failures)


def _normalize_repo_path(value: str) -> str:
    return value.strip().replace("\\", "/")


def _worker_result_entry_path_reason(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return "path entry must be a nonblank string"
    failures = unsafe_repo_relative_path_patterns((value.strip(),))
    if failures:
        return failures[0]
    return None


def _completed_worker_result_path_failures(
    worker_run_id: str,
    payload: dict[object, object],
    repo_root: Path,
) -> tuple[PlanningIntegrityFailure, ...]:
    failures: list[PlanningIntegrityFailure] = []
    for key in ("changed_files", "artifacts"):
        values = payload.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            reason = _worker_result_entry_path_reason(value)
            if reason is not None:
                failures.append(
                    PlanningIntegrityFailure(
                        "completed_worker_run_invalid_result_schema",
                        f"{worker_run_id}: {key} entry is unsafe: {value} ({reason})",
                    )
                )
                continue
            path = _artifact_path(repo_root, str(value))
            if path is None:
                failures.append(
                    PlanningIntegrityFailure(
                        "completed_worker_run_invalid_result_schema",
                        f"{worker_run_id}: {key} entry is not repo-local: {value}",
                    )
                )
                continue
            if not path.exists():
                failures.append(
                    PlanningIntegrityFailure(
                        "completed_worker_run_invalid_result_schema",
                        f"{worker_run_id}: {key} entry does not exist: {value}",
                    )
                )
    return tuple(failures)


def _completed_worker_result_allowed_path_failures(
    worker_run_id: str,
    payload: dict[object, object],
    allowed_paths_json: str,
) -> tuple[PlanningIntegrityFailure, ...]:
    allowed_patterns = _json_string_array(allowed_paths_json)
    if not allowed_patterns:
        return ()
    changed_files = payload.get("changed_files")
    if not isinstance(changed_files, list):
        return ()
    failures: list[PlanningIntegrityFailure] = []
    for value in changed_files:
        reason = _worker_result_entry_path_reason(value)
        if reason is not None:
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: changed_files entry is unsafe: {value} ({reason})",
                )
            )
            continue
        normalized = value.strip().replace("\\", "/")
        if not any(
            fnmatchcase(normalized, pattern.replace("\\", "/")) for pattern in allowed_patterns
        ):
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_changed_file_outside_allowed_paths",
                    f"{worker_run_id}: {value} not covered by allowed_paths",
                )
            )
    return tuple(failures)


def _completed_worker_result_task_alignment_failures(
    worker_run_id: str,
    payload: dict[object, object],
    verification_json: str,
    acceptance_json: str,
) -> tuple[PlanningIntegrityFailure, ...]:
    failures: list[PlanningIntegrityFailure] = []
    tests_run = payload.get("tests_run")
    if isinstance(tests_run, list):
        tests_run_set = {
            command
            for value in tests_run
            if isinstance(value, dict)
            for command in (value.get("command"),)
            if isinstance(command, str) and command.strip()
        }
        for command in _json_string_array(verification_json):
            reason = unsafe_verification_command_reason(command)
            if reason is not None:
                failures.append(
                    PlanningIntegrityFailure(
                        "completed_worker_run_invalid_result_schema",
                        f"{worker_run_id}: task verification_commands is unsafe: {reason}",
                    )
                )
            if command not in tests_run_set:
                failures.append(
                    PlanningIntegrityFailure(
                        "completed_worker_run_invalid_result_schema",
                        f"{worker_run_id}: tests_run missing task verification command {command}",
                    )
                )
    acceptance_results = payload.get("acceptance_results")
    if isinstance(acceptance_results, dict):
        criteria = _json_string_array(acceptance_json)
        for criterion in criteria:
            result = acceptance_results.get(criterion)
            if not _acceptance_result_passes(result):
                failures.append(
                    PlanningIntegrityFailure(
                        "completed_worker_run_invalid_result_schema",
                        (
                            f"{worker_run_id}: acceptance_results missing passing evidence for "
                            f"{criterion}"
                        ),
                    )
                )
        if criteria and len(acceptance_results) < len(criteria):
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: acceptance_results does not cover all task criteria",
                )
            )
    return tuple(failures)


def _acceptance_result_passes(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    status = value.get("status")
    evidence = value.get("evidence")
    return (
        isinstance(status, str)
        and status.lower() in {"passed", "verified", "completed"}
        and isinstance(evidence, str)
        and bool(evidence.strip())
    )


def _has_nonblank_string(values: list[object]) -> bool:
    return any(isinstance(value, str) and value.strip() for value in values)


def _check_completed_worker_runs_are_linked(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT wr.worker_run_id, st.plan_id, wr.result_path
        FROM worker_runs wr
        JOIN supervisor_tasks st ON st.task_id = wr.task_id
        WHERE wr.status = 'completed'
          AND wr.result_path IS NOT NULL
          AND trim(wr.result_path) != ''
          AND NOT EXISTS (
              SELECT 1 FROM plan_artifact_links pa
              WHERE pa.plan_id = st.plan_id
                AND pa.artifact_id = wr.result_path
                AND pa.relationship = 'worker-result'
          )
        ORDER BY wr.worker_run_id
        """
    ).fetchall()
    return tuple(
        PlanningIntegrityFailure(
            "completed_worker_run_result_not_linked",
            f"{worker_run_id} on {plan_id} links {result_path}",
        )
        for worker_run_id, plan_id, result_path in rows
    )


def _artifact_path(repo_root: Path, artifact_id: str) -> Path | None:
    value = artifact_id.split("#", 1)[0].replace("\\", "/").strip()
    if not value:
        return None
    if re.match(r"^[a-z][a-z0-9+.-]*://", value, flags=re.IGNORECASE):
        return None
    if re.match(r"^[A-Za-z]:", value):
        return None
    path = Path(value)
    if path.is_absolute():
        return None
    resolved = (repo_root / path).resolve()
    repo_resolved = repo_root.resolve()
    try:
        resolved.relative_to(repo_resolved)
    except ValueError:
        return None
    return resolved


def _check_open_afk_tasks_have_execution_contracts(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        f"""
        SELECT st.task_id
        FROM supervisor_tasks st
        JOIN plans p ON p.plan_id = st.plan_id
        WHERE p.status IN ({", ".join("?" for _ in CONTRACT_PLAN_STATUSES)})
          AND st.task_type = 'AFK'
          AND st.status IN ({", ".join("?" for _ in CONTRACT_TASK_STATUSES)})
          AND (
              st.acceptance_criteria_json = '[]'
              OR st.verification_commands_json = '[]'
              OR st.allowed_paths_json = '[]'
        )
        ORDER BY st.task_id
        """,
        (*CONTRACT_PLAN_STATUSES, *CONTRACT_TASK_STATUSES),
    ).fetchall()
    return tuple(
        PlanningIntegrityFailure(
            "open_afk_task_missing_execution_contract",
            str(task_id),
        )
        for (task_id,) in rows
    )


def _check_open_afk_task_contract_values(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        f"""
        SELECT
            st.task_id,
            st.acceptance_criteria_json,
            st.verification_commands_json,
            st.allowed_paths_json
        FROM supervisor_tasks st
        JOIN plans p ON p.plan_id = st.plan_id
        WHERE p.status IN ({", ".join("?" for _ in CONTRACT_PLAN_STATUSES)})
          AND st.task_type = 'AFK'
          AND st.status IN ({", ".join("?" for _ in CONTRACT_TASK_STATUSES)})
        ORDER BY st.task_id
        """,
        (*CONTRACT_PLAN_STATUSES, *CONTRACT_TASK_STATUSES),
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    for task_id, acceptance_json, verification_json, paths_json in rows:
        contract_fields = {
            "acceptance_criteria": acceptance_json,
            "verification_commands": verification_json,
            "allowed_paths": paths_json,
        }
        for field_name, raw_value in contract_fields.items():
            try:
                values = json.loads(str(raw_value))
            except json.JSONDecodeError:
                continue
            if not isinstance(values, list):
                continue
            if not any(isinstance(value, str) and value.strip() for value in values):
                failures.append(
                    PlanningIntegrityFailure(
                        "open_afk_task_invalid_execution_contract",
                        f"{task_id}.{field_name} has no nonblank string values",
                    )
                )
        try:
            allowed_paths = json.loads(str(paths_json))
        except json.JSONDecodeError:
            allowed_paths = []
        if isinstance(allowed_paths, list):
            for failure in unsafe_repo_relative_path_patterns(allowed_paths):
                failures.append(
                    PlanningIntegrityFailure(
                        "open_afk_task_invalid_execution_contract",
                        f"{task_id}.allowed_paths is unsafe: {failure}",
                    )
                )
        try:
            verification_commands = json.loads(str(verification_json))
        except json.JSONDecodeError:
            verification_commands = []
        if isinstance(verification_commands, list):
            for command in verification_commands:
                if not isinstance(command, str) or not command.strip():
                    continue
                reason = unsafe_verification_command_reason(command)
                if reason:
                    failures.append(
                        PlanningIntegrityFailure(
                            "open_afk_task_invalid_execution_contract",
                            f"{task_id}.verification_commands is unsafe: {command} ({reason})",
                        )
                    )
    return tuple(failures)


def _json_string_array(raw_value: str) -> tuple[str, ...]:
    try:
        values = json.loads(raw_value)
    except json.JSONDecodeError:
        return ()
    if not isinstance(values, list):
        return ()
    return tuple(value.strip() for value in values if isinstance(value, str) and value.strip())


def _check_progress_links_are_declared(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT pp.progress_id, pp.plan_id, pp.linked_artifact_id
        FROM plan_progress_events pp
        WHERE pp.linked_artifact_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM plan_artifact_links pa
              WHERE pa.plan_id = pp.plan_id
                AND pa.artifact_id = pp.linked_artifact_id
          )
        ORDER BY pp.plan_id, pp.progress_id
        """
    ).fetchall()
    return tuple(
        PlanningIntegrityFailure(
            "progress_link_missing_artifact_link",
            f"{progress_id} on {plan_id} links {artifact_id}",
        )
        for progress_id, plan_id, artifact_id in rows
    )


def _check_plan_timestamps_cover_progress(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT p.plan_id
        FROM plans p
        WHERE EXISTS (
            SELECT 1 FROM plan_progress_events pp
            WHERE pp.plan_id = p.plan_id
              AND pp.occurred_at > p.updated_at
        )
        ORDER BY p.plan_id
        """
    ).fetchall()
    return tuple(
        PlanningIntegrityFailure(
            "plan_updated_at_trails_progress",
            str(plan_id),
        )
        for (plan_id,) in rows
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=None)
    args = parser.parse_args(argv)

    db_path = args.path or default_planning_database_path()
    failures = check_planning_integrity(db_path)
    if failures:
        print("Planning integrity checks failed.", file=sys.stderr)
        for failure in failures:
            print(f"- {failure.check_name}: {failure.reason}", file=sys.stderr)
        return 1
    print("Planning integrity checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
