#!/usr/bin/env python3
"""Fail on planning SQLite drift that can mislead fresh Codex threads."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import sqlite3
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from codex_supervisor.evidence_vocabulary import (  # noqa: E402
        BROWSER_SMOKE_PASSED_EVENT,
        FINAL_STATE_COMMIT_RELATIONSHIPS,
        PROMOTION_COMPLETED_EVENT,
        REVIEW_ENFORCEMENT_ENABLED_EVENT,
        REVIEW_RESULT_RECORDED_EVENT,
        WORKER_EVIDENCE_MANIFEST_ARTIFACT_RELATIONSHIP,
        WORKER_RESULT_ARTIFACT_RELATIONSHIP,
        WORKER_RESULT_NORMALIZED_ARTIFACT_RELATIONSHIP,
    )
    from codex_supervisor.execution_surface import canonical_worker_backend  # noqa: E402
    from codex_supervisor.paths import default_planning_database_path  # noqa: E402
    from codex_supervisor.planning import (  # noqa: E402
        CRITERION_STATUSES,
        CURRENT_QUEUE_PLAN_STATUSES,
        MILESTONE_STATUSES,
        NONTERMINAL_WORKER_RUN_STATUSES,
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
    from codex_supervisor.task_policy import (  # noqa: E402
        controller_owned_allowed_path_violations,
        task_uses_controller_worker_profile,
    )
    from codex_supervisor.worker_results import (  # noqa: E402
        STALE_COMPLETED_RESULT_BLOCKER_PHRASES,
    )
except ModuleNotFoundError:
    BROWSER_SMOKE_PASSED_EVENT = "browser_smoke_passed"
    FINAL_STATE_COMMIT_RELATIONSHIPS = ("final-project-state", "final-state", "completion")
    PROMOTION_COMPLETED_EVENT = "promotion_completed"
    REVIEW_ENFORCEMENT_ENABLED_EVENT = "review_enforcement_enabled"
    REVIEW_RESULT_RECORDED_EVENT = "review_result_recorded"
    WORKER_EVIDENCE_MANIFEST_ARTIFACT_RELATIONSHIP = "worker-evidence-manifest"
    WORKER_RESULT_ARTIFACT_RELATIONSHIP = "worker-result"
    WORKER_RESULT_NORMALIZED_ARTIFACT_RELATIONSHIP = "worker-result-normalized"
    STALE_COMPLETED_RESULT_BLOCKER_PHRASES = (
        "remains blocked",
        "still blocked",
        "is blocked by",
        "broad supervisor gate is blocked",
        "verification remains blocked",
        "should repair planning",
        "create the required separate afk review task",
    )

    def canonical_worker_backend(worker_backend: str) -> str:
        return (
            "codex_exec" if worker_backend in {"codex_exec", "live_codex_exec"} else worker_backend
        )

    def controller_owned_allowed_path_violations(
        allowed_paths: Iterable[object],
        *,
        scope: object,
        worker_backend: str = "codex_exec",
    ) -> tuple[str, ...]:
        protected_docs = {
            ".gitignore",
            ".gitattributes",
            "README.md",
            "AGENTS.md",
            "PLANS.md",
            "ARCHITECTURE.md",
            "CONTRACTS.md",
            "ROADMAP.md",
            "SOP.md",
            "TESTING.md",
            "DECISIONS.md",
            "LICENSE",
            "ATTRIBUTIONS.md",
        }
        parsed_scope = scope if isinstance(scope, dict) else {}
        if parsed_scope.get("controller_mutation_kind") in {
            "controller",
            "planning",
            "promotion",
            "source_lock",
        }:
            return ()
        legacy_role = None
        role = parsed_scope.get("task_role", parsed_scope.get("worker_role"))
        if parsed_scope.get("controller_task") is True:
            legacy_role = "controller_task"
        elif role in {"controller", "planning", "promotion", "source_lock"}:
            legacy_role = f"task_role={role}"
        violations: list[str] = []
        forbidden = tuple(
            item.strip().replace("\\", "/")
            for item in parsed_scope.get("worker_must_not_edit", [])
            if isinstance(item, str) and item.strip()
        )
        for value in allowed_paths:
            if not isinstance(value, str):
                continue
            normalized = value.strip().replace("\\", "/")
            if normalized in forbidden:
                violations.append(
                    f"{normalized}: allowed path overlaps worker_must_not_edit `{normalized}`"
                )
            if normalized in {
                "plans/planning.sqlite3",
                "HANDOFF.md",
                "scripts/**",
                "scripts/check_file_justification.py",
                "scripts/check_planning_integrity.py",
                "scripts/check_protected_files.py",
                "scripts/print_protected_hashes.py",
                "scripts/verify.py",
            }:
                if legacy_role is not None:
                    violations.append(
                        f"{legacy_role}: legacy controller role is ignored without "
                        "controller_mutation_kind"
                    )
                violations.append(f"{normalized}: controller-owned path")
                continue
            if normalized in protected_docs:
                if legacy_role is not None:
                    violations.append(
                        f"{legacy_role}: legacy controller role is ignored without "
                        "controller_mutation_kind"
                    )
                violations.append(f"{normalized}: protected source-of-truth doc")
                continue
            if normalized == ".agents/**" or normalized.startswith(".agents/"):
                if legacy_role is not None:
                    violations.append(
                        f"{legacy_role}: legacy controller role is ignored without "
                        "controller_mutation_kind"
                    )
                violations.append(f"{normalized}: controller-owned path")
        return tuple(dict.fromkeys(violations))

    def task_uses_controller_worker_profile(scope: object) -> bool:
        parsed_scope = scope if isinstance(scope, dict) else {}
        return parsed_scope.get("controller_mutation_kind") in {
            "controller",
            "planning",
            "promotion",
            "source_lock",
        }

    PLAN_STATUSES = frozenset({"active", "blocked", "completed", "abandoned", "superseded"})
    CURRENT_QUEUE_PLAN_STATUSES = frozenset({"active", "blocked"})
    MILESTONE_STATUSES = frozenset({"pending", "active", "blocked", "completed", "cancelled"})
    CRITERION_STATUSES = frozenset({"pending", "blocked", "completed", "failed", "cancelled"})
    TASK_STATUSES = frozenset(
        {"pending", "ready", "running", "blocked", "reviewing", "completed", "failed", "cancelled"}
    )
    OPEN_TASK_STATUSES = TASK_STATUSES - {"completed", "failed", "cancelled"}
    TASK_STATUSES_ALLOWED_WITH_NONTERMINAL_WORKER_RUN = frozenset(
        {"running", "blocked", "reviewing"}
    )
    WORKER_RUN_STATUSES = frozenset(
        {"queued", "running", "blocked", "completed", "failed", "cancelled", "needs_review"}
    )
    NONTERMINAL_WORKER_RUN_STATUSES = WORKER_RUN_STATUSES - {
        "completed",
        "failed",
        "cancelled",
    }
    DRIVE_PATH_PATTERN = re.compile(r"^[A-Za-z]:")
    NPM_WORKSPACE_VALUE_PATTERN = re.compile(r"^[A-Za-z0-9_.@/-]+$")
    UV_RUN_READONLY_PREFIX = ("uv", "run", "--no-sync")
    SHELL_METACHARACTERS = ("|", "&", ";", "<", ">", "`", "$(")

    def default_planning_database_path(repo_root: Path | None = None) -> Path:
        root = repo_root or REPO_ROOT
        return root / "plans" / "planning.sqlite3"

    def open_existing_planning_database(  # type: ignore[misc]
        path: Path,
        *,
        read_only: bool = False,
        validate: bool = False,
    ) -> Any:
        if not path.exists():
            msg = f"missing database: {path}"
            raise ValueError(msg)
        return None

    def unsafe_repo_relative_path_patterns(values: Iterable[object]) -> tuple[str, ...]:
        failures: list[str] = []
        for value in values:
            if not isinstance(value, str) or not value.strip():
                continue
            raw_value = value.strip()
            normalized = raw_value.replace("\\", "/")
            if re.match(r"^[a-z][a-z0-9+.-]*://", normalized, flags=re.IGNORECASE):
                failures.append(f"{raw_value}: URLs are not repo-local paths")
                continue
            if normalized.startswith("/") or normalized.startswith("//"):
                failures.append(f"{raw_value}: absolute paths are not allowed")
                continue
            if DRIVE_PATH_PATTERN.match(raw_value):
                failures.append(f"{raw_value}: drive-qualified paths are not allowed")
                continue
            if ":" in normalized:
                failures.append(f"{raw_value}: colons are not allowed")
                continue
            parts = tuple(normalized.split("/"))
            if any(part == "" for part in parts):
                failures.append(f"{raw_value}: empty path segments are not allowed")
                continue
            if any(part == "." for part in parts):
                failures.append(f"{raw_value}: current-directory segments are not allowed")
                continue
            if any(part == ".." for part in parts):
                failures.append(f"{raw_value}: parent traversal is not allowed")
        return tuple(failures)

    def unsafe_worker_result_path_reason(value: object) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return "result_path must be a nonblank string"
        raw_value = value.strip()
        failures = unsafe_repo_relative_path_patterns((raw_value,))
        if failures:
            return failures[0]
        if Path(raw_value.replace("\\", "/")).suffix.lower() != ".json":
            return "completed worker result_path must end with .json"
        return None

    def unsafe_verification_command_reason(command: object) -> str | None:
        if not isinstance(command, str):
            return "verification command must be a string"
        raw_command = command.strip()
        if any(fragment in raw_command for fragment in SHELL_METACHARACTERS):
            return "shell metacharacters and redirection are not allowed"
        try:
            tokens = tuple(shlex.split(raw_command))
        except ValueError as exc:
            return f"could not parse command: {exc}"
        if not tokens:
            return "empty command"
        if tokens[:3] == UV_RUN_READONLY_PREFIX:
            tokens = tokens[3:]
        if not tokens:
            return "verification is missing a command"
        if tokens[0] == "npm":
            return _fallback_npm_command_reason(tokens)
        if tokens[0] in {"python", "python3"}:
            return None if "-B" in tokens else "python verification must use -B"
        if tokens[0] in {"pytest", "ruff", "mypy"}:
            return None
        if tokens[:2] == ("git", "status") or tokens == ("git", "diff", "--check"):
            return None
        return "unsupported verification command shape"

    def _fallback_npm_command_reason(tokens: tuple[str, ...]) -> str | None:
        if tokens == ("npm", "test", "--workspaces", "--if-present"):
            return None
        if tokens == ("npm", "audit", "--omit=dev"):
            return None
        if (
            len(tokens) == 5
            and tokens[:3] == ("npm", "run", "build")
            and tokens[3] == "--workspace"
        ):
            workspace = tokens[4].replace("\\", "/")
            if workspace.startswith("/") or ".." in workspace.split("/"):
                return "npm workspace must be repo-local"
            if not NPM_WORKSPACE_VALUE_PATTERN.match(workspace):
                return "npm workspace must be a plain workspace name"
            return None
        return "npm verification is limited to approved read-only commands"


CONTRACT_PLAN_STATUSES = CURRENT_QUEUE_PLAN_STATUSES
CONTRACT_TASK_STATUSES = ("ready", "running", "blocked", "reviewing")
JSON_OBJECT_COLUMNS = (
    ("plans", "non_goals_json"),
    ("plans", "context_json"),
    ("plan_milestones", "details_json"),
    ("supervisor_tasks", "scope_json"),
    ("supervisor_tasks", "out_of_scope_json"),
    ("worker_runs", "metadata_json"),
    ("worker_result_records", "raw_payload_json"),
    ("worker_result_records", "acceptance_results_json"),
    ("worker_result_records", "metadata_json"),
    ("development_log_entries", "metadata_json"),
)
JSON_ARRAY_COLUMNS = (
    ("supervisor_tasks", "acceptance_criteria_json"),
    ("supervisor_tasks", "verification_commands_json"),
    ("supervisor_tasks", "allowed_paths_json"),
    ("supervisor_tasks", "blocked_by_json"),
    ("worker_result_records", "changed_files_json"),
    ("worker_result_records", "artifacts_json"),
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
    }
)
IGNORED_RUNTIME_ROOTS = frozenset({"artifacts", "logs", "runs", "worktrees"})
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
            failures.extend(
                _check_completed_publication_required_tasks_have_commit_links(connection)
            )
            failures.extend(_check_completed_product_worker_runs_have_commit_links(connection))
            failures.extend(_check_current_queue_plans_have_operational_structure(connection))
            failures.extend(_check_completed_plans_have_completed_criteria(connection))
            failures.extend(_check_completed_plans_have_no_open_tasks(connection))
            failures.extend(_check_nonterminal_worker_runs_match_task_state(connection))
            failures.extend(_check_nonterminal_codex_exec_runs_have_story_loop_evidence(connection))
            failures.extend(
                _check_stalled_codex_exec_runs_do_not_have_file_change_events(connection)
            )
            failures.extend(_check_open_afk_tasks_have_execution_contracts(connection))
            failures.extend(_check_open_afk_task_contract_values(connection))
            failures.extend(_check_open_codex_exec_tasks_avoid_controller_owned_paths(connection))
            failures.extend(_check_completed_worker_runs_have_result_records(connection))
            failures.extend(
                _check_completed_worker_runs_preserve_indexed_evidence(connection, repo_root)
            )
            failures.extend(
                _check_completed_worker_runs_do_not_hide_failed_controller_results(
                    connection,
                    repo_root,
                )
            )
            failures.extend(_check_completed_afk_tasks_have_worker_evidence(connection))
            failures.extend(_check_completed_codex_exec_tasks_have_review_posture(connection))
            failures.extend(_check_completed_promotion_tasks_have_progress(connection))
            failures.extend(_check_completed_review_required_tasks_have_review_evidence(connection))
            failures.extend(_check_review_required_promotions_have_review_evidence(connection))
            failures.extend(_check_worker_result_records_have_run_links(connection))
            failures.extend(_check_completed_worker_runs_have_artifact_links(connection))
            failures.extend(_check_worker_result_records_have_valid_payloads(connection, repo_root))
            failures.extend(_check_passed_browser_smoke_has_progress(connection))
            failures.extend(_check_worker_result_records_align_with_runs(connection))
            failures.extend(_check_worker_results_not_stored_as_public_files(connection, repo_root))
            failures.extend(_check_handoff_snapshot_is_compact(repo_root))
            failures.extend(_check_handoff_snapshot_matches_queue_state(connection, repo_root))
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


def _check_nonterminal_codex_exec_runs_have_story_loop_evidence(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        f"""
        SELECT wr.worker_run_id, wr.backend, wr.prompt_path, wr.jsonl_path, wr.metadata_json
        FROM worker_runs wr
        JOIN supervisor_tasks st ON st.task_id = wr.task_id
        JOIN plans p ON p.plan_id = st.plan_id
        WHERE wr.status IN ({", ".join("?" for _ in NONTERMINAL_WORKER_RUN_STATUSES)})
          AND p.status IN ({", ".join("?" for _ in CURRENT_QUEUE_PLAN_STATUSES)})
        ORDER BY wr.worker_run_id
        """,
        (*sorted(NONTERMINAL_WORKER_RUN_STATUSES), *CURRENT_QUEUE_PLAN_STATUSES),
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    for worker_run_id, backend, prompt_path, jsonl_path, metadata_json in rows:
        if canonical_worker_backend(str(backend)) != "codex_exec":
            continue
        metadata = _json_object(metadata_json)
        planned_evidence = metadata.get("planned_evidence_paths")
        runtime_preflight = metadata.get("runtime_preflight")
        missing: list[str] = []
        if not isinstance(runtime_preflight, dict):
            missing.append("runtime_preflight")
        elif runtime_preflight.get("worker_execution") != "codex_exec":
            missing.append("runtime_preflight.worker_execution=codex_exec")
        if not isinstance(planned_evidence, dict):
            missing.append("planned_evidence_paths")
        else:
            for key in ("worktree", "prompt", "liveness_probe", "jsonl", "raw_result"):
                value = planned_evidence.get(key)
                if not isinstance(value, str) or not value.strip():
                    missing.append(f"planned_evidence_paths.{key}")
        if not isinstance(prompt_path, str) or not prompt_path.strip():
            missing.append("prompt_path")
        if not isinstance(jsonl_path, str) or not jsonl_path.strip():
            missing.append("jsonl_path")
        if missing:
            failures.append(
                PlanningIntegrityFailure(
                    "nonterminal_codex_exec_run_without_story_loop_evidence",
                    f"{worker_run_id}: missing {', '.join(missing)}",
                )
            )
    return tuple(failures)


def _check_stalled_codex_exec_runs_do_not_have_file_change_events(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT wr.worker_run_id, wr.backend, wr.failure_class,
               COUNT(event.event_id) AS file_change_events
        FROM worker_runs wr
        JOIN worker_run_events event ON event.worker_run_id = wr.worker_run_id
        WHERE wr.status = 'failed'
          AND wr.failure_class LIKE 'worker_stalled%'
          AND event.event_type LIKE '%file_change%'
        GROUP BY wr.worker_run_id, wr.backend, wr.failure_class
        ORDER BY wr.worker_run_id
        """
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    for worker_run_id, backend, failure_class, file_change_events in rows:
        if canonical_worker_backend(str(backend)) != "codex_exec":
            continue
        failures.append(
            PlanningIntegrityFailure(
                "stalled_codex_exec_run_has_file_change_events",
                f"{worker_run_id}: {failure_class} conflicts with {file_change_events} "
                "file-change event(s)",
            )
        )
    return tuple(failures)


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


def _check_completed_publication_required_tasks_have_commit_links(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT st.task_id, st.plan_id, st.scope_json, p.context_json
        FROM supervisor_tasks st
        JOIN plans p ON p.plan_id = st.plan_id
        WHERE st.task_type = 'AFK'
          AND st.status = 'completed'
        ORDER BY st.plan_id, st.task_id
        """
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    relationship_placeholders = ", ".join("?" for _ in FINAL_STATE_COMMIT_RELATIONSHIPS)
    for task_id, plan_id, scope_json, context_json in rows:
        scope = _json_object(scope_json)
        context = _json_object(context_json)
        if not _requires_final_commit(scope, context):
            continue
        final_commit_link = connection.execute(
            f"""
            SELECT 1
            FROM plan_commit_links
            WHERE plan_id = ?
              AND relationship IN ({relationship_placeholders})
            LIMIT 1
            """,
            (plan_id, *FINAL_STATE_COMMIT_RELATIONSHIPS),
        ).fetchone()
        if final_commit_link is not None:
            continue
        any_commit_link = connection.execute(
            "SELECT 1 FROM plan_commit_links WHERE plan_id = ? LIMIT 1",
            (plan_id,),
        ).fetchone()
        check_name = (
            "completed_final_commit_required_task_without_final_state_commit_link"
            if any_commit_link is not None
            else "completed_publication_required_task_without_commit_link"
        )
        reason = (
            f"{task_id} on {plan_id} requires a final-state commit link"
            if any_commit_link is not None
            else f"{task_id} on {plan_id} requires a final commit link"
        )
        failures.append(
            PlanningIntegrityFailure(
                check_name,
                reason,
            )
        )
    return tuple(failures)


def _check_completed_product_worker_runs_have_commit_links(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT st.task_id, st.plan_id, wr.worker_run_id, wr.metadata_json
        FROM worker_runs wr
        JOIN supervisor_tasks st ON st.task_id = wr.task_id
        WHERE st.status = 'completed'
          AND wr.status = 'completed'
          AND wr.backend IN ('codex_exec', 'live_codex_exec')
        ORDER BY st.task_id, wr.worker_run_id
        """
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    for task_id, plan_id, worker_run_id, metadata_json in rows:
        try:
            metadata = json.loads(str(metadata_json or "{}"))
        except json.JSONDecodeError:
            continue
        if not isinstance(metadata, dict):
            continue
        if metadata.get("worker_profile") != "sanitized_product_worker":
            continue
        if _plan_has_final_state_commit_link(connection, str(plan_id)):
            continue
        failures.append(
            PlanningIntegrityFailure(
                "completed_product_worker_task_without_commit_link",
                f"{task_id} on {plan_id} via {worker_run_id} requires a final commit link",
            )
        )
    return tuple(failures)


def _plan_has_final_state_commit_link(connection: sqlite3.Connection, plan_id: str) -> bool:
    relationship_placeholders = ", ".join("?" for _ in FINAL_STATE_COMMIT_RELATIONSHIPS)
    row = connection.execute(
        f"""
        SELECT 1
        FROM plan_commit_links
        WHERE plan_id = ?
          AND relationship IN ({relationship_placeholders})
        LIMIT 1
        """,
        (plan_id, *FINAL_STATE_COMMIT_RELATIONSHIPS),
    ).fetchone()
    return row is not None


def _json_object(raw_value: object) -> dict[object, object]:
    try:
        value = json.loads(str(raw_value))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _requires_final_commit(scope: dict[object, object], context: dict[object, object]) -> bool:
    keys = (
        "final_commit_required",
        "publication_required",
        "full_afk_completion_requires_commit",
        "plugin_full_afk",
        "full_afk",
    )
    return any(scope.get(key) is True or context.get(key) is True for key in keys)


def _scope_requires_browser_smoke(raw_scope: object) -> bool:
    return _json_object(raw_scope).get("browser_smoke_required") is True


def _repo_has_git_metadata(repo_root: Path) -> bool:
    return (repo_root / ".git").exists()


def _rowid_column(table: str) -> str:
    return {
        "plans": "plan_id",
        "plan_milestones": "milestone_id",
        "supervisor_tasks": "task_id",
        "worker_runs": "worker_run_id",
        "worker_result_records": "result_id",
        "development_log_entries": "entry_id",
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
    rows = connection.execute(
        """
        SELECT ac.criterion_id, ac.plan_id, ac.status
        FROM plan_acceptance_criteria ac
        JOIN plans p ON p.plan_id = ac.plan_id
        WHERE p.status = 'completed'
          AND ac.status != 'completed'
        ORDER BY ac.plan_id, ac.criterion_id
        """
    ).fetchall()
    return tuple(
        PlanningIntegrityFailure(
            "completed_plan_has_incomplete_criterion",
            f"{criterion_id} on {plan_id} is {status}",
        )
        for criterion_id, plan_id, status in rows
    )


def _check_completed_worker_runs_have_result_records(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT wr.worker_run_id, wr.result_path, wr.result_id
        FROM worker_runs wr
        WHERE wr.status = 'completed'
          AND (
              wr.result_id IS NULL
              OR trim(wr.result_id) = ''
              OR wr.result_path IS NOT NULL
              OR NOT EXISTS (
                  SELECT 1
                  FROM worker_result_records result
                  WHERE result.result_id = wr.result_id
                    AND result.status = 'completed'
              )
              OR NOT EXISTS (
                  SELECT 1
                  FROM worker_result_run_links link
                  WHERE link.result_id = wr.result_id
                    AND link.worker_run_id = wr.worker_run_id
              )
          )
        ORDER BY wr.worker_run_id
        """
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    for worker_run_id, result_path, result_id in rows:
        if result_path is not None:
            reason = f"{worker_run_id}: completed worker run still stores result_path {result_path}"
        elif result_id is None or not str(result_id).strip():
            reason = f"{worker_run_id}: completed worker run has no result_id"
        else:
            reason = (
                f"{worker_run_id}: result_id {result_id} is missing, non-completed, or unlinked"
            )
        failures.append(
            PlanningIntegrityFailure("completed_worker_run_without_result_record", reason)
        )
    return tuple(failures)


def _check_completed_worker_runs_preserve_indexed_evidence(
    connection: sqlite3.Connection,
    repo_root: Path,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT wr.worker_run_id, wr.backend, wr.prompt_path, wr.jsonl_path, wr.worktree_path,
               wr.metadata_json, st.scope_json, p.context_json
        FROM worker_runs wr
        LEFT JOIN supervisor_tasks st ON st.task_id = wr.task_id
        LEFT JOIN plans p ON p.plan_id = st.plan_id
        WHERE wr.status = 'completed'
        ORDER BY worker_run_id
        """
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    for (
        worker_run_id,
        backend,
        prompt_path,
        jsonl_path,
        worktree_path,
        metadata_json,
        scope_json,
        context_json,
    ) in rows:
        try:
            metadata = json.loads(str(metadata_json))
        except json.JSONDecodeError:
            continue
        if not isinstance(metadata, dict):
            continue
        raw_evidence_paths = metadata.get("raw_evidence_paths")
        requires_codex_exec_evidence = canonical_worker_backend(
            str(backend)
        ) == "codex_exec" and _requires_final_commit(
            _json_object(scope_json), _json_object(context_json)
        )
        if requires_codex_exec_evidence:
            if not isinstance(raw_evidence_paths, dict):
                failures.append(
                    PlanningIntegrityFailure(
                        "completed_codex_exec_run_without_raw_evidence_paths",
                        f"{worker_run_id}: full-AFK codex_exec completion lacks raw_evidence_paths",
                    )
                )
                continue
            required_raw_evidence = (
                "prompt",
                "liveness_probe",
                "jsonl",
                "stdout",
                "stderr",
                "final_message",
                "diff_summary",
                "result",
                "evidence_manifest",
            )
            missing_raw_evidence = tuple(
                key
                for key in required_raw_evidence
                if not isinstance(raw_evidence_paths.get(key), str)
                or not str(raw_evidence_paths.get(key)).strip()
            )
            if missing_raw_evidence:
                failures.append(
                    PlanningIntegrityFailure(
                        "completed_codex_exec_run_missing_required_raw_evidence",
                        f"{worker_run_id}: raw_evidence_paths missing required keys: "
                        f"{', '.join(missing_raw_evidence)}",
                    )
                )
            missing_indexed_evidence = tuple(
                key
                for key, value in (
                    ("prompt_path", prompt_path),
                    ("jsonl_path", jsonl_path),
                    ("worktree_path", worktree_path),
                )
                if not isinstance(value, str) or not value.strip()
            )
            if missing_indexed_evidence:
                failures.append(
                    PlanningIntegrityFailure(
                        "completed_codex_exec_run_missing_indexed_evidence",
                        f"{worker_run_id}: completed codex_exec run missing indexed evidence: "
                        f"{', '.join(missing_indexed_evidence)}",
                    )
                )
        if isinstance(raw_evidence_paths, dict):
            indexed_paths = {
                "prompt": ("prompt_path", prompt_path),
                "jsonl": ("jsonl_path", jsonl_path),
            }
            for evidence_key, (indexed_key, indexed_value) in indexed_paths.items():
                raw_value = raw_evidence_paths.get(evidence_key)
                if not isinstance(raw_value, str) or not raw_value.strip():
                    continue
                if indexed_value != raw_value:
                    failures.append(
                        PlanningIntegrityFailure(
                            "completed_worker_run_indexed_evidence_drift",
                            f"{worker_run_id}: indexed {indexed_key}={indexed_value!r}, "
                            f"raw evidence records {raw_value!r}",
                        )
                    )
            for evidence_key, raw_value in sorted(raw_evidence_paths.items()):
                if not isinstance(raw_value, str) or not raw_value.strip():
                    failures.append(
                        PlanningIntegrityFailure(
                            "completed_worker_run_raw_evidence_invalid",
                            f"{worker_run_id}: raw evidence {evidence_key} must be nonblank",
                        )
                    )
                    continue
                evidence_path = _artifact_path(repo_root, raw_value)
                if (
                    evidence_path is not None
                    and not evidence_path.exists()
                    and not _missing_ignored_runtime_path_is_clean_checkout(
                        repo_root,
                        raw_value,
                    )
                ):
                    failures.append(
                        PlanningIntegrityFailure(
                            "completed_worker_run_indexed_evidence_missing",
                            f"{worker_run_id}: raw evidence {evidence_key} does not exist: "
                            f"{raw_value}",
                        )
                    )
        manifest_value = metadata.get("evidence_manifest_path")
        if not isinstance(manifest_value, str) or not manifest_value.strip():
            manifest_value = metadata.get("evidence_manifest")
        if isinstance(manifest_value, str) and manifest_value.strip():
            manifest_path = _artifact_path(repo_root, manifest_value)
            if (
                manifest_path is not None
                and not manifest_path.exists()
                and not _missing_ignored_runtime_path_is_clean_checkout(
                    repo_root,
                    manifest_value,
                )
            ):
                failures.append(
                    PlanningIntegrityFailure(
                        "completed_worker_run_evidence_manifest_missing",
                        f"{worker_run_id}: evidence manifest does not exist: {manifest_value}",
                    )
                )
            elif manifest_path is not None and manifest_path.is_file():
                failures.extend(
                    _worker_evidence_manifest_hash_failures(
                        worker_run_id=str(worker_run_id),
                        repo_root=repo_root,
                        manifest_path=manifest_path,
                    )
                )
    return tuple(failures)


def _check_completed_worker_runs_do_not_hide_failed_controller_results(
    connection: sqlite3.Connection,
    repo_root: Path,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT worker_run_id
        FROM worker_runs
        WHERE status = 'completed'
        ORDER BY worker_run_id
        """
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    for (worker_run_id,) in rows:
        controller_path = repo_root / "runs" / str(worker_run_id) / "controller.stdout.json"
        if not controller_path.is_file():
            continue
        try:
            payload = json.loads(controller_path.read_text(encoding="utf-8"))
        except OSError, json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or payload.get("status") != "failed":
            continue
        payload_worker_run_id = payload.get("worker_run_id")
        if isinstance(payload_worker_run_id, str) and payload_worker_run_id != str(worker_run_id):
            continue
        failure_class = payload.get("failure_class")
        failures.append(
            PlanningIntegrityFailure(
                "completed_worker_run_failed_controller_result",
                f"{worker_run_id}: controller.stdout.json records failed status"
                + (
                    f" ({failure_class})"
                    if isinstance(failure_class, str) and failure_class.strip()
                    else ""
                ),
            )
        )
    return tuple(failures)


def _check_completed_afk_tasks_have_worker_evidence(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT st.task_id, st.plan_id, st.scope_json, st.worker_backend
        FROM supervisor_tasks st
        JOIN plans p ON p.plan_id = st.plan_id
        WHERE st.task_type = 'AFK'
          AND st.status = 'completed'
          AND NOT EXISTS (
              SELECT 1
              FROM worker_runs wr
              WHERE wr.task_id = st.task_id
                AND wr.status = 'completed'
                AND wr.result_id IS NOT NULL
                AND trim(wr.result_id) != ''
                AND EXISTS (
                    SELECT 1
                    FROM worker_result_run_links link
                    WHERE link.result_id = wr.result_id
                      AND link.worker_run_id = wr.worker_run_id
                )
        )
        ORDER BY st.task_id
        """
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    for task_id, plan_id, scope_json, worker_backend in rows:
        if _completed_afk_review_task_has_review_evidence(
            connection,
            plan_id=str(plan_id),
            scope_json=str(scope_json),
            worker_backend=str(worker_backend),
        ):
            continue
        if _completed_afk_manual_task_has_progress_evidence(
            connection,
            plan_id=str(plan_id),
            task_id=str(task_id),
            worker_backend=str(worker_backend),
        ):
            continue
        failures.append(
            PlanningIntegrityFailure(
                "completed_afk_task_without_worker_evidence",
                f"{task_id} on plan {plan_id}",
            )
        )
    return tuple(failures)


def _check_completed_codex_exec_tasks_have_review_posture(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT st.task_id, st.plan_id, st.scope_json
        FROM supervisor_tasks st
        WHERE st.task_type = 'AFK'
          AND st.status = 'completed'
          AND st.review_required = 0
          AND EXISTS (
              SELECT 1
              FROM worker_runs wr
              WHERE wr.task_id = st.task_id
                AND wr.status = 'completed'
                AND wr.result_id IS NOT NULL
                AND trim(wr.result_id) != ''
                AND wr.backend IN ('codex_exec', 'live_codex_exec')
          )
        ORDER BY st.task_id
        """
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    for task_id, plan_id, scope_json in rows:
        scope = _json_object(scope_json)
        if _scope_review_waived(scope) or task_uses_controller_worker_profile(scope):
            continue
        failures.append(
            PlanningIntegrityFailure(
                "completed_codex_exec_task_without_review_or_waiver",
                f"{task_id} on plan {plan_id} completed without review_required or waiver",
            )
        )
    return tuple(failures)


def _scope_review_waived(scope: dict[object, object]) -> bool:
    return scope.get("review_skipped") is True or scope.get("review_gate") == "review_skipped"


def _check_completed_promotion_tasks_have_progress(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT task_id, plan_id, title, goal, scope_json, worker_backend
        FROM supervisor_tasks
        WHERE status = 'completed'
        ORDER BY task_id
        """
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    for task_id, plan_id, title, goal, scope_json, worker_backend in rows:
        if canonical_worker_backend(str(worker_backend)) != "manual":
            continue
        if not _is_promotion_task(
            task_id=str(task_id),
            title=str(title or ""),
            goal=str(goal or ""),
            scope=_json_object(scope_json),
        ):
            continue
        if _promotion_progress_for_task(connection, str(plan_id), str(task_id)) is not None:
            continue
        failures.append(
            PlanningIntegrityFailure(
                "completed_promotion_task_without_promotion_progress",
                f"{task_id} on plan {plan_id} completed without {PROMOTION_COMPLETED_EVENT}",
            )
        )
    return tuple(failures)


def _is_promotion_task(
    *,
    task_id: str,
    title: str,
    goal: str,
    scope: dict[object, object],
) -> bool:
    if task_id.startswith("task-promote"):
        return True
    if (
        scope.get("task_role") == "promotion"
        or scope.get("controller_mutation_kind") == "promotion"
    ):
        return True
    text = f"{title} {goal}".lower()
    return "promote" in text and "worker" in text


def _worker_evidence_manifest_hash_failures(
    *,
    worker_run_id: str,
    repo_root: Path,
    manifest_path: Path,
) -> tuple[PlanningIntegrityFailure, ...]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return (
            PlanningIntegrityFailure(
                "completed_worker_run_evidence_manifest_invalid",
                f"{worker_run_id}: evidence manifest is unreadable: {exc}",
            ),
        )
    if not isinstance(manifest, dict):
        return (
            PlanningIntegrityFailure(
                "completed_worker_run_evidence_manifest_invalid",
                f"{worker_run_id}: evidence manifest must be an object",
            ),
        )
    paths = manifest.get("paths")
    if not isinstance(paths, dict):
        return ()
    failures: list[PlanningIntegrityFailure] = []
    for evidence_key, record in sorted(paths.items()):
        if not isinstance(record, dict) or record.get("exists") is not True:
            continue
        expected_sha = record.get("sha256")
        expected_bytes = record.get("bytes")
        if not isinstance(expected_sha, str) or not isinstance(expected_bytes, int):
            continue
        raw_evidence_paths = manifest.get("raw_evidence_paths")
        relative_path = None
        if isinstance(raw_evidence_paths, dict):
            candidate = raw_evidence_paths.get(evidence_key)
            if isinstance(candidate, str):
                relative_path = candidate
        if relative_path is None:
            metadata_paths = manifest.get("paths_by_key")
            if isinstance(metadata_paths, dict):
                candidate = metadata_paths.get(evidence_key)
                if isinstance(candidate, str):
                    relative_path = candidate
        if relative_path is None:
            relative_path = _manifest_default_relative_path(
                manifest_path,
                evidence_key=str(evidence_key),
            )
        evidence_path = _artifact_path(repo_root, relative_path)
        if evidence_path is None or not evidence_path.is_file():
            continue
        actual_bytes = evidence_path.stat().st_size
        actual_sha = _sha256_file(evidence_path)
        if actual_sha != expected_sha or actual_bytes != expected_bytes:
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_evidence_manifest_hash_drift",
                    (
                        f"{worker_run_id}: evidence manifest {evidence_key} hash/size drift "
                        f"for {relative_path}"
                    ),
                )
            )
    return tuple(failures)


def _manifest_default_relative_path(manifest_path: Path, *, evidence_key: str) -> str:
    run_id = manifest_path.parent.name
    if evidence_key == "raw_result":
        return f"artifacts/{run_id}/worker-result.raw.json"
    if evidence_key == "prompt":
        return f"runs/{run_id}/prompt.md"
    if evidence_key == "jsonl":
        return f"runs/{run_id}/events.jsonl"
    if evidence_key == "stdout":
        return f"runs/{run_id}/stdout.txt"
    if evidence_key == "stderr":
        return f"runs/{run_id}/stderr.txt"
    if evidence_key == "final_message":
        return f"runs/{run_id}/final-message.txt"
    if evidence_key == "diff_summary":
        return f"runs/{run_id}/diff-summary.txt"
    return ""


def _completed_afk_review_task_has_review_evidence(
    connection: sqlite3.Connection,
    *,
    plan_id: str,
    scope_json: str,
    worker_backend: str,
) -> bool:
    if canonical_worker_backend(worker_backend) != "codex_review":
        return False
    try:
        scope = json.loads(scope_json)
    except json.JSONDecodeError:
        return False
    if not isinstance(scope, dict):
        return False
    if scope.get("review_gate") != "separate_review_required_task":
        return False
    source_task_id = scope.get("source_task_id")
    if not isinstance(source_task_id, str) or not source_task_id.strip():
        return False
    return _review_progress_for_task(connection, plan_id, source_task_id) is not None


def _completed_afk_manual_task_has_progress_evidence(
    connection: sqlite3.Connection,
    *,
    plan_id: str,
    task_id: str,
    worker_backend: str,
) -> bool:
    if canonical_worker_backend(worker_backend) != "manual":
        return False
    promotion = _promotion_progress_for_task(connection, plan_id, task_id)
    if promotion is None:
        return False
    _, details = promotion
    source_task_id = details.get("source_task_id")
    if not isinstance(source_task_id, str) or not source_task_id.strip():
        return False
    if not _source_task_is_review_required(connection, plan_id, source_task_id):
        return True
    return _review_progress_for_task(connection, plan_id, source_task_id) is not None or (
        details.get("hitl_authority_required") is True
        and (
            details.get("hitl_authority_accepted") is True
            or details.get("hitl_authority") == "accepted"
        )
    )


def _source_task_is_review_required(
    connection: sqlite3.Connection,
    plan_id: str,
    source_task_id: str,
) -> bool:
    row = connection.execute(
        """
        SELECT review_required
        FROM supervisor_tasks
        WHERE plan_id = ?
          AND task_id = ?
        """,
        (plan_id, source_task_id),
    ).fetchone()
    return row is not None and bool(row[0])


def _check_completed_review_required_tasks_have_review_evidence(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT st.task_id, st.plan_id, st.task_type, st.scope_json, p.context_json
        FROM supervisor_tasks st
        JOIN plans p ON p.plan_id = st.plan_id
        JOIN (
            SELECT plan_id, MIN(occurred_at) AS enabled_at
            FROM plan_progress_events
            WHERE event_type = ?
            GROUP BY plan_id
        ) marker ON marker.plan_id = st.plan_id
        WHERE st.status = 'completed'
          AND st.review_required = 1
          AND st.updated_at >= marker.enabled_at
        ORDER BY st.task_id
        """,
        (REVIEW_ENFORCEMENT_ENABLED_EVENT,),
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    for task_id, plan_id, task_type, scope_json, context_json in rows:
        review_progress = _review_progress_for_task(connection, str(plan_id), str(task_id))
        if review_progress is None:
            failures.append(
                PlanningIntegrityFailure(
                    "completed_review_required_task_without_review_result",
                    f"{task_id} completed without {REVIEW_RESULT_RECORDED_EVENT} progress",
                )
            )
            continue
        progress_id, details = review_progress
        if (
            task_type == "AFK"
            and _requires_final_commit(_json_object(scope_json), _json_object(context_json))
            and not details.get("hitl_authority_required")
            and not _has_afk_review_task_for_source(connection, str(plan_id), str(task_id))
        ):
            failures.append(
                PlanningIntegrityFailure(
                    "completed_full_afk_review_required_task_without_afk_review_task",
                    f"{task_id} completed with review progress but no separate AFK review task",
                )
            )
            continue
        accepted_findings = details.get("accepted_findings", [])
        if not isinstance(accepted_findings, list):
            failures.append(
                PlanningIntegrityFailure(
                    "completed_review_required_task_invalid_review_result",
                    f"{progress_id} accepted_findings must be a list",
                )
            )
            continue
        review_id = details.get("review_id")
        if not isinstance(review_id, str) or not review_id.strip():
            failures.append(
                PlanningIntegrityFailure(
                    "completed_review_required_task_invalid_review_result",
                    f"{progress_id} review_id must be nonblank",
                )
            )
            continue
        for finding in accepted_findings:
            finding_id = finding.get("finding_id") if isinstance(finding, dict) else None
            if not isinstance(finding_id, str) or not finding_id.strip():
                failures.append(
                    PlanningIntegrityFailure(
                        "completed_review_required_task_invalid_review_result",
                        f"{progress_id} accepted finding is missing finding_id",
                    )
                )
                continue
            if not _accepted_finding_has_repair_task(
                connection,
                str(plan_id),
                review_id,
                finding_id,
            ):
                failures.append(
                    PlanningIntegrityFailure(
                        "completed_review_required_task_without_routed_finding",
                        f"{task_id} review {review_id} finding {finding_id}",
                    )
                )
    return tuple(failures)


def _has_afk_review_task_for_source(
    connection: sqlite3.Connection,
    plan_id: str,
    source_task_id: str,
) -> bool:
    rows = connection.execute(
        """
        SELECT task_type, worker_backend, scope_json
        FROM supervisor_tasks
        WHERE plan_id = ?
        """,
        (plan_id,),
    ).fetchall()
    for task_type, worker_backend, scope_json in rows:
        if task_type != "AFK" or canonical_worker_backend(str(worker_backend)) != "codex_review":
            continue
        try:
            scope = json.loads(str(scope_json))
        except json.JSONDecodeError:
            continue
        if not isinstance(scope, dict):
            continue
        if (
            scope.get("review_gate") == "separate_review_required_task"
            and scope.get("source_task_id") == source_task_id
        ):
            return True
    return False


def _check_review_required_promotions_have_review_evidence(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT progress.progress_id, progress.plan_id, progress.details
        FROM plan_progress_events progress
        WHERE progress.event_type = ?
        ORDER BY progress.plan_id, progress.progress_id
        """,
        (PROMOTION_COMPLETED_EVENT,),
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    for progress_id, plan_id, details_json in rows:
        try:
            details = json.loads(str(details_json or "{}"))
        except json.JSONDecodeError:
            continue
        if not isinstance(details, dict):
            continue
        source_task_id = details.get("source_task_id")
        if not isinstance(source_task_id, str) or not source_task_id.strip():
            continue
        if not _source_task_is_review_required(connection, str(plan_id), source_task_id):
            continue
        if _review_progress_for_task(connection, str(plan_id), source_task_id) is not None:
            continue
        if details.get("hitl_authority_required") is True and (
            details.get("hitl_authority_accepted") is True
            or details.get("hitl_authority") == "accepted"
        ):
            continue
        failures.append(
            PlanningIntegrityFailure(
                "promotion_of_review_required_task_without_review_result",
                f"{progress_id} promotes {source_task_id} without review result or HITL authority",
            )
        )
    return tuple(failures)


def _review_progress_for_task(
    connection: sqlite3.Connection,
    plan_id: str,
    task_id: str,
) -> tuple[str, dict[str, object]] | None:
    rows = connection.execute(
        """
        SELECT progress_id, details
        FROM plan_progress_events
        WHERE plan_id = ?
          AND event_type = ?
        ORDER BY occurred_at DESC, progress_id DESC
        """,
        (plan_id, REVIEW_RESULT_RECORDED_EVENT),
    ).fetchall()
    for progress_id, details_json in rows:
        try:
            details = json.loads(str(details_json or "{}"))
        except json.JSONDecodeError:
            continue
        if isinstance(details, dict) and details.get("target") == task_id:
            return str(progress_id), details
    return None


def _promotion_progress_for_task(
    connection: sqlite3.Connection,
    plan_id: str,
    task_id: str,
) -> tuple[str, dict[str, object]] | None:
    rows = connection.execute(
        """
        SELECT progress_id, details
        FROM plan_progress_events
        WHERE plan_id = ?
          AND event_type = ?
        ORDER BY occurred_at DESC, progress_id DESC
        """,
        (plan_id, PROMOTION_COMPLETED_EVENT),
    ).fetchall()
    for progress_id, details_json in rows:
        try:
            details = json.loads(str(details_json or "{}"))
        except json.JSONDecodeError:
            continue
        if not isinstance(details, dict):
            continue
        scoped_task_id = _promotion_progress_task_id(details)
        source_task_id = details.get("source_task_id")
        if scoped_task_id == task_id and isinstance(source_task_id, str) and source_task_id.strip():
            return str(progress_id), details
    return None


def _promotion_progress_task_id(details: dict[str, object]) -> str | None:
    for key in ("task_id", "promotion_task_id", "target_task_id", "target"):
        value = details.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _accepted_finding_has_repair_task(
    connection: sqlite3.Connection,
    plan_id: str,
    review_id: str,
    finding_id: str,
) -> bool:
    rows = connection.execute(
        """
        SELECT scope_json
        FROM supervisor_tasks
        WHERE plan_id = ?
        """,
        (plan_id,),
    ).fetchall()
    for (scope_json,) in rows:
        try:
            scope = json.loads(str(scope_json))
        except json.JSONDecodeError:
            continue
        if not isinstance(scope, dict):
            continue
        if (
            scope.get("source_review_id") == review_id
            and scope.get("source_finding_id") == finding_id
        ):
            return True
    return False


def _check_worker_result_records_have_run_links(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT result.result_id
        FROM worker_result_records result
        WHERE NOT EXISTS (
            SELECT 1
            FROM worker_result_run_links link
            WHERE link.result_id = result.result_id
        )
        ORDER BY result.result_id
        """
    ).fetchall()
    return tuple(
        PlanningIntegrityFailure(
            "worker_result_without_run_link",
            str(result_id),
        )
        for (result_id,) in rows
    )


def _check_completed_worker_runs_have_artifact_links(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT wr.worker_run_id, st.plan_id, wr.metadata_json, result.source_path,
               result.metadata_json
        FROM worker_runs wr
        JOIN supervisor_tasks st ON st.task_id = wr.task_id
        JOIN worker_result_run_links link ON link.worker_run_id = wr.worker_run_id
        JOIN worker_result_records result ON result.result_id = link.result_id
        WHERE wr.status = 'completed'
        ORDER BY wr.worker_run_id
        """
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    for worker_run_id, plan_id, run_metadata_json, source_path, result_metadata_json in rows:
        expected_links = _expected_completed_worker_artifact_links(
            source_path=source_path,
            result_metadata_json=result_metadata_json,
            run_metadata_json=run_metadata_json,
        )
        missing = tuple(
            f"{relationship}:{artifact_id}"
            for artifact_id, relationship in expected_links
            if not _plan_artifact_link_exists(
                connection,
                plan_id=str(plan_id),
                artifact_id=artifact_id,
                relationship=relationship,
            )
        )
        if not missing:
            continue
        failures.append(
            PlanningIntegrityFailure(
                "completed_worker_run_missing_artifact_links",
                f"{worker_run_id} on {plan_id} missing artifact links: {', '.join(missing)}",
            )
        )
    return tuple(failures)


def _expected_completed_worker_artifact_links(
    *,
    source_path: object,
    result_metadata_json: object,
    run_metadata_json: object,
) -> tuple[tuple[str, str], ...]:
    links: list[tuple[str, str]] = []
    source_artifact_id = _worker_result_linkable_artifact_id(source_path)
    if source_artifact_id is not None:
        links.append((source_artifact_id, WORKER_RESULT_ARTIFACT_RELATIONSHIP))
    result_metadata = _json_object(result_metadata_json)
    normalized_path = result_metadata.get("normalized_result_path")
    normalized_artifact_id = _worker_result_linkable_artifact_id(normalized_path)
    if normalized_artifact_id is not None:
        links.append(
            (
                normalized_artifact_id,
                WORKER_RESULT_NORMALIZED_ARTIFACT_RELATIONSHIP,
            )
        )
    run_metadata = _json_object(run_metadata_json)
    manifest_path = _worker_run_evidence_manifest_path(run_metadata)
    manifest_artifact_id = _worker_result_linkable_artifact_id(manifest_path)
    if manifest_artifact_id is not None:
        links.append((manifest_artifact_id, WORKER_EVIDENCE_MANIFEST_ARTIFACT_RELATIONSHIP))
    return tuple(dict.fromkeys(links))


def _worker_result_linkable_artifact_id(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = _normalize_repo_path(value)
    if normalized.startswith("worker-results/"):
        return None
    return normalized


def _worker_run_evidence_manifest_path(metadata: dict[object, object]) -> str | None:
    for key in ("evidence_manifest_path", "evidence_manifest"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for parent_key in ("raw_evidence_paths", "planned_evidence_paths"):
        parent = metadata.get(parent_key)
        if not isinstance(parent, dict):
            continue
        value = parent.get("evidence_manifest")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _plan_artifact_link_exists(
    connection: sqlite3.Connection,
    *,
    plan_id: str,
    artifact_id: str,
    relationship: str,
) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM plan_artifact_links
        WHERE plan_id = ?
          AND artifact_id = ?
          AND relationship = ?
        LIMIT 1
        """,
        (plan_id, artifact_id, relationship),
    ).fetchone()
    return row is not None


def _check_worker_result_records_have_valid_payloads(
    connection: sqlite3.Connection,
    repo_root: Path,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT
            result.result_id,
            result.status,
            result.raw_payload_json,
            result.tests_run_json,
            result.acceptance_results_json,
            result.changed_files_json,
            result.artifacts_json,
            result.completion_notes,
            result.source_path,
            result.source_sha256
        FROM worker_result_records result
        ORDER BY result.result_id
        """
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    for (
        result_id,
        status,
        raw_payload_json,
        tests_run_json,
        acceptance_results_json,
        changed_files_json,
        artifacts_json,
        completion_notes,
        source_path,
        source_sha256,
    ) in rows:
        try:
            payload = json.loads(str(raw_payload_json))
        except json.JSONDecodeError as exc:
            failures.append(
                PlanningIntegrityFailure(
                    "worker_result_invalid_payload",
                    f"{result_id}: raw_payload_json is invalid JSON: {exc.msg}",
                )
            )
            continue
        if not isinstance(payload, dict):
            failures.append(
                PlanningIntegrityFailure(
                    "worker_result_invalid_payload",
                    f"{result_id}: raw_payload_json must be an object",
                )
            )
            continue
        failures.extend(_worker_result_type_failures(str(result_id), payload))
        missing = sorted(WORKER_RESULT_REQUIRED_KEYS - set(payload))
        if missing:
            failures.append(
                PlanningIntegrityFailure(
                    "worker_result_invalid_payload",
                    f"{result_id}: missing {', '.join(missing)}",
                )
            )
        if payload.get("status") != status:
            failures.append(
                PlanningIntegrityFailure(
                    "worker_result_status_mismatch",
                    (
                        f"{result_id}: row status {status!r} differs from payload "
                        f"{payload.get('status')!r}"
                    ),
                )
            )
        if not _payload_has_completion_notes(payload) and not (
            isinstance(completion_notes, str) and completion_notes.strip()
        ):
            failures.append(
                PlanningIntegrityFailure(
                    "worker_result_missing_completion_notes",
                    str(result_id),
                )
            )
        if status == "completed":
            failures.extend(_completed_worker_result_evidence_failures(str(result_id), payload))
            failures.extend(
                _completed_worker_result_stale_blocker_failures(str(result_id), payload)
            )
        failures.extend(_completed_worker_result_test_run_failures(str(result_id), payload))
        failures.extend(_completed_worker_result_browser_smoke_failures(str(result_id), payload))
        failures.extend(
            _worker_result_source_hash_failures(
                str(result_id),
                repo_root,
                source_path,
                source_sha256,
            )
        )
        failures.extend(
            _db_worker_result_path_array_failures(
                str(result_id),
                "changed_files_json",
                str(changed_files_json),
                reject_worker_results=True,
            )
        )
        failures.extend(
            _db_worker_result_path_array_failures(
                str(result_id),
                "artifacts_json",
                str(artifacts_json),
                reject_worker_results=True,
            )
        )
        failures.extend(_db_worker_result_tests_array_failures(str(result_id), str(tests_run_json)))
        try:
            acceptance_results = json.loads(str(acceptance_results_json))
        except json.JSONDecodeError as exc:
            failures.append(
                PlanningIntegrityFailure(
                    "worker_result_invalid_acceptance_results",
                    f"{result_id}: {exc.msg}",
                )
            )
        else:
            if not isinstance(acceptance_results, dict):
                failures.append(
                    PlanningIntegrityFailure(
                        "worker_result_invalid_acceptance_results",
                        f"{result_id}: acceptance_results_json must be an object",
                    )
                )
    return tuple(failures)


def _check_passed_browser_smoke_has_progress(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        """
        SELECT wr.worker_run_id, st.plan_id, result.raw_payload_json
        FROM worker_result_records result
        JOIN worker_result_run_links link ON link.result_id = result.result_id
        JOIN worker_runs wr ON wr.worker_run_id = link.worker_run_id
        JOIN supervisor_tasks st ON st.task_id = wr.task_id
        WHERE wr.status = 'completed'
          AND result.status = 'completed'
        ORDER BY wr.worker_run_id
        """
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    for worker_run_id, plan_id, raw_payload_json in rows:
        try:
            payload = json.loads(str(raw_payload_json or "{}"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if not _payload_has_passed_browser_smoke(payload):
            continue
        if _has_browser_smoke_passed_progress(
            connection,
            plan_id=str(plan_id),
            worker_run_id=str(worker_run_id),
        ):
            continue
        failures.append(
            PlanningIntegrityFailure(
                "completed_worker_run_missing_browser_smoke_progress",
                f"{worker_run_id} on {plan_id} has passed browser smoke without progress event",
            )
        )
    return tuple(failures)


def _payload_has_passed_browser_smoke(payload: dict[object, object]) -> bool:
    entries = payload.get("browser_smoke_results")
    if not isinstance(entries, list):
        return False
    return any(isinstance(entry, dict) and entry.get("status") == "passed" for entry in entries)


def _has_browser_smoke_passed_progress(
    connection: sqlite3.Connection,
    *,
    plan_id: str,
    worker_run_id: str,
) -> bool:
    rows = connection.execute(
        """
        SELECT details
        FROM plan_progress_events
        WHERE plan_id = ?
          AND event_type = ?
        """,
        (plan_id, BROWSER_SMOKE_PASSED_EVENT),
    ).fetchall()
    for (details_json,) in rows:
        try:
            details = json.loads(str(details_json or "{}"))
        except json.JSONDecodeError:
            continue
        if isinstance(details, dict) and details.get("worker_run_id") == worker_run_id:
            return True
    return False


def _check_worker_result_records_align_with_runs(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    completed_result_ids_by_run = {
        str(worker_run_id): str(result_id)
        for worker_run_id, result_id in connection.execute(
            """
            SELECT worker_run_id, result_id
            FROM worker_runs
            WHERE status = 'completed'
              AND result_id IS NOT NULL
              AND trim(result_id) != ''
            """
        ).fetchall()
    }
    rows = connection.execute(
        """
        SELECT
            result.result_id,
            result.status,
            result.raw_payload_json,
            result.tests_run_json,
            result.acceptance_results_json,
            result.changed_files_json,
            link.worker_run_id,
            wr.status,
            st.verification_commands_json,
            st.acceptance_criteria_json,
            st.allowed_paths_json,
            st.scope_json
        FROM worker_result_records result
        JOIN worker_result_run_links link ON link.result_id = result.result_id
        LEFT JOIN worker_runs wr ON wr.worker_run_id = link.worker_run_id
        LEFT JOIN supervisor_tasks st ON st.task_id = wr.task_id
        ORDER BY result.result_id, link.worker_run_id
        """
    ).fetchall()
    failures: list[PlanningIntegrityFailure] = []
    for (
        result_id,
        result_status,
        raw_payload_json,
        tests_run_json,
        acceptance_results_json,
        changed_files_json,
        worker_run_id,
        worker_run_status,
        verification_json,
        acceptance_json,
        allowed_paths_json,
        scope_json,
    ) in rows:
        try:
            payload = json.loads(str(raw_payload_json))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if result_status == "completed" and worker_run_status != "completed":
            failures.append(
                PlanningIntegrityFailure(
                    "worker_result_run_status_mismatch",
                    (
                        f"{result_id}: linked run {worker_run_id} is "
                        f"{worker_run_status}, not completed"
                    ),
                )
            )
        if result_status != "completed":
            continue
        failures.extend(_completed_worker_result_identity_failures(str(worker_run_id), payload))
        failures.extend(
            _completed_worker_result_shared_link_failures(
                str(worker_run_id),
                str(result_id),
                payload,
                completed_result_ids_by_run,
            )
        )
        payload_for_task = dict(payload)
        try:
            tests_run = json.loads(str(tests_run_json))
        except json.JSONDecodeError:
            tests_run = payload.get("tests_run")
        try:
            acceptance_results = json.loads(str(acceptance_results_json))
        except json.JSONDecodeError:
            acceptance_results = payload.get("acceptance_results")
        try:
            changed_files = json.loads(str(changed_files_json))
        except json.JSONDecodeError:
            changed_files = payload.get("changed_files")
        payload_for_task["tests_run"] = tests_run
        payload_for_task["acceptance_results"] = acceptance_results
        payload_for_task["changed_files"] = changed_files
        if allowed_paths_json is not None:
            failures.extend(
                _completed_worker_result_allowed_path_failures(
                    str(worker_run_id),
                    payload_for_task,
                    str(allowed_paths_json),
                )
            )
        if verification_json is not None and acceptance_json is not None:
            failures.extend(
                _completed_worker_result_task_alignment_failures(
                    str(worker_run_id),
                    payload_for_task,
                    str(verification_json),
                    str(acceptance_json),
                )
            )
        failures.extend(
            _completed_worker_result_browser_smoke_failures(
                str(worker_run_id),
                payload,
                required=_scope_requires_browser_smoke(scope_json),
            )
        )
    return tuple(failures)


def _payload_has_completion_notes(payload: dict[object, object]) -> bool:
    for key in ("completion_notes", "handoff_notes"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _db_worker_result_path_array_failures(
    result_id: str,
    field_name: str,
    value_json: str,
    *,
    reject_worker_results: bool,
) -> tuple[PlanningIntegrityFailure, ...]:
    try:
        values = json.loads(value_json)
    except json.JSONDecodeError as exc:
        return (
            PlanningIntegrityFailure(
                "worker_result_invalid_path_array",
                f"{result_id}: {field_name} invalid JSON: {exc.msg}",
            ),
        )
    if not isinstance(values, list):
        return (
            PlanningIntegrityFailure(
                "worker_result_invalid_path_array",
                f"{result_id}: {field_name} must be an array",
            ),
        )
    failures: list[PlanningIntegrityFailure] = []
    for item in values:
        reason = _worker_result_entry_path_reason(item)
        if reason is not None:
            failures.append(
                PlanningIntegrityFailure(
                    "worker_result_invalid_path_array",
                    f"{result_id}: {field_name} entry is unsafe: {item} ({reason})",
                )
            )
            continue
        normalized = _normalize_repo_path(str(item))
        if reject_worker_results and normalized.startswith("worker-results/"):
            failures.append(
                PlanningIntegrityFailure(
                    "worker_result_filesystem_artifact_recorded",
                    f"{result_id}: {field_name} stores {normalized}",
                )
            )
    return tuple(failures)


def _db_worker_result_tests_array_failures(
    result_id: str,
    value_json: str,
) -> tuple[PlanningIntegrityFailure, ...]:
    try:
        values = json.loads(value_json)
    except json.JSONDecodeError as exc:
        return (
            PlanningIntegrityFailure(
                "worker_result_invalid_tests_run",
                f"{result_id}: tests_run_json invalid JSON: {exc.msg}",
            ),
        )
    if not isinstance(values, list):
        return (
            PlanningIntegrityFailure(
                "worker_result_invalid_tests_run",
                f"{result_id}: tests_run_json must be an array",
            ),
        )
    return _completed_worker_result_test_run_failures(result_id, {"tests_run": values})


def _check_worker_results_not_stored_as_public_files(
    connection: sqlite3.Connection,
    repo_root: Path,
) -> tuple[PlanningIntegrityFailure, ...]:
    failures: list[PlanningIntegrityFailure] = []
    worker_results_dir = repo_root / "worker-results"
    if worker_results_dir.exists():
        failures.append(
            PlanningIntegrityFailure(
                "worker_results_directory_exists",
                "worker-results/ must not exist in the repo",
            )
        )
    rows = connection.execute(
        """
        SELECT 'worker_run' AS source, worker_run_id AS id, result_path AS path
        FROM worker_runs
        WHERE result_path IS NOT NULL AND trim(result_path) != ''
        UNION ALL
        SELECT 'artifact_link' AS source, plan_id AS id, artifact_id AS path
        FROM plan_artifact_links
        WHERE artifact_id LIKE 'worker-results/%'
        UNION ALL
        SELECT 'progress_link' AS source, progress_id AS id, linked_artifact_id AS path
        FROM plan_progress_events
        WHERE linked_artifact_id LIKE 'worker-results/%'
        ORDER BY source, id
        """
    ).fetchall()
    for source, identifier, path in rows:
        failures.append(
            PlanningIntegrityFailure(
                "worker_result_filesystem_reference",
                f"{source} {identifier}: {path}",
            )
        )
    return tuple(failures)


def _check_handoff_snapshot_is_compact(repo_root: Path) -> tuple[PlanningIntegrityFailure, ...]:
    handoff_path = repo_root / "HANDOFF.md"
    if not handoff_path.exists():
        if not (repo_root / ".git").exists():
            return ()
        return (PlanningIntegrityFailure("handoff_snapshot_missing", "HANDOFF.md is missing"),)
    text = handoff_path.read_text(encoding="utf-8")
    failures: list[PlanningIntegrityFailure] = []
    line_count = len(text.splitlines())
    if line_count > 180:
        failures.append(
            PlanningIntegrityFailure(
                "handoff_snapshot_too_large",
                f"HANDOFF.md has {line_count} lines; expected a compact snapshot",
            )
        )
    forbidden_patterns = (
        "Running Development Log",
        "Development Log",
        "Completion Log",
        "Worker Results",
        "Stage Log",
        "Historical Checkpoint",
    )
    for pattern in forbidden_patterns:
        if pattern.lower() in text.lower():
            failures.append(
                PlanningIntegrityFailure(
                    "handoff_contains_historical_log",
                    f"HANDOFF.md contains {pattern!r}",
                )
            )
            break
    return tuple(failures)


def _check_handoff_snapshot_matches_queue_state(
    connection: sqlite3.Connection,
    repo_root: Path,
) -> tuple[PlanningIntegrityFailure, ...]:
    handoff_path = repo_root / "HANDOFF.md"
    if not handoff_path.exists():
        return ()
    active_queue_count = int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM plans
            WHERE status IN ('active', 'blocked')
            """
        ).fetchone()[0]
    )
    if active_queue_count:
        return ()
    text = handoff_path.read_text(encoding="utf-8").lower()
    queue_state_line = next(
        (line for line in text.splitlines() if "current queue state:" in line),
        None,
    )
    if queue_state_line is not None and not any(
        state in queue_state_line for state in ("empty", "completed")
    ):
        return (
            PlanningIntegrityFailure(
                "handoff_snapshot_stale_queue_state",
                "HANDOFF.md current queue state disagrees with planning SQLite: no active or "
                "blocked queue plan remains",
            ),
        )
    stale_review_phrases = (
        "ready for required review",
        "review pending",
        "awaiting review",
        "needs review before completion",
    )
    for phrase in stale_review_phrases:
        if phrase in text:
            return (
                PlanningIntegrityFailure(
                    "handoff_snapshot_stale_review_state",
                    f"HANDOFF.md says {phrase!r}, but no active or blocked queue plan remains",
                ),
            )
    return ()


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
            st.allowed_paths_json,
            st.scope_json
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
    for (
        worker_run_id,
        result_path,
        verification_json,
        acceptance_json,
        allowed_paths_json,
        scope_json,
    ) in rows:
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
        failures.extend(
            _completed_worker_result_browser_smoke_failures(
                str(worker_run_id),
                payload,
                required=_scope_requires_browser_smoke(scope_json),
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
        "browser_smoke_results": list,
        "changed_files": list,
        "tests_run": list,
        "acceptance_results": dict,
        "risks": list,
        "follow_up_tasks": list,
        "artifacts": list,
        "completion_notes": str,
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


def _completed_worker_result_shared_link_failures(
    worker_run_id: str,
    result_id: str,
    payload: dict[object, object],
    completed_result_ids_by_run: dict[str, str],
) -> tuple[PlanningIntegrityFailure, ...]:
    worker_run_ids = payload.get("worker_run_ids")
    if not isinstance(worker_run_ids, list):
        return ()

    failures: list[PlanningIntegrityFailure] = []
    for value in worker_run_ids:
        if not isinstance(value, str) or not value.strip():
            continue
        declared_worker_run_id = value.strip()
        declared_result_id = completed_result_ids_by_run.get(declared_worker_run_id)
        if declared_result_id == result_id:
            continue
        if declared_result_id is None:
            reason = (
                f"{worker_run_id}: worker_run_ids entry {declared_worker_run_id!r} does not "
                "match a completed worker run for this result_id"
            )
        else:
            reason = (
                f"{worker_run_id}: worker_run_ids entry {declared_worker_run_id!r} points at "
                f"{declared_result_id}, not {result_id}"
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
    failures: list[PlanningIntegrityFailure] = []
    changed_files = payload.get("changed_files")
    if isinstance(changed_files, list) and not _has_nonblank_string(changed_files):
        failures.append(
            PlanningIntegrityFailure(
                "completed_worker_run_invalid_result_schema",
                f"{worker_run_id}: completed result requires nonempty changed_files",
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
    summary = payload.get("summary")
    if isinstance(summary, str) and not summary.strip():
        failures.append(
            PlanningIntegrityFailure(
                "completed_worker_run_invalid_result_schema",
                f"{worker_run_id}: summary must be nonblank",
            )
        )
    if not _payload_has_completion_notes(payload):
        failures.append(
            PlanningIntegrityFailure(
                "completed_worker_run_invalid_result_schema",
                f"{worker_run_id}: completion_notes or handoff_notes must be nonblank",
            )
        )
    return tuple(failures)


def _completed_worker_result_stale_blocker_failures(
    worker_run_id: str,
    payload: dict[object, object],
) -> tuple[PlanningIntegrityFailure, ...]:
    failures: list[PlanningIntegrityFailure] = []
    for key in ("risks", "follow_up_tasks"):
        value = payload.get(key)
        if not isinstance(value, list):
            continue
        for index, item in enumerate(value):
            if not isinstance(item, str):
                continue
            phrase = _stale_completed_result_blocker_phrase(item)
            if phrase is None:
                continue
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_stale_result_blocker",
                    f"{worker_run_id}: {key}[{index}] contains stale blocker phrase: {phrase}",
                )
            )
    return tuple(failures)


def _stale_completed_result_blocker_phrase(value: str) -> str | None:
    normalized = value.lower()
    return next(
        (phrase for phrase in STALE_COMPLETED_RESULT_BLOCKER_PHRASES if phrase in normalized),
        None,
    )


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


def _completed_worker_result_browser_smoke_failures(
    worker_run_id: str,
    payload: dict[object, object],
    *,
    required: bool = False,
) -> tuple[PlanningIntegrityFailure, ...]:
    browser_smoke_results = payload.get("browser_smoke_results")
    if browser_smoke_results is None:
        if required and payload.get("status") == "completed":
            return (
                PlanningIntegrityFailure(
                    "completed_worker_run_missing_browser_smoke",
                    f"{worker_run_id}: browser_smoke_results are required",
                ),
            )
        return ()
    if not isinstance(browser_smoke_results, list):
        return (
            PlanningIntegrityFailure(
                "completed_worker_run_invalid_result_schema",
                f"{worker_run_id}: browser_smoke_results must be a list",
            ),
        )
    failures: list[PlanningIntegrityFailure] = []
    completed = payload.get("status") == "completed"
    if required and completed and not browser_smoke_results:
        failures.append(
            PlanningIntegrityFailure(
                "completed_worker_run_missing_browser_smoke",
                f"{worker_run_id}: browser_smoke_results must include a passed entry",
            )
        )
    for index, value in enumerate(browser_smoke_results):
        if not isinstance(value, dict):
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: browser_smoke_results[{index}] must be an object",
                )
            )
            continue
        status = value.get("status")
        if status not in {"passed", "failed", "blocked"}:
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    (
                        f"{worker_run_id}: browser_smoke_results[{index}].status must be "
                        "passed, failed, or blocked"
                    ),
                )
            )
        elif completed and status != "passed":
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: browser_smoke_results[{index}] did not pass",
                )
            )
        summary = value.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: browser_smoke_results[{index}].summary must be nonblank",
                )
            )
        exit_code = value.get("exit_code")
        if exit_code is not None and not isinstance(exit_code, int):
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: browser_smoke_results[{index}].exit_code must be an integer",
                )
            )
        elif completed and isinstance(exit_code, int) and exit_code != 0:
            failures.append(
                PlanningIntegrityFailure(
                    "completed_worker_run_invalid_result_schema",
                    f"{worker_run_id}: browser_smoke_results[{index}] exit_code is {exit_code}",
                )
            )
        for string_key in ("tool", "command", "url"):
            string_value = value.get(string_key)
            if string_value is not None and (
                not isinstance(string_value, str) or not string_value.strip()
            ):
                failures.append(
                    PlanningIntegrityFailure(
                        "completed_worker_run_invalid_result_schema",
                        (
                            f"{worker_run_id}: browser_smoke_results[{index}].{string_key} "
                            "must be nonblank"
                        ),
                    )
                )
        artifact = value.get("artifact")
        if artifact is not None:
            reason = _worker_result_entry_path_reason(artifact)
            if reason is not None:
                failures.append(
                    PlanningIntegrityFailure(
                        "completed_worker_run_invalid_result_schema",
                        (
                            f"{worker_run_id}: browser_smoke_results[{index}].artifact is "
                            f"unsafe: {reason}"
                        ),
                    )
                )
    return tuple(failures)


def _worker_result_source_hash_failures(
    result_id: str,
    repo_root: Path,
    source_path: object,
    source_sha256: object,
) -> tuple[PlanningIntegrityFailure, ...]:
    if not isinstance(source_path, str) or not source_path.strip():
        return ()
    if not isinstance(source_sha256, str) or not source_sha256.strip():
        return ()
    source_file = _artifact_path(repo_root, source_path)
    if source_file is None or not source_file.is_file():
        return ()
    actual_sha256 = _sha256_file(source_file)
    if actual_sha256 == source_sha256:
        return ()
    return (
        PlanningIntegrityFailure(
            "worker_result_source_hash_drift",
            (
                f"{result_id}: source_path {source_path} hash is {actual_sha256}, "
                f"expected {source_sha256}"
            ),
        ),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contains_stale_test_summary_phrase(value: str) -> bool:
    normalized = value.lower()
    return any(phrase in normalized for phrase in STALE_TEST_SUMMARY_PHRASES)


def _completed_worker_result_artifact_reference_failures(
    worker_run_id: str,
    result_path: str,
    payload: dict[object, object],
) -> tuple[PlanningIntegrityFailure, ...]:
    return ()


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
                AND pa.relationship = ?
          )
        ORDER BY wr.worker_run_id
        """,
        (WORKER_RESULT_ARTIFACT_RELATIONSHIP,),
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


def _missing_ignored_runtime_path_is_clean_checkout(repo_root: Path, artifact_id: str) -> bool:
    value = artifact_id.split("#", 1)[0].replace("\\", "/").strip()
    if not value:
        return False
    root = value.split("/", 1)[0]
    if root not in IGNORED_RUNTIME_ROOTS:
        return False
    return not (repo_root / root).exists()


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


def _check_open_codex_exec_tasks_avoid_controller_owned_paths(
    connection: sqlite3.Connection,
) -> tuple[PlanningIntegrityFailure, ...]:
    rows = connection.execute(
        f"""
        SELECT st.task_id, st.scope_json, st.allowed_paths_json, st.worker_backend
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
    for task_id, scope_json, paths_json, worker_backend in rows:
        if canonical_worker_backend(str(worker_backend)) != "codex_exec":
            continue
        try:
            allowed_paths = json.loads(str(paths_json))
        except json.JSONDecodeError:
            continue
        if not isinstance(allowed_paths, list):
            continue
        for violation in controller_owned_allowed_path_violations(
            allowed_paths,
            scope=_json_object(scope_json),
            worker_backend=str(worker_backend),
        ):
            failures.append(
                PlanningIntegrityFailure(
                    "open_codex_exec_task_allows_controller_owned_path",
                    f"{task_id}: {violation}",
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
