"""Tracked SQLite planning store."""

from __future__ import annotations

import json
import re
import shlex
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

JsonObject = dict[str, Any]
JsonArray = list[Any]
JsonStringArray = list[str]


@dataclass(frozen=True)
class PlanningSchemaIndex:
    table: str
    name: str
    columns: tuple[str, ...]
    unique: bool = False
    partial: bool = False
    where_sql: str | None = None


CURRENT_PLANNING_SCHEMA_VERSION = 4
PLANNING_SCHEMA_MIGRATIONS = (
    (1, "initial_supervisor_planning_schema"),
    (2, "worker_runs_one_nonterminal_per_task_index"),
    (3, "strict_status_and_review_constraints"),
    (4, "strict_commit_link_sha_constraint"),
)
PLAN_STATUSES = frozenset({"active", "blocked", "completed", "abandoned", "superseded"})
CURRENT_QUEUE_PLAN_STATUSES = frozenset({"active", "blocked"})
TERMINAL_PLAN_STATUSES = frozenset({"completed", "abandoned", "superseded"})
MILESTONE_STATUSES = frozenset({"pending", "active", "blocked", "completed", "cancelled"})
OPEN_MILESTONE_STATUSES = frozenset({"pending", "active", "blocked"})
CRITERION_STATUSES = frozenset({"pending", "blocked", "completed", "failed", "cancelled"})
OPEN_CRITERION_STATUSES = frozenset({"pending", "blocked"})
TASK_TYPES = frozenset({"AFK", "HITL"})
TASK_STATUSES = frozenset(
    {"pending", "ready", "running", "blocked", "reviewing", "completed", "failed", "cancelled"}
)
WORKER_RUN_STATUSES = frozenset(
    {"queued", "running", "blocked", "completed", "failed", "cancelled", "needs_review"}
)
NONTERMINAL_WORKER_RUN_STATUSES = WORKER_RUN_STATUSES - {"completed", "failed", "cancelled"}
CLAIM_WORKER_RUN_STATUSES = frozenset({"queued", "running"})
TASK_STATUSES_ALLOWED_WITH_NONTERMINAL_WORKER_RUN = frozenset({"running", "blocked", "reviewing"})
TASK_STATUSES_ALLOWED_TO_START_NONTERMINAL_WORKER_RUN = (
    TASK_STATUSES_ALLOWED_WITH_NONTERMINAL_WORKER_RUN | {"ready"}
)
TERMINAL_TASK_STATUSES = frozenset({"completed", "failed", "cancelled"})
OPEN_TASK_STATUSES = TASK_STATUSES - TERMINAL_TASK_STATUSES
TERMINAL_EVIDENCE_CLEARING_WORKER_RUN_STATUSES = frozenset({"queued", "running"})
FAILURE_WORKER_RUN_STATUSES = frozenset({"blocked", "failed", "cancelled"})
SUCCESSFUL_WORKER_RUN_STATUSES = frozenset({"completed"})
DRIVE_PATH_PATTERN = re.compile(r"^[A-Za-z]:")
FULL_COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHELL_METACHARACTERS = (
    "|",
    "&",
    ";",
    "<",
    ">",
    "`",
    "$(",
)
UV_RUN_READONLY_PREFIX = ("uv", "run", "--no-sync")
SAFE_PYTHON_CHECK_SCRIPTS = frozenset(
    {
        "scripts/check_file_justification.py",
        "scripts/check_planning_integrity.py",
        "scripts/check_protected_files.py",
        "scripts/check_public_repo_hygiene.py",
        "scripts/check_skill_inventory.py",
        "scripts/check_source_inventory.py",
        "scripts/verify.py",
    }
)
SAFE_PYTHON_CHECK_SCRIPT_ARGS = {
    "scripts/check_public_repo_hygiene.py": frozenset({(), ("--publication-ready",)}),
    "scripts/verify.py": frozenset({(), ("--publication-ready",)}),
}
SAFE_CODEX_SUPERVISOR_CLI_READ_COMMANDS = frozenset(
    {
        "--help",
        "goal-contract-render",
        "plan-list",
        "plan-summary",
        "story-loop-status",
        "task-current",
        "task-list",
        "task-show",
        "worker-run-list",
        "worker-run-show",
    }
)

PLANNING_SCHEMA_TABLE_COLUMNS = {
    "schema_migrations": ("version", "name", "applied_at"),
    "plans": (
        "plan_id",
        "slug",
        "title",
        "goal",
        "non_goals_json",
        "context_json",
        "status",
        "priority",
        "owner_agent",
        "superseded_by_plan_id",
        "created_at",
        "updated_at",
    ),
    "plan_milestones": (
        "milestone_id",
        "plan_id",
        "title",
        "status",
        "sort_order",
        "details_json",
    ),
    "plan_acceptance_criteria": (
        "criterion_id",
        "plan_id",
        "description",
        "status",
        "verification_command",
    ),
    "plan_decisions": (
        "decision_id",
        "plan_id",
        "decision",
        "rationale",
        "alternatives_considered",
        "consequences",
        "decided_at",
    ),
    "plan_progress_events": (
        "progress_id",
        "plan_id",
        "event_type",
        "summary",
        "details",
        "linked_artifact_id",
        "occurred_at",
    ),
    "plan_artifact_links": ("plan_id", "artifact_id", "relationship"),
    "plan_commit_links": ("plan_id", "commit_sha", "relationship"),
    "supervisor_tasks": (
        "task_id",
        "plan_id",
        "title",
        "goal",
        "task_type",
        "status",
        "scope_json",
        "out_of_scope_json",
        "acceptance_criteria_json",
        "verification_commands_json",
        "allowed_paths_json",
        "blocked_by_json",
        "worker_backend",
        "review_required",
        "created_at",
        "updated_at",
    ),
    "worker_runs": (
        "worker_run_id",
        "task_id",
        "backend",
        "status",
        "worktree_path",
        "prompt_path",
        "jsonl_path",
        "result_path",
        "started_at",
        "completed_at",
        "failure_class",
        "metadata_json",
    ),
}

PLANNING_SCHEMA_INDEXES = (
    PlanningSchemaIndex("plans", "idx_plans_status", ("status",)),
    PlanningSchemaIndex("plans", "idx_plans_priority", ("priority",)),
    PlanningSchemaIndex("plan_milestones", "idx_plan_milestones_plan_id", ("plan_id",)),
    PlanningSchemaIndex(
        "plan_acceptance_criteria",
        "idx_plan_acceptance_plan_id",
        ("plan_id",),
    ),
    PlanningSchemaIndex("plan_decisions", "idx_plan_decisions_plan_id", ("plan_id",)),
    PlanningSchemaIndex("plan_progress_events", "idx_plan_progress_plan_id", ("plan_id",)),
    PlanningSchemaIndex(
        "plan_progress_events",
        "idx_plan_progress_occurred_at",
        ("occurred_at",),
    ),
    PlanningSchemaIndex("supervisor_tasks", "idx_supervisor_tasks_plan_id", ("plan_id",)),
    PlanningSchemaIndex("supervisor_tasks", "idx_supervisor_tasks_status", ("status",)),
    PlanningSchemaIndex("worker_runs", "idx_worker_runs_task_id", ("task_id",)),
    PlanningSchemaIndex("worker_runs", "idx_worker_runs_status", ("status",)),
    PlanningSchemaIndex(
        "worker_runs",
        "idx_worker_runs_one_nonterminal_per_task",
        ("task_id",),
        unique=True,
        partial=True,
        where_sql="status IN ('queued', 'running', 'blocked', 'needs_review')",
    ),
)

PLANNING_SCHEMA_TABLE_REQUIRED_SQL = {
    "plans": (
        "status text not null check(status in",
        "'active'",
        "'blocked'",
        "'completed'",
        "'abandoned'",
        "'superseded'",
    ),
    "plan_milestones": (
        "status text not null check(status in",
        "'pending'",
        "'active'",
        "'blocked'",
        "'completed'",
        "'cancelled'",
    ),
    "plan_acceptance_criteria": (
        "status text not null check(status in",
        "'pending'",
        "'blocked'",
        "'completed'",
        "'failed'",
        "'cancelled'",
    ),
    "plan_commit_links": (
        "commit_sha text not null check(",
        "length(commit_sha) = 40",
        "commit_sha not glob '*[^0-9a-f]*'",
    ),
    "supervisor_tasks": (
        "task_type text not null check(task_type in ('afk', 'hitl'))",
        "status text not null check(status in",
        "'pending'",
        "'ready'",
        "'running'",
        "'blocked'",
        "'reviewing'",
        "'completed'",
        "'failed'",
        "'cancelled'",
        "review_required integer not null default 1 check(review_required in (0, 1))",
    ),
    "worker_runs": (
        "status text not null check(status in",
        "'queued'",
        "'running'",
        "'blocked'",
        "'completed'",
        "'failed'",
        "'cancelled'",
        "'needs_review'",
    ),
}

CONSTRAINED_TABLE_REBUILD_ORDER = (
    "plans",
    "plan_milestones",
    "plan_acceptance_criteria",
    "plan_decisions",
    "plan_progress_events",
    "plan_artifact_links",
    "plan_commit_links",
    "supervisor_tasks",
    "worker_runs",
)


@dataclass(frozen=True)
class PlanRecord:
    plan_id: str
    slug: str
    title: str
    goal: str
    status: str
    priority: int = 0
    owner_agent: str | None = None
    non_goals: JsonObject = field(default_factory=dict)
    context: JsonObject = field(default_factory=dict)
    superseded_by_plan_id: str | None = None


@dataclass(frozen=True)
class PlanMilestoneRecord:
    milestone_id: str
    plan_id: str
    title: str
    status: str
    sort_order: int = 0
    details: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class PlanAcceptanceCriterionRecord:
    criterion_id: str
    plan_id: str
    description: str
    status: str
    verification_command: str | None = None


@dataclass(frozen=True)
class PlanDecisionRecord:
    decision_id: str
    plan_id: str
    decision: str
    rationale: str
    alternatives_considered: str | None = None
    consequences: str | None = None
    decided_at: datetime | None = None


@dataclass(frozen=True)
class PlanProgressRecord:
    progress_id: str
    plan_id: str
    event_type: str
    summary: str
    details: str | None = None
    linked_artifact_id: str | None = None
    occurred_at: datetime | None = None


@dataclass(frozen=True)
class PlanArtifactLinkRecord:
    plan_id: str
    artifact_id: str
    relationship: str


@dataclass(frozen=True)
class PlanCommitLinkRecord:
    plan_id: str
    commit_sha: str
    relationship: str


@dataclass(frozen=True)
class SupervisorTaskRecord:
    task_id: str
    plan_id: str
    title: str
    goal: str
    task_type: str
    status: str
    scope: JsonObject = field(default_factory=dict)
    out_of_scope: JsonObject = field(default_factory=dict)
    acceptance_criteria: JsonStringArray = field(default_factory=list)
    verification_commands: JsonStringArray = field(default_factory=list)
    allowed_paths: JsonStringArray = field(default_factory=list)
    blocked_by: JsonStringArray = field(default_factory=list)
    worker_backend: str = "codex_exec"
    review_required: bool = True


@dataclass(frozen=True)
class SupervisorTaskSummaryRecord:
    task_id: str
    plan_id: str
    plan_title: str
    plan_status: str
    plan_priority: int
    title: str
    goal: str
    task_type: str
    status: str
    scope: JsonObject
    out_of_scope: JsonObject
    acceptance_criteria: JsonStringArray
    verification_commands: JsonStringArray
    allowed_paths: JsonStringArray
    blocked_by: JsonStringArray
    worker_backend: str
    review_required: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class WorkerRunRecord:
    worker_run_id: str
    task_id: str
    backend: str
    status: str
    worktree_path: str | None = None
    prompt_path: str | None = None
    jsonl_path: str | None = None
    result_path: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    failure_class: str | None = None
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class TaskClaimRecord:
    task: SupervisorTaskSummaryRecord
    worker_run: WorkerRunRecord


@dataclass(frozen=True)
class PlanningQueueSnapshot:
    plans: tuple[PlanRecord, ...]
    tasks: tuple[SupervisorTaskSummaryRecord, ...]
    worker_runs: tuple[WorkerRunRecord, ...]
    criteria: tuple[PlanAcceptanceCriterionRecord, ...]


class PlanningSQLiteStore:
    """Repository wrapper around the tracked planning SQLite database."""

    def __init__(self, path: Path, *, read_only: bool = False) -> None:
        self.path = path
        self.read_only = read_only

    @contextmanager
    def connect(
        self,
        *,
        create: bool = False,
        read_only: bool | None = None,
    ) -> Iterator[sqlite3.Connection]:
        effective_read_only = self.read_only if read_only is None else read_only
        if self.read_only and read_only is False:
            msg = "Cannot override a read-only planning store with read_only=False"
            raise ValueError(msg)
        if create and effective_read_only:
            msg = "Cannot create a database through a read-only planning store"
            raise ValueError(msg)
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path)
        else:
            mode = "ro" if effective_read_only else "rw"
            connection = sqlite3.connect(_sqlite_uri(self.path, mode), uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect(create=True) as connection:
            connection.executescript(PLANNING_SCHEMA_SQL)
            now = _format_datetime(_utc_now())
            _apply_schema_migrations(connection, now)

    def schema_version(self) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT MAX(version) AS version FROM schema_migrations"
            ).fetchone()
        if row is None or row["version"] is None:
            return 0
        return int(row["version"])

    def validate_schema(self) -> None:
        """Fail early when a planning database is not the expected supervisor schema."""

        with self.connect(read_only=True) as connection:
            for table, expected_columns in PLANNING_SCHEMA_TABLE_COLUMNS.items():
                rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
                if not rows:
                    msg = f"planning schema missing table: {table}"
                    raise ValueError(msg)
                actual_columns = {str(row["name"]) for row in rows}
                missing_columns = tuple(
                    column for column in expected_columns if column not in actual_columns
                )
                if missing_columns:
                    missing = ", ".join(missing_columns)
                    msg = f"planning schema table {table} missing column(s): {missing}"
                    raise ValueError(msg)
                required_fragments = PLANNING_SCHEMA_TABLE_REQUIRED_SQL.get(table, ())
                if required_fragments:
                    table_sql_row = connection.execute(
                        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                        (table,),
                    ).fetchone()
                    table_sql = (
                        ""
                        if table_sql_row is None
                        else _normalize_schema_sql(str(table_sql_row["sql"] or ""))
                    )
                    missing_fragments = tuple(
                        fragment for fragment in required_fragments if fragment not in table_sql
                    )
                    if missing_fragments:
                        msg = (
                            f"planning schema table {table} does not contain expected SQL: "
                            f"{missing_fragments[0]}"
                        )
                        raise ValueError(msg)
            for expected_index in PLANNING_SCHEMA_INDEXES:
                rows = connection.execute(f"PRAGMA index_list({expected_index.table})").fetchall()
                indexes_by_name = {str(row["name"]): row for row in rows}
                row = indexes_by_name.get(expected_index.name)
                if row is None:
                    msg = (
                        f"planning schema table {expected_index.table} missing index: "
                        f"{expected_index.name}"
                    )
                    raise ValueError(msg)
                unique = bool(row["unique"])
                if unique != expected_index.unique:
                    msg = (
                        f"planning schema index {expected_index.name} unique={unique} does not "
                        f"match expected {expected_index.unique}"
                    )
                    raise ValueError(msg)
                partial = bool(row["partial"])
                if partial != expected_index.partial:
                    msg = (
                        f"planning schema index {expected_index.name} partial={partial} does not "
                        f"match expected {expected_index.partial}"
                    )
                    raise ValueError(msg)
                index_columns = tuple(
                    str(index_row["name"])
                    for index_row in connection.execute(
                        f"PRAGMA index_info({expected_index.name})"
                    ).fetchall()
                )
                if index_columns != expected_index.columns:
                    msg = (
                        f"planning schema index {expected_index.name} columns {index_columns} "
                        f"do not match expected {expected_index.columns}"
                    )
                    raise ValueError(msg)
                if expected_index.where_sql is not None:
                    expected_where = _normalize_schema_sql(f"WHERE {expected_index.where_sql}")
                    index_sql_row = connection.execute(
                        "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
                        (expected_index.name,),
                    ).fetchone()
                    actual_sql = "" if index_sql_row is None else str(index_sql_row["sql"] or "")
                    if expected_where not in _normalize_schema_sql(actual_sql):
                        msg = (
                            f"planning schema index {expected_index.name} predicate does not "
                            f"match expected {expected_index.where_sql}"
                        )
                        raise ValueError(msg)
            row = connection.execute(
                "SELECT MAX(version) AS version FROM schema_migrations"
            ).fetchone()
            version = 0 if row is None or row["version"] is None else int(row["version"])
            if version != CURRENT_PLANNING_SCHEMA_VERSION:
                msg = (
                    f"planning schema version {version} does not match expected "
                    f"{CURRENT_PLANNING_SCHEMA_VERSION}"
                )
                raise ValueError(msg)

    def upsert_plan(self, record: PlanRecord) -> None:
        _validate_required(record.plan_id, "plan_id")
        _validate_required(record.slug, "slug")
        _validate_required(record.title, "title")
        _validate_required(record.goal, "goal")
        _validate_required(record.status, "status")
        _validate_choice(record.status, PLAN_STATUSES, "status")
        now = _format_datetime(_utc_now())
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            _validate_plan_can_enter_status(connection, record.plan_id, record.status)
            connection.execute(
                """
                INSERT INTO plans (
                    plan_id, slug, title, goal, non_goals_json, context_json, status,
                    priority, owner_agent, superseded_by_plan_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plan_id) DO UPDATE SET
                    slug = excluded.slug,
                    title = excluded.title,
                    goal = excluded.goal,
                    non_goals_json = excluded.non_goals_json,
                    context_json = excluded.context_json,
                    status = excluded.status,
                    priority = excluded.priority,
                    owner_agent = excluded.owner_agent,
                    superseded_by_plan_id = excluded.superseded_by_plan_id,
                    updated_at = excluded.updated_at
                """,
                (
                    record.plan_id,
                    record.slug,
                    record.title,
                    record.goal,
                    _dump_json(record.non_goals),
                    _dump_json(record.context),
                    record.status,
                    record.priority,
                    record.owner_agent,
                    record.superseded_by_plan_id,
                    now,
                    now,
                ),
            )

    def update_plan_status(
        self,
        plan_id: str,
        status: str,
        *,
        superseded_by_plan_id: str | None = None,
    ) -> None:
        _validate_required(plan_id, "plan_id")
        _validate_required(status, "status")
        _validate_choice(status, PLAN_STATUSES, "status")
        now = _format_datetime(_utc_now())
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT plan_id FROM plans WHERE plan_id = ?",
                (plan_id,),
            ).fetchone()
            _raise_missing(0 if row is None else 1, "plan", plan_id)
            _validate_plan_can_enter_status(connection, plan_id, status)
            cursor = connection.execute(
                """
                UPDATE plans
                SET status = ?, superseded_by_plan_id = ?, updated_at = ?
                WHERE plan_id = ?
                """,
                (status, superseded_by_plan_id, now, plan_id),
            )
            _raise_missing(cursor.rowcount, "plan", plan_id)

    def list_plans(self, *, status: str | None = None) -> tuple[PlanRecord, ...]:
        with self.connect() as connection:
            return _list_plans(connection, status=status)

    def upsert_plan_milestone(self, record: PlanMilestoneRecord) -> None:
        _validate_required(record.milestone_id, "milestone_id")
        _validate_required(record.plan_id, "plan_id")
        _validate_required(record.title, "title")
        _validate_required(record.status, "status")
        _validate_choice(record.status, MILESTONE_STATUSES, "status")
        now = _format_datetime(_utc_now())
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO plan_milestones (
                    milestone_id, plan_id, title, status, sort_order, details_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(milestone_id) DO UPDATE SET
                    plan_id = excluded.plan_id,
                    title = excluded.title,
                    status = excluded.status,
                    sort_order = excluded.sort_order,
                    details_json = excluded.details_json
                """,
                (
                    record.milestone_id,
                    record.plan_id,
                    record.title,
                    record.status,
                    record.sort_order,
                    _dump_json(record.details),
                ),
            )
            _touch_plan(connection, record.plan_id, now)

    def update_plan_milestone_status(self, milestone_id: str, status: str) -> None:
        _validate_required(milestone_id, "milestone_id")
        _validate_required(status, "status")
        _validate_choice(status, MILESTONE_STATUSES, "status")
        now = _format_datetime(_utc_now())
        with self.connect() as connection:
            row = connection.execute(
                "SELECT plan_id FROM plan_milestones WHERE milestone_id = ?",
                (milestone_id,),
            ).fetchone()
            _raise_missing(0 if row is None else 1, "milestone", milestone_id)
            connection.execute(
                "UPDATE plan_milestones SET status = ? WHERE milestone_id = ?",
                (status, milestone_id),
            )
            _touch_plan(connection, str(row["plan_id"]), now)

    def list_plan_milestones(
        self,
        *,
        plan_id: str | None = None,
    ) -> tuple[PlanMilestoneRecord, ...]:
        query = "SELECT * FROM plan_milestones"
        parameters: list[object] = []
        if plan_id is not None:
            query += " WHERE plan_id = ?"
            parameters.append(plan_id)
        query += " ORDER BY plan_id, sort_order, milestone_id"
        with self.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(_plan_milestone_from_row(row) for row in rows)

    def upsert_plan_acceptance_criterion(self, record: PlanAcceptanceCriterionRecord) -> None:
        _validate_required(record.criterion_id, "criterion_id")
        _validate_required(record.plan_id, "plan_id")
        _validate_required(record.description, "description")
        _validate_required(record.status, "status")
        _validate_choice(record.status, CRITERION_STATUSES, "status")
        if record.verification_command is not None and record.verification_command.strip():
            reason = unsafe_verification_command_reason(record.verification_command)
            if reason:
                msg = (
                    "verification_command contains unsafe verification command: "
                    f"{record.verification_command} ({reason})"
                )
                raise ValueError(msg)
        now = _format_datetime(_utc_now())
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO plan_acceptance_criteria (
                    criterion_id, plan_id, description, status, verification_command
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(criterion_id) DO UPDATE SET
                    plan_id = excluded.plan_id,
                    description = excluded.description,
                    status = excluded.status,
                    verification_command = excluded.verification_command
                """,
                (
                    record.criterion_id,
                    record.plan_id,
                    record.description,
                    record.status,
                    record.verification_command,
                ),
            )
            _touch_plan(connection, record.plan_id, now)

    def update_plan_acceptance_criterion_status(self, criterion_id: str, status: str) -> None:
        _validate_required(criterion_id, "criterion_id")
        _validate_required(status, "status")
        _validate_choice(status, CRITERION_STATUSES, "status")
        now = _format_datetime(_utc_now())
        with self.connect() as connection:
            row = connection.execute(
                "SELECT plan_id FROM plan_acceptance_criteria WHERE criterion_id = ?",
                (criterion_id,),
            ).fetchone()
            _raise_missing(0 if row is None else 1, "criterion", criterion_id)
            connection.execute(
                "UPDATE plan_acceptance_criteria SET status = ? WHERE criterion_id = ?",
                (status, criterion_id),
            )
            _touch_plan(connection, str(row["plan_id"]), now)

    def list_plan_acceptance_criteria(
        self,
        *,
        plan_id: str | None = None,
    ) -> tuple[PlanAcceptanceCriterionRecord, ...]:
        with self.connect() as connection:
            return _list_plan_acceptance_criteria(connection, plan_id=plan_id)

    def list_supervisor_tasks(
        self,
        *,
        status: str | None = None,
        active_plans_only: bool = False,
        current_queue_plans_only: bool = False,
        task_type: str | None = None,
        unblocked_only: bool = False,
    ) -> tuple[SupervisorTaskSummaryRecord, ...]:
        if active_plans_only and current_queue_plans_only:
            msg = "active_plans_only and current_queue_plans_only are mutually exclusive"
            raise ValueError(msg)
        with self.connect() as connection:
            tasks = _list_supervisor_task_summaries(
                connection,
                status=status,
                active_plans_only=active_plans_only,
                current_queue_plans_only=current_queue_plans_only,
                task_type=task_type,
            )
            if unblocked_only:
                blocker_lookup = _list_supervisor_task_summaries(
                    connection,
                    active_plans_only=active_plans_only,
                    current_queue_plans_only=current_queue_plans_only,
                )
                tasks = tuple(
                    task for task in tasks if not has_unresolved_task_blockers(task, blocker_lookup)
                )
        return tasks

    def next_ready_afk_task(self) -> SupervisorTaskSummaryRecord | None:
        with self.connect() as connection:
            tasks = _list_supervisor_task_summaries(connection, active_plans_only=False)
            worker_runs = _list_worker_runs(connection)
            return next(
                (task for task in tasks if is_executable_afk_task(task, tasks, worker_runs)),
                None,
            )

    def read_queue_snapshot(self) -> PlanningQueueSnapshot:
        """Read queue status inputs from a single SQLite snapshot."""

        with self.connect() as connection:
            return PlanningQueueSnapshot(
                plans=_list_plans(connection),
                tasks=_list_supervisor_task_summaries(connection),
                worker_runs=_list_worker_runs(connection),
                criteria=_list_plan_acceptance_criteria(connection),
            )

    def upsert_supervisor_task(
        self,
        record: SupervisorTaskRecord,
        *,
        validate_current_queue_contract: bool = False,
    ) -> None:
        _validate_required(record.task_id, "task_id")
        _validate_required(record.plan_id, "plan_id")
        _validate_required(record.title, "title")
        _validate_required(record.goal, "goal")
        _validate_required(record.task_type, "task_type")
        _validate_required(record.status, "status")
        _validate_required(record.worker_backend, "worker_backend")
        _validate_choice(record.task_type, TASK_TYPES, "task_type")
        _validate_choice(record.status, TASK_STATUSES, "status")
        _validate_string_array(record.acceptance_criteria, "acceptance_criteria")
        _validate_string_array(record.verification_commands, "verification_commands")
        _validate_string_array(record.allowed_paths, "allowed_paths")
        _validate_repo_relative_path_patterns(record.allowed_paths, "allowed_paths")
        _validate_string_array(record.blocked_by, "blocked_by")
        now = _format_datetime(_utc_now())
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT plan_id FROM supervisor_tasks WHERE task_id = ?",
                (record.task_id,),
            ).fetchone()
            previous_plan_id = str(existing["plan_id"]) if existing is not None else None
            if previous_plan_id is not None and previous_plan_id != record.plan_id:
                worker_run_count = connection.execute(
                    "SELECT COUNT(*) AS total FROM worker_runs WHERE task_id = ?",
                    (record.task_id,),
                ).fetchone()
                if int(worker_run_count["total"]) > 0:
                    msg = (
                        f"cannot move task {record.task_id} from plan {previous_plan_id} "
                        f"to plan {record.plan_id} while worker history exists"
                    )
                    raise ValueError(msg)
            if record.status not in TASK_STATUSES_ALLOWED_WITH_NONTERMINAL_WORKER_RUN:
                active_run = _first_nonterminal_worker_run_for_task(connection, record.task_id)
                if active_run is not None:
                    msg = (
                        f"cannot set task {record.task_id} to {record.status} while worker run "
                        f"{active_run['worker_run_id']} is {active_run['status']}"
                    )
                    raise ValueError(msg)
            if validate_current_queue_contract:
                _validate_task_contract_for_current_queue_plan(connection, record)
            connection.execute(
                """
                INSERT INTO supervisor_tasks (
                    task_id, plan_id, title, goal, task_type, status, scope_json,
                    out_of_scope_json, acceptance_criteria_json, verification_commands_json,
                    allowed_paths_json, blocked_by_json, worker_backend, review_required,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    plan_id = excluded.plan_id,
                    title = excluded.title,
                    goal = excluded.goal,
                    task_type = excluded.task_type,
                    status = excluded.status,
                    scope_json = excluded.scope_json,
                    out_of_scope_json = excluded.out_of_scope_json,
                    acceptance_criteria_json = excluded.acceptance_criteria_json,
                    verification_commands_json = excluded.verification_commands_json,
                    allowed_paths_json = excluded.allowed_paths_json,
                    blocked_by_json = excluded.blocked_by_json,
                    worker_backend = excluded.worker_backend,
                    review_required = excluded.review_required,
                    updated_at = excluded.updated_at
                """,
                (
                    record.task_id,
                    record.plan_id,
                    record.title,
                    record.goal,
                    record.task_type,
                    record.status,
                    _dump_json(record.scope),
                    _dump_json(record.out_of_scope),
                    _dump_json(record.acceptance_criteria),
                    _dump_json(record.verification_commands),
                    _dump_json(record.allowed_paths),
                    _dump_json(record.blocked_by),
                    record.worker_backend,
                    int(record.review_required),
                    now,
                    now,
                ),
            )
            if previous_plan_id is not None and previous_plan_id != record.plan_id:
                _touch_plan(connection, previous_plan_id, now)
            _touch_plan(connection, record.plan_id, now)

    def update_supervisor_task_status(self, task_id: str, status: str) -> None:
        _validate_required(task_id, "task_id")
        _validate_required(status, "status")
        _validate_choice(status, TASK_STATUSES, "status")
        now = _format_datetime(_utc_now())
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM supervisor_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            _raise_missing(0 if row is None else 1, "task", task_id)
            summary = _get_supervisor_task_summary(connection, task_id)
            if summary is not None:
                _validate_status_transition_contract_for_current_queue_plan(
                    connection,
                    summary,
                    status,
                )
            if status not in TASK_STATUSES_ALLOWED_WITH_NONTERMINAL_WORKER_RUN:
                active_run = _first_nonterminal_worker_run_for_task(connection, task_id)
                if active_run is not None:
                    msg = (
                        f"cannot set task {task_id} to {status} while worker run "
                        f"{active_run['worker_run_id']} is {active_run['status']}"
                    )
                    raise ValueError(msg)
            connection.execute(
                "UPDATE supervisor_tasks SET status = ?, updated_at = ? WHERE task_id = ?",
                (status, now, task_id),
            )
            _touch_plan(connection, str(row["plan_id"]), now)

    def add_plan_decision(self, record: PlanDecisionRecord) -> None:
        _validate_required(record.decision_id, "decision_id")
        _validate_required(record.plan_id, "plan_id")
        _validate_required(record.decision, "decision")
        _validate_required(record.rationale, "rationale")
        decided_at = _format_datetime(record.decided_at or _utc_now())
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO plan_decisions (
                    decision_id, plan_id, decision, rationale, alternatives_considered,
                    consequences, decided_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.decision_id,
                    record.plan_id,
                    record.decision,
                    record.rationale,
                    record.alternatives_considered,
                    record.consequences,
                    decided_at,
                ),
            )
            _touch_plan(connection, record.plan_id, decided_at)

    def list_plan_decisions(
        self,
        *,
        plan_id: str | None = None,
    ) -> tuple[PlanDecisionRecord, ...]:
        query = "SELECT * FROM plan_decisions"
        parameters: list[object] = []
        if plan_id is not None:
            query += " WHERE plan_id = ?"
            parameters.append(plan_id)
        query += " ORDER BY decided_at DESC, decision_id"
        with self.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(_plan_decision_from_row(row) for row in rows)

    def add_plan_progress(self, record: PlanProgressRecord) -> None:
        _validate_required(record.progress_id, "progress_id")
        _validate_required(record.plan_id, "plan_id")
        _validate_required(record.event_type, "event_type")
        _validate_required(record.summary, "summary")
        if record.linked_artifact_id is not None:
            _validate_artifact_id(record.linked_artifact_id, "linked_artifact_id")
        occurred_at = _format_datetime(record.occurred_at or _utc_now())
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO plan_progress_events (
                    progress_id, plan_id, event_type, summary, details,
                    linked_artifact_id, occurred_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.progress_id,
                    record.plan_id,
                    record.event_type,
                    record.summary,
                    record.details,
                    record.linked_artifact_id,
                    occurred_at,
                ),
            )
            if record.linked_artifact_id is not None:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO plan_artifact_links(plan_id, artifact_id, relationship)
                    VALUES (?, ?, ?)
                    """,
                    (record.plan_id, record.linked_artifact_id, "progress-linked-artifact"),
                )
            _touch_plan(connection, record.plan_id, occurred_at)

    def add_plan_progress_with_artifact_links(
        self,
        progress: PlanProgressRecord,
        artifact_links: Iterable[PlanArtifactLinkRecord],
    ) -> None:
        _validate_required(progress.progress_id, "progress_id")
        _validate_required(progress.plan_id, "plan_id")
        _validate_required(progress.event_type, "event_type")
        _validate_required(progress.summary, "summary")
        artifact_link_tuple = tuple(artifact_links)
        if progress.linked_artifact_id is not None and not any(
            link.artifact_id == progress.linked_artifact_id for link in artifact_link_tuple
        ):
            artifact_link_tuple = (
                *artifact_link_tuple,
                PlanArtifactLinkRecord(
                    plan_id=progress.plan_id,
                    artifact_id=progress.linked_artifact_id,
                    relationship="progress-linked-artifact",
                ),
            )
        for artifact_link in artifact_link_tuple:
            _validate_required(artifact_link.plan_id, "artifact_link.plan_id")
            _validate_required(artifact_link.artifact_id, "artifact_link.artifact_id")
            _validate_required(artifact_link.relationship, "artifact_link.relationship")
            _validate_artifact_id(artifact_link.artifact_id, "artifact_link.artifact_id")
            if artifact_link.plan_id != progress.plan_id:
                msg = (
                    "Artifact links recorded with story progress must use the progress plan_id: "
                    f"{progress.plan_id}"
                )
                raise ValueError(msg)
        occurred_at = _format_datetime(progress.occurred_at or _utc_now())
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO plan_progress_events (
                    progress_id, plan_id, event_type, summary, details,
                    linked_artifact_id, occurred_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    progress.progress_id,
                    progress.plan_id,
                    progress.event_type,
                    progress.summary,
                    progress.details,
                    progress.linked_artifact_id,
                    occurred_at,
                ),
            )
            for artifact_link in artifact_link_tuple:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO plan_artifact_links(plan_id, artifact_id, relationship)
                    VALUES (?, ?, ?)
                    """,
                    (
                        artifact_link.plan_id,
                        artifact_link.artifact_id,
                        artifact_link.relationship,
                    ),
                )
            _touch_plan(connection, progress.plan_id, occurred_at)

    def list_plan_progress(
        self,
        *,
        plan_id: str | None = None,
    ) -> tuple[PlanProgressRecord, ...]:
        query = "SELECT * FROM plan_progress_events"
        parameters: list[object] = []
        if plan_id is not None:
            query += " WHERE plan_id = ?"
            parameters.append(plan_id)
        query += " ORDER BY occurred_at DESC, progress_id"
        with self.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(_plan_progress_from_row(row) for row in rows)

    def add_plan_artifact_link(self, record: PlanArtifactLinkRecord) -> None:
        _validate_required(record.plan_id, "plan_id")
        _validate_required(record.artifact_id, "artifact_id")
        _validate_required(record.relationship, "relationship")
        _validate_artifact_id(record.artifact_id, "artifact_id")
        now = _format_datetime(_utc_now())
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO plan_artifact_links(plan_id, artifact_id, relationship)
                VALUES (?, ?, ?)
                """,
                (record.plan_id, record.artifact_id, record.relationship),
            )
            if cursor.rowcount:
                _touch_plan(connection, record.plan_id, now)

    def list_plan_artifact_links(
        self,
        *,
        plan_id: str | None = None,
    ) -> tuple[PlanArtifactLinkRecord, ...]:
        query = "SELECT * FROM plan_artifact_links"
        parameters: list[object] = []
        if plan_id is not None:
            query += " WHERE plan_id = ?"
            parameters.append(plan_id)
        query += " ORDER BY plan_id, artifact_id, relationship"
        with self.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(_plan_artifact_link_from_row(row) for row in rows)

    def add_plan_commit_link(self, record: PlanCommitLinkRecord) -> None:
        _validate_required(record.plan_id, "plan_id")
        _validate_required(record.commit_sha, "commit_sha")
        _validate_commit_sha(record.commit_sha)
        _validate_required(record.relationship, "relationship")
        now = _format_datetime(_utc_now())
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO plan_commit_links(plan_id, commit_sha, relationship)
                VALUES (?, ?, ?)
                """,
                (record.plan_id, record.commit_sha, record.relationship),
            )
            if cursor.rowcount:
                _touch_plan(connection, record.plan_id, now)

    def delete_plan_commit_link(self, record: PlanCommitLinkRecord) -> bool:
        _validate_required(record.plan_id, "plan_id")
        _validate_required(record.commit_sha, "commit_sha")
        _validate_commit_sha(record.commit_sha)
        _validate_required(record.relationship, "relationship")
        with self.connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM plan_commit_links
                WHERE plan_id = ? AND commit_sha = ? AND relationship = ?
                """,
                (record.plan_id, record.commit_sha, record.relationship),
            )
            if cursor.rowcount:
                now = _format_datetime(_utc_now())
                _touch_plan(connection, record.plan_id, now)
                return True
            return False

    def list_plan_commit_links(
        self,
        *,
        plan_id: str | None = None,
    ) -> tuple[PlanCommitLinkRecord, ...]:
        query = "SELECT * FROM plan_commit_links"
        parameters: list[object] = []
        if plan_id is not None:
            query += " WHERE plan_id = ?"
            parameters.append(plan_id)
        query += " ORDER BY plan_id, commit_sha, relationship"
        with self.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(_plan_commit_link_from_row(row) for row in rows)

    def upsert_worker_run(self, record: WorkerRunRecord) -> None:
        _validate_required(record.worker_run_id, "worker_run_id")
        _validate_required(record.task_id, "task_id")
        _validate_required(record.backend, "backend")
        _validate_required(record.status, "status")
        _validate_choice(record.status, WORKER_RUN_STATUSES, "status")
        result_path = (
            None
            if record.status in TERMINAL_EVIDENCE_CLEARING_WORKER_RUN_STATUSES
            else record.result_path
        )
        completed_at = (
            None
            if record.status in TERMINAL_EVIDENCE_CLEARING_WORKER_RUN_STATUSES
            else record.completed_at
        )
        failure_class = (
            record.failure_class if record.status in FAILURE_WORKER_RUN_STATUSES else None
        )
        if record.status == "completed" and not result_path:
            msg = "completed worker runs require result_path"
            raise ValueError(msg)
        if record.status == "completed":
            _validate_worker_result_path(result_path)
        now = _format_datetime(_utc_now())
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT task_id FROM worker_runs WHERE worker_run_id = ?",
                (record.worker_run_id,),
            ).fetchone()
            if existing is not None and str(existing["task_id"]) != record.task_id:
                msg = (
                    f"worker_run_id {record.worker_run_id} is already attached to task "
                    f"{existing['task_id']}"
                )
                raise ValueError(msg)
            task_status_row = _task_status_row(connection, record.task_id)
            _raise_missing(0 if task_status_row is None else 1, "task", record.task_id)
            if record.status in NONTERMINAL_WORKER_RUN_STATUSES:
                _validate_worker_run_can_be_nonterminal(
                    connection,
                    task_id=record.task_id,
                    worker_run_id=record.worker_run_id,
                    worker_status=record.status,
                )
                active_run = _first_nonterminal_worker_run_for_task(
                    connection,
                    record.task_id,
                    excluding_worker_run_id=record.worker_run_id,
                )
                if active_run is not None:
                    msg = (
                        f"task {record.task_id} already has nonterminal worker run "
                        f"{active_run['worker_run_id']} ({active_run['status']})"
                    )
                    raise ValueError(msg)
            stored_task_id = str(existing["task_id"]) if existing is not None else record.task_id
            connection.execute(
                """
                INSERT INTO worker_runs (
                    worker_run_id, task_id, backend, status, worktree_path, prompt_path,
                    jsonl_path, result_path, started_at, completed_at, failure_class,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(worker_run_id) DO UPDATE SET
                    backend = excluded.backend,
                    status = excluded.status,
                    worktree_path = excluded.worktree_path,
                    prompt_path = excluded.prompt_path,
                    jsonl_path = excluded.jsonl_path,
                    result_path = excluded.result_path,
                    started_at = excluded.started_at,
                    completed_at = excluded.completed_at,
                    failure_class = excluded.failure_class,
                    metadata_json = excluded.metadata_json
                """,
                (
                    record.worker_run_id,
                    record.task_id,
                    record.backend,
                    record.status,
                    record.worktree_path,
                    record.prompt_path,
                    record.jsonl_path,
                    result_path,
                    record.started_at,
                    completed_at,
                    failure_class,
                    _dump_json(record.metadata),
                ),
            )
            _sync_task_and_plan_for_worker_run(connection, stored_task_id, record.status, now)
            if record.status == "completed" and result_path is not None:
                _link_worker_result_artifact(connection, stored_task_id, result_path)

    def claim_next_ready_afk_task(
        self,
        *,
        worker_run_id: str,
        backend: str,
        task_id: str | None = None,
        status: str = "running",
        worktree_path: str | None = None,
        prompt_path: str | None = None,
        jsonl_path: str | None = None,
        metadata: JsonObject | None = None,
    ) -> TaskClaimRecord | None:
        _validate_required(worker_run_id, "worker_run_id")
        _validate_required(backend, "backend")
        if task_id is not None:
            _validate_required(task_id, "task_id")
        _validate_required(status, "status")
        _validate_choice(status, CLAIM_WORKER_RUN_STATUSES, "status")
        now = _format_datetime(_utc_now())
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            tasks = _list_supervisor_task_summaries(connection, active_plans_only=False)
            worker_runs = _list_worker_runs(connection)
            task = next(
                (
                    candidate
                    for candidate in tasks
                    if is_executable_afk_task(candidate, tasks, worker_runs)
                ),
                None,
            )
            if task is not None and task_id is not None and task.task_id != task_id:
                return None
            if task is None:
                return None
            cursor = connection.execute(
                """
                UPDATE supervisor_tasks
                SET status = 'running',
                    updated_at = ?
                WHERE task_id = ?
                  AND status = 'ready'
                """,
                (now, task.task_id),
            )
            if cursor.rowcount == 0:
                return None
            connection.execute(
                """
                INSERT INTO worker_runs (
                    worker_run_id, task_id, backend, status, worktree_path, prompt_path,
                    jsonl_path, result_path, started_at, completed_at, failure_class,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, NULL, ?)
                """,
                (
                    worker_run_id,
                    task.task_id,
                    backend,
                    status,
                    worktree_path,
                    prompt_path,
                    jsonl_path,
                    now,
                    _dump_json(metadata or {}),
                ),
            )
            _touch_plan(connection, task.plan_id, now)
            claimed_task = _get_supervisor_task_summary(connection, task.task_id)
            worker_run = WorkerRunRecord(
                worker_run_id=worker_run_id,
                task_id=task.task_id,
                backend=backend,
                status=status,
                worktree_path=worktree_path,
                prompt_path=prompt_path,
                jsonl_path=jsonl_path,
                started_at=now,
                metadata=metadata or {},
            )
        return TaskClaimRecord(task=claimed_task, worker_run=worker_run)

    def update_worker_run_status(
        self,
        worker_run_id: str,
        status: str,
        *,
        failure_class: str | None = None,
        completed_at: str | None = None,
        result_path: str | None = None,
    ) -> None:
        _validate_required(worker_run_id, "worker_run_id")
        _validate_required(status, "status")
        _validate_choice(status, WORKER_RUN_STATUSES, "status")
        if result_path is not None and not result_path.strip():
            msg = "result_path must be nonblank when provided"
            raise ValueError(msg)
        normalized_result_path = result_path.strip() if result_path is not None else None
        now = _format_datetime(_utc_now())
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT task_id, result_path FROM worker_runs WHERE worker_run_id = ?",
                (worker_run_id,),
            ).fetchone()
            _raise_missing(0 if row is None else 1, "worker_run", worker_run_id)
            clears_terminal_evidence = status in TERMINAL_EVIDENCE_CLEARING_WORKER_RUN_STATUSES
            effective_result_path = (
                None if clears_terminal_evidence else normalized_result_path or row["result_path"]
            )
            if status == "completed" and not effective_result_path:
                msg = "completed worker runs require result_path"
                raise ValueError(msg)
            if status == "completed":
                _validate_worker_result_path(effective_result_path)
            if status in NONTERMINAL_WORKER_RUN_STATUSES:
                _validate_worker_run_can_be_nonterminal(
                    connection,
                    task_id=str(row["task_id"]),
                    worker_run_id=worker_run_id,
                    worker_status=status,
                )
                active_run = _first_nonterminal_worker_run_for_task(
                    connection,
                    str(row["task_id"]),
                    excluding_worker_run_id=worker_run_id,
                )
                if active_run is not None:
                    msg = (
                        f"task {row['task_id']} already has nonterminal worker run "
                        f"{active_run['worker_run_id']} ({active_run['status']})"
                    )
                    raise ValueError(msg)
            stored_failure_class = failure_class if status in FAILURE_WORKER_RUN_STATUSES else None
            stored_completed_at = None if clears_terminal_evidence else completed_at
            stored_result_path = None if clears_terminal_evidence else normalized_result_path
            cursor = connection.execute(
                """
                UPDATE worker_runs
                SET status = ?,
                    failure_class = CASE
                        WHEN ? THEN NULL
                        WHEN ? THEN ?
                        ELSE failure_class
                    END,
                    completed_at = CASE
                        WHEN ? THEN NULL
                        ELSE COALESCE(?, completed_at)
                    END,
                    result_path = CASE
                        WHEN ? THEN NULL
                        ELSE COALESCE(?, result_path)
                    END
                WHERE worker_run_id = ?
                """,
                (
                    status,
                    clears_terminal_evidence,
                    status not in FAILURE_WORKER_RUN_STATUSES,
                    stored_failure_class,
                    clears_terminal_evidence,
                    stored_completed_at,
                    clears_terminal_evidence,
                    stored_result_path,
                    worker_run_id,
                ),
            )
            _raise_missing(cursor.rowcount, "worker_run", worker_run_id)
            _sync_task_and_plan_for_worker_run(connection, str(row["task_id"]), status, now)
            if status == "completed" and effective_result_path is not None:
                _link_worker_result_artifact(
                    connection,
                    str(row["task_id"]),
                    str(effective_result_path),
                )

    def list_worker_runs(
        self,
        *,
        task_id: str | None = None,
    ) -> tuple[WorkerRunRecord, ...]:
        query = "SELECT * FROM worker_runs"
        parameters: list[object] = []
        if task_id is not None:
            query += " WHERE task_id = ?"
            parameters.append(task_id)
        query += " ORDER BY started_at DESC, worker_run_id"
        with self.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(_worker_run_from_row(row) for row in rows)


def initialize_planning_database(path: Path) -> PlanningSQLiteStore:
    """Initialize and return the planning store."""

    store = PlanningSQLiteStore(path)
    store.initialize()
    store.validate_schema()
    return store


def open_existing_planning_database(
    path: Path,
    *,
    read_only: bool = True,
    validate: bool = False,
) -> PlanningSQLiteStore:
    """Return a planning store without creating or migrating the database."""

    store = PlanningSQLiteStore(path, read_only=read_only)
    if validate:
        store.validate_schema()
    return store


def has_unresolved_task_blockers(
    task: SupervisorTaskSummaryRecord,
    tasks: Iterable[SupervisorTaskSummaryRecord],
) -> bool:
    """Return whether a task has unresolved dependency blockers."""

    return bool(unresolved_task_blockers(task, tasks))


def unresolved_task_blockers(
    task: SupervisorTaskSummaryRecord,
    tasks: Iterable[SupervisorTaskSummaryRecord],
) -> tuple[str, ...]:
    """Return dependency blocker IDs that are missing or not completed."""

    tasks_by_id = {candidate.task_id: candidate for candidate in tasks}
    blockers: list[str] = []
    for blocker in task.blocked_by:
        blocker_id = str(blocker)
        blocker_task = tasks_by_id.get(blocker_id)
        if blocker_task is None or blocker_task.status != "completed":
            blockers.append(blocker_id)
    return tuple(blockers)


def missing_execution_contract_fields(task: SupervisorTaskSummaryRecord) -> tuple[str, ...]:
    """Return task contract fields that must exist before AFK execution."""

    missing: list[str] = []
    if not _contains_nonblank_string(task.acceptance_criteria):
        missing.append("acceptance_criteria")
    if not _contains_nonblank_string(task.verification_commands) or any(
        unsafe_verification_command_reason(command)
        for command in task.verification_commands
        if isinstance(command, str) and command.strip()
    ):
        missing.append("verification_commands")
    if not _contains_nonblank_string(task.allowed_paths) or unsafe_repo_relative_path_patterns(
        task.allowed_paths
    ):
        missing.append("allowed_paths")
    return tuple(missing)


def is_executable_afk_task(
    task: SupervisorTaskSummaryRecord,
    tasks: Iterable[SupervisorTaskSummaryRecord],
    worker_runs: Iterable[WorkerRunRecord] = (),
) -> bool:
    """Return whether a task is ready for autonomous execution."""

    return (
        task.plan_status == "active"
        and task.task_type == "AFK"
        and task.status == "ready"
        and not has_unresolved_task_blockers(task, tasks)
        and not missing_execution_contract_fields(task)
        and not has_nonterminal_worker_run(task.task_id, worker_runs)
    )


def has_nonterminal_worker_run(
    task_id: str,
    worker_runs: Iterable[WorkerRunRecord],
) -> bool:
    """Return whether a task already has a queued/running/review worker run."""

    return any(
        run.task_id == task_id and run.status in NONTERMINAL_WORKER_RUN_STATUSES
        for run in worker_runs
    )


def has_completed_worker_run(
    task_id: str,
    worker_runs: Iterable[WorkerRunRecord],
) -> bool:
    """Return whether a task already has completed worker evidence."""

    return any(
        run.task_id == task_id and run.status in SUCCESSFUL_WORKER_RUN_STATUSES
        for run in worker_runs
    )


def _contains_nonblank_string(values: Iterable[object]) -> bool:
    return any(isinstance(value, str) and value.strip() for value in values)


def unsafe_repo_relative_path_patterns(values: Iterable[object]) -> tuple[str, ...]:
    """Return allowed-path contract values that are not safe repo-relative patterns."""

    failures: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        raw_value = value.strip()
        if not raw_value:
            continue
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
        parts = tuple(part for part in normalized.split("/") if part)
        if ".." in parts:
            failures.append(f"{raw_value}: parent traversal is not allowed")
    return tuple(failures)


def unsafe_worker_result_path_reason(value: object) -> str | None:
    """Return why a completed worker result path is unsafe, if any."""

    if not isinstance(value, str) or not value.strip():
        return "result_path must be a nonblank string"
    raw_value = value.strip()
    if "#" in raw_value:
        return "fragments are not allowed in worker result paths"
    failures = unsafe_repo_relative_path_patterns((raw_value,))
    if failures:
        return failures[0]
    normalized = raw_value.replace("\\", "/")
    if Path(normalized).suffix.lower() != ".json":
        return "completed worker result_path must end with .json"
    return None


def unsafe_verification_command_reason(command: object) -> str | None:
    """Return why a worker verification command is unsafe, if any."""

    if not isinstance(command, str):
        return "verification command must be a string"
    raw_command = command.strip()
    if _contains_control_character(raw_command):
        return "control characters are not allowed"
    if any(fragment in raw_command for fragment in SHELL_METACHARACTERS):
        return "shell metacharacters and redirection are not allowed"
    try:
        tokens = tuple(shlex.split(raw_command))
    except ValueError as exc:
        return f"could not parse command: {exc}"
    if not tokens:
        return "empty command"
    if tokens == ("uv", "lock", "--check"):
        return None
    if tokens[:2] == ("git", "status"):
        return None
    if tokens == ("git", "diff", "--check"):
        return None
    if tokens[:2] == ("uv", "run"):
        if tokens[:3] != UV_RUN_READONLY_PREFIX:
            return "uv run verification must include --no-sync"
        uv_tokens = tokens[3:]
        if not uv_tokens:
            return "uv run --no-sync verification is missing a command"
        if uv_tokens[0] == "ruff":
            return _ruff_command_reason(uv_tokens)
        if uv_tokens[0] == "mypy":
            return _mypy_command_reason(uv_tokens)
        if uv_tokens[0] in {"python", "python3"}:
            return _safe_python_command_reason(uv_tokens[1:])
        if uv_tokens[0] == "codex-supervisor":
            return _codex_supervisor_cli_command_reason(uv_tokens[1:])
        return "uv run --no-sync verification is limited to approved read-only commands"
    if tokens[0] == "ruff":
        return _ruff_command_reason(tokens)
    if tokens[0] == "mypy":
        return _mypy_command_reason(tokens)
    if tokens[0] in {"python", "python3"} and len(tokens) >= 2:
        return _safe_python_command_reason(tokens[1:])
    return "unsupported verification command shape"


def _contains_control_character(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _safe_python_command_reason(tokens: tuple[str, ...]) -> str | None:
    if not tokens or tokens[0] != "-B":
        return "python verification must use -B to disable bytecode writes"
    remaining = tokens[1:]
    if not remaining:
        return "python verification is missing a script or module"
    script = remaining[0]
    if script in SAFE_PYTHON_CHECK_SCRIPTS:
        return _safe_python_script_reason(script, remaining[1:])
    if script == "-m":
        module = remaining[1] if len(remaining) >= 2 else ""
        args = remaining[2:] if len(remaining) >= 2 else ()
        if module == "pytest":
            return _pytest_command_reason(args)
        return _safe_python_module_reason(module, args)
    return "python verification is limited to approved scripts or modules"


def _safe_python_script_reason(script: str, args: tuple[str, ...]) -> str | None:
    allowed_args = SAFE_PYTHON_CHECK_SCRIPT_ARGS.get(script, frozenset({()}))
    if args in allowed_args:
        return None
    return f"{script} verification uses unsupported arguments"


def _pytest_command_reason(tokens: tuple[str, ...]) -> str | None:
    blocked_output_flags = (
        "--basetemp",
        "--cache-clear",
        "--cov",
        "--junitxml",
        "--json-report",
        "--lf",
        "--last-failed",
        "--new-first",
        "--stepwise",
    )
    for token in tokens:
        if any(token == flag or token.startswith(flag + "=") for flag in blocked_output_flags):
            return "pytest verification must not write cache, coverage, or report artifacts"
    for index, token in enumerate(tokens[:-1]):
        if token == "-p" and tokens[index + 1] == "no:cacheprovider":
            return None
    return "pytest verification must disable cache with -p no:cacheprovider"


def _ruff_command_reason(tokens: tuple[str, ...]) -> str | None:
    if "--no-cache" not in tokens:
        return "ruff verification must include --no-cache"
    if "--fix" in tokens or any(token.startswith("--fix") for token in tokens):
        return "ruff verification must not mutate files"
    args = tokens[1:] if tokens and tokens[0] == "ruff" else tokens
    if args and args[0] == "check":
        return None
    if args and args[0] == "format" and "--check" in args:
        return None
    return "ruff verification is limited to check or format --check"


def _mypy_command_reason(tokens: tuple[str, ...]) -> str | None:
    if any(token == "--install-types" or token.startswith("--install-types=") for token in tokens):
        return "mypy verification must not install type packages"
    if "--no-incremental" in tokens:
        return None
    return "mypy verification must include --no-incremental"


def _safe_python_module_reason(module: str, args: tuple[str, ...]) -> str | None:
    if module == "codex_supervisor.cli":
        return _codex_supervisor_cli_command_reason(args)
    return "python -m verification is limited to codex_supervisor.cli read-only commands"


def _codex_supervisor_cli_command_reason(args: tuple[str, ...]) -> str | None:
    if not args:
        return "codex_supervisor.cli verification is missing a read-only subcommand"
    command = args[0]
    if command in SAFE_CODEX_SUPERVISOR_CLI_READ_COMMANDS:
        return None
    return "codex_supervisor.cli verification is limited to read-only subcommands"


def _validate_repo_relative_path_patterns(values: Iterable[object], field_name: str) -> None:
    failures = unsafe_repo_relative_path_patterns(values)
    if failures:
        msg = f"{field_name} contains unsafe repo-relative path pattern: {failures[0]}"
        raise ValueError(msg)


def _validate_artifact_id(value: object, field_name: str) -> None:
    failures = unsafe_repo_relative_path_patterns((value,))
    if failures:
        msg = f"{field_name} contains unsafe repo-relative artifact path: {failures[0]}"
        raise ValueError(msg)


def _validate_verification_commands(values: Iterable[object], field_name: str) -> None:
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        reason = unsafe_verification_command_reason(value)
        if reason:
            msg = f"{field_name} contains unsafe verification command: {value} ({reason})"
            raise ValueError(msg)


def _validate_worker_result_path(value: object) -> None:
    reason = unsafe_worker_result_path_reason(value)
    if reason:
        msg = f"completed worker result_path is unsafe: {reason}"
        raise ValueError(msg)


def _validate_task_contract_for_current_queue_plan(
    connection: sqlite3.Connection,
    record: SupervisorTaskRecord,
) -> None:
    plan_status = _plan_status_for_task_contract_validation(connection, record.plan_id)
    if plan_status not in CURRENT_QUEUE_PLAN_STATUSES:
        return
    if (
        record.task_type != "AFK"
        or record.status == "pending"
        or record.status not in OPEN_TASK_STATUSES
    ):
        return
    failures = _afk_execution_contract_failures(
        acceptance_criteria=record.acceptance_criteria,
        verification_commands=record.verification_commands,
        allowed_paths=record.allowed_paths,
    )
    if failures:
        msg = (
            f"open AFK task {record.task_id} on {plan_status} plan {record.plan_id} "
            f"has invalid execution contract: {failures[0]}"
        )
        raise ValueError(msg)


def _validate_status_transition_contract_for_current_queue_plan(
    connection: sqlite3.Connection,
    task: SupervisorTaskSummaryRecord,
    next_status: str,
) -> None:
    if task.plan_status not in CURRENT_QUEUE_PLAN_STATUSES:
        return
    if task.task_type != "AFK" or next_status not in OPEN_TASK_STATUSES:
        return
    failures = _afk_execution_contract_failures(
        acceptance_criteria=task.acceptance_criteria,
        verification_commands=task.verification_commands,
        allowed_paths=task.allowed_paths,
    )
    if failures:
        msg = (
            f"cannot set AFK task {task.task_id} to {next_status} on {task.plan_status} "
            f"plan {task.plan_id}; invalid execution contract: {failures[0]}"
        )
        raise ValueError(msg)
    plan_status = _plan_status_for_task_contract_validation(connection, task.plan_id)
    if plan_status != task.plan_status:
        msg = f"task {task.task_id} plan status changed during validation"
        raise ValueError(msg)


def _plan_status_for_task_contract_validation(
    connection: sqlite3.Connection,
    plan_id: str,
) -> str:
    row = connection.execute("SELECT status FROM plans WHERE plan_id = ?", (plan_id,)).fetchone()
    _raise_missing(0 if row is None else 1, "plan", plan_id)
    return str(row["status"])


def _afk_execution_contract_failures(
    *,
    acceptance_criteria: Iterable[object],
    verification_commands: Iterable[object],
    allowed_paths: Iterable[object],
) -> tuple[str, ...]:
    failures: list[str] = []
    if not _contains_nonblank_string(acceptance_criteria):
        failures.append("acceptance_criteria must include a nonblank criterion")
    if not _contains_nonblank_string(verification_commands):
        failures.append("verification_commands must include a nonblank command")
    for command in verification_commands:
        if not isinstance(command, str) or not command.strip():
            continue
        reason = unsafe_verification_command_reason(command)
        if reason:
            failures.append(f"verification command is unsafe: {command} ({reason})")
            break
    if not _contains_nonblank_string(allowed_paths):
        failures.append("allowed_paths must include a repo-relative path pattern")
    path_failures = unsafe_repo_relative_path_patterns(allowed_paths)
    if path_failures:
        failures.append(f"allowed_paths is unsafe: {path_failures[0]}")
    return tuple(failures)


def _validate_plan_can_enter_status(
    connection: sqlite3.Connection,
    plan_id: str,
    status: str,
) -> None:
    if status not in TERMINAL_PLAN_STATUSES:
        return
    open_task = _first_open_task_for_plan(connection, plan_id)
    if open_task is not None:
        msg = (
            f"cannot set plan {plan_id} to {status} while task "
            f"{open_task['task_id']} is {open_task['status']}; close or move open tasks first"
        )
        raise ValueError(msg)
    open_milestone = _first_open_milestone_for_plan(connection, plan_id)
    if open_milestone is not None:
        msg = (
            f"cannot set plan {plan_id} to {status} while milestone "
            f"{open_milestone['milestone_id']} is {open_milestone['status']}"
        )
        raise ValueError(msg)
    open_criterion = _first_open_criterion_for_plan(connection, plan_id)
    if open_criterion is not None:
        msg = (
            f"cannot set plan {plan_id} to {status} while criterion "
            f"{open_criterion['criterion_id']} is {open_criterion['status']}"
        )
        raise ValueError(msg)
    if status == "completed":
        incomplete_criterion = _first_not_completed_criterion_for_plan(connection, plan_id)
        if incomplete_criterion is not None:
            msg = (
                f"cannot set plan {plan_id} to completed while criterion "
                f"{incomplete_criterion['criterion_id']} is {incomplete_criterion['status']}"
            )
            raise ValueError(msg)


def _first_open_task_for_plan(connection: sqlite3.Connection, plan_id: str) -> sqlite3.Row | None:
    placeholders = ", ".join("?" for _ in OPEN_TASK_STATUSES)
    return cast(
        sqlite3.Row | None,
        connection.execute(
            f"""
            SELECT task_id, status
            FROM supervisor_tasks
            WHERE plan_id = ?
              AND status IN ({placeholders})
            ORDER BY task_id
            LIMIT 1
            """,
            (plan_id, *sorted(OPEN_TASK_STATUSES)),
        ).fetchone(),
    )


def _first_open_milestone_for_plan(
    connection: sqlite3.Connection,
    plan_id: str,
) -> sqlite3.Row | None:
    placeholders = ", ".join("?" for _ in OPEN_MILESTONE_STATUSES)
    return cast(
        sqlite3.Row | None,
        connection.execute(
            f"""
            SELECT milestone_id, status
            FROM plan_milestones
            WHERE plan_id = ?
              AND status IN ({placeholders})
            ORDER BY sort_order, milestone_id
            LIMIT 1
            """,
            (plan_id, *sorted(OPEN_MILESTONE_STATUSES)),
        ).fetchone(),
    )


def _first_open_criterion_for_plan(
    connection: sqlite3.Connection,
    plan_id: str,
) -> sqlite3.Row | None:
    placeholders = ", ".join("?" for _ in OPEN_CRITERION_STATUSES)
    return cast(
        sqlite3.Row | None,
        connection.execute(
            f"""
            SELECT criterion_id, status
            FROM plan_acceptance_criteria
            WHERE plan_id = ?
              AND status IN ({placeholders})
            ORDER BY criterion_id
            LIMIT 1
            """,
            (plan_id, *sorted(OPEN_CRITERION_STATUSES)),
        ).fetchone(),
    )


def _first_not_completed_criterion_for_plan(
    connection: sqlite3.Connection,
    plan_id: str,
) -> sqlite3.Row | None:
    return cast(
        sqlite3.Row | None,
        connection.execute(
            """
            SELECT criterion_id, status
            FROM plan_acceptance_criteria
            WHERE plan_id = ?
              AND status != 'completed'
            ORDER BY criterion_id
            LIMIT 1
            """,
            (plan_id,),
        ).fetchone(),
    )


def _task_status_row(connection: sqlite3.Connection, task_id: str) -> sqlite3.Row | None:
    return cast(
        sqlite3.Row | None,
        connection.execute(
            "SELECT status FROM supervisor_tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone(),
    )


def _validate_worker_run_can_be_nonterminal(
    connection: sqlite3.Connection,
    *,
    task_id: str,
    worker_run_id: str,
    worker_status: str,
) -> None:
    row = _task_status_row(connection, task_id)
    _raise_missing(0 if row is None else 1, "task", task_id)
    assert row is not None
    task_status = str(row["status"])
    if task_status not in TASK_STATUSES_ALLOWED_TO_START_NONTERMINAL_WORKER_RUN:
        msg = (
            f"cannot set worker run {worker_run_id} to {worker_status} while task "
            f"{task_id} is {task_status}; reopen the task before starting a worker run"
        )
        raise ValueError(msg)


def _first_nonterminal_worker_run_for_task(
    connection: sqlite3.Connection,
    task_id: str,
    *,
    excluding_worker_run_id: str | None = None,
) -> sqlite3.Row | None:
    placeholders = ", ".join("?" for _ in NONTERMINAL_WORKER_RUN_STATUSES)
    parameters: list[object] = [task_id, *sorted(NONTERMINAL_WORKER_RUN_STATUSES)]
    exclusion_clause = ""
    if excluding_worker_run_id is not None:
        exclusion_clause = "AND worker_run_id != ?"
        parameters.append(excluding_worker_run_id)
    return cast(
        sqlite3.Row | None,
        connection.execute(
            f"""
            SELECT worker_run_id, status
            FROM worker_runs
            WHERE task_id = ?
              AND status IN ({placeholders})
              {exclusion_clause}
            ORDER BY started_at DESC, worker_run_id
            LIMIT 1
            """,
            parameters,
        ).fetchone(),
    )


def _list_supervisor_task_summaries(
    connection: sqlite3.Connection,
    *,
    status: str | None = None,
    active_plans_only: bool = False,
    current_queue_plans_only: bool = False,
    task_type: str | None = None,
) -> tuple[SupervisorTaskSummaryRecord, ...]:
    if active_plans_only and current_queue_plans_only:
        msg = "active_plans_only and current_queue_plans_only are mutually exclusive"
        raise ValueError(msg)
    query = """
        SELECT
            st.*,
            p.title AS plan_title,
            p.status AS plan_status,
            p.priority AS plan_priority
        FROM supervisor_tasks st
        JOIN plans p ON p.plan_id = st.plan_id
    """
    clauses: list[str] = []
    parameters: list[str] = []
    if status is not None:
        clauses.append("st.status = ?")
        parameters.append(status)
    if active_plans_only:
        clauses.append("p.status = 'active'")
    if current_queue_plans_only:
        clauses.append("p.status IN ('active', 'blocked')")
    if task_type is not None:
        clauses.append("st.task_type = ?")
        parameters.append(task_type)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += """
        ORDER BY
            CASE WHEN p.status = 'active' THEN 0 ELSE 1 END,
            p.priority DESC,
            CASE WHEN st.status = 'ready' THEN 0 ELSE 1 END,
            st.updated_at DESC,
            st.task_id
    """
    rows = connection.execute(query, parameters).fetchall()
    return tuple(_supervisor_task_summary_from_row(row) for row in rows)


def _get_supervisor_task_summary(
    connection: sqlite3.Connection,
    task_id: str,
) -> SupervisorTaskSummaryRecord:
    tasks = _list_supervisor_task_summaries(connection)
    for task in tasks:
        if task.task_id == task_id:
            return task
    raise KeyError(f"No task found: {task_id}")


def _list_plans(
    connection: sqlite3.Connection,
    *,
    status: str | None = None,
) -> tuple[PlanRecord, ...]:
    if status is None:
        rows = connection.execute(
            """
            SELECT * FROM plans
            ORDER BY
                CASE status
                    WHEN 'active' THEN 0
                    WHEN 'blocked' THEN 1
                    ELSE 2
                END,
                priority DESC,
                updated_at DESC,
                plan_id
            """
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT * FROM plans
            WHERE status = ?
            ORDER BY priority DESC, updated_at DESC, plan_id
            """,
            (status,),
        ).fetchall()
    return tuple(_plan_from_row(row) for row in rows)


def _list_plan_acceptance_criteria(
    connection: sqlite3.Connection,
    *,
    plan_id: str | None = None,
) -> tuple[PlanAcceptanceCriterionRecord, ...]:
    query = "SELECT * FROM plan_acceptance_criteria"
    parameters: list[object] = []
    if plan_id is not None:
        query += " WHERE plan_id = ?"
        parameters.append(plan_id)
    query += " ORDER BY plan_id, criterion_id"
    rows = connection.execute(query, parameters).fetchall()
    return tuple(_plan_acceptance_criterion_from_row(row) for row in rows)


def _list_worker_runs(connection: sqlite3.Connection) -> tuple[WorkerRunRecord, ...]:
    rows = connection.execute("SELECT * FROM worker_runs ORDER BY started_at DESC, worker_run_id")
    return tuple(_worker_run_from_row(row) for row in rows)


def _plan_from_row(row: sqlite3.Row) -> PlanRecord:
    return PlanRecord(
        plan_id=str(row["plan_id"]),
        slug=str(row["slug"]),
        title=str(row["title"]),
        goal=str(row["goal"]),
        status=str(row["status"]),
        priority=int(row["priority"]),
        owner_agent=str(row["owner_agent"]) if row["owner_agent"] is not None else None,
        non_goals=_load_json_object(str(row["non_goals_json"])),
        context=_load_json_object(str(row["context_json"])),
        superseded_by_plan_id=(
            str(row["superseded_by_plan_id"]) if row["superseded_by_plan_id"] is not None else None
        ),
    )


def _plan_milestone_from_row(row: sqlite3.Row) -> PlanMilestoneRecord:
    return PlanMilestoneRecord(
        milestone_id=str(row["milestone_id"]),
        plan_id=str(row["plan_id"]),
        title=str(row["title"]),
        status=str(row["status"]),
        sort_order=int(row["sort_order"]),
        details=_load_json_object(str(row["details_json"])),
    )


def _plan_acceptance_criterion_from_row(row: sqlite3.Row) -> PlanAcceptanceCriterionRecord:
    return PlanAcceptanceCriterionRecord(
        criterion_id=str(row["criterion_id"]),
        plan_id=str(row["plan_id"]),
        description=str(row["description"]),
        status=str(row["status"]),
        verification_command=(
            str(row["verification_command"]) if row["verification_command"] is not None else None
        ),
    )


def _supervisor_task_summary_from_row(row: sqlite3.Row) -> SupervisorTaskSummaryRecord:
    return SupervisorTaskSummaryRecord(
        task_id=str(row["task_id"]),
        plan_id=str(row["plan_id"]),
        plan_title=str(row["plan_title"]),
        plan_status=str(row["plan_status"]),
        plan_priority=int(row["plan_priority"]),
        title=str(row["title"]),
        goal=str(row["goal"]),
        task_type=str(row["task_type"]),
        status=str(row["status"]),
        scope=_load_json_object(str(row["scope_json"])),
        out_of_scope=_load_json_object(str(row["out_of_scope_json"])),
        acceptance_criteria=_load_json_string_array(
            str(row["acceptance_criteria_json"]),
            "acceptance_criteria",
        ),
        verification_commands=_load_json_string_array(
            str(row["verification_commands_json"]),
            "verification_commands",
        ),
        allowed_paths=_load_json_string_array(str(row["allowed_paths_json"]), "allowed_paths"),
        blocked_by=_load_json_string_array(str(row["blocked_by_json"]), "blocked_by"),
        worker_backend=str(row["worker_backend"]),
        review_required=bool(row["review_required"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _plan_decision_from_row(row: sqlite3.Row) -> PlanDecisionRecord:
    return PlanDecisionRecord(
        decision_id=str(row["decision_id"]),
        plan_id=str(row["plan_id"]),
        decision=str(row["decision"]),
        rationale=str(row["rationale"]),
        alternatives_considered=(
            str(row["alternatives_considered"])
            if row["alternatives_considered"] is not None
            else None
        ),
        consequences=str(row["consequences"]) if row["consequences"] is not None else None,
        decided_at=_parse_datetime(str(row["decided_at"])),
    )


def _plan_progress_from_row(row: sqlite3.Row) -> PlanProgressRecord:
    return PlanProgressRecord(
        progress_id=str(row["progress_id"]),
        plan_id=str(row["plan_id"]),
        event_type=str(row["event_type"]),
        summary=str(row["summary"]),
        details=str(row["details"]) if row["details"] is not None else None,
        linked_artifact_id=(
            str(row["linked_artifact_id"]) if row["linked_artifact_id"] is not None else None
        ),
        occurred_at=_parse_datetime(str(row["occurred_at"])),
    )


def _plan_artifact_link_from_row(row: sqlite3.Row) -> PlanArtifactLinkRecord:
    return PlanArtifactLinkRecord(
        plan_id=str(row["plan_id"]),
        artifact_id=str(row["artifact_id"]),
        relationship=str(row["relationship"]),
    )


def _plan_commit_link_from_row(row: sqlite3.Row) -> PlanCommitLinkRecord:
    return PlanCommitLinkRecord(
        plan_id=str(row["plan_id"]),
        commit_sha=str(row["commit_sha"]),
        relationship=str(row["relationship"]),
    )


def _worker_run_from_row(row: sqlite3.Row) -> WorkerRunRecord:
    return WorkerRunRecord(
        worker_run_id=str(row["worker_run_id"]),
        task_id=str(row["task_id"]),
        backend=str(row["backend"]),
        status=str(row["status"]),
        worktree_path=str(row["worktree_path"]) if row["worktree_path"] is not None else None,
        prompt_path=str(row["prompt_path"]) if row["prompt_path"] is not None else None,
        jsonl_path=str(row["jsonl_path"]) if row["jsonl_path"] is not None else None,
        result_path=str(row["result_path"]) if row["result_path"] is not None else None,
        started_at=str(row["started_at"]) if row["started_at"] is not None else None,
        completed_at=str(row["completed_at"]) if row["completed_at"] is not None else None,
        failure_class=str(row["failure_class"]) if row["failure_class"] is not None else None,
        metadata=_load_json_object(str(row["metadata_json"])),
    )


def _touch_plan(connection: sqlite3.Connection, plan_id: str, updated_at: str) -> None:
    connection.execute(
        "UPDATE plans SET updated_at = ? WHERE plan_id = ?",
        (updated_at, plan_id),
    )


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _sqlite_uri(path: Path, mode: str) -> str:
    resolved = path.resolve()
    quoted_path = quote(resolved.as_posix(), safe="/:")
    return f"file:{quoted_path}?mode={mode}"


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _format_datetime(value: datetime) -> str:
    normalized = value.astimezone(UTC).replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")


def _dump_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json_object(value: str) -> JsonObject:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        msg = "Expected JSON object"
        raise ValueError(msg)
    return parsed


def _load_json_array(value: str) -> JsonArray:
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        msg = "Expected JSON array"
        raise ValueError(msg)
    return parsed


def _load_json_string_array(value: str, field_name: str) -> JsonStringArray:
    parsed = _load_json_array(value)
    _validate_string_array(parsed, field_name)
    return cast(JsonStringArray, parsed)


def _validate_string_array(values: Iterable[object], field_name: str) -> None:
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value.strip():
            msg = f"{field_name}[{index}] must be a nonblank string"
            raise ValueError(msg)


def _validate_required(value: str, field_name: str) -> None:
    if not value.strip():
        msg = f"{field_name} is required"
        raise ValueError(msg)


def _validate_commit_sha(value: str) -> None:
    if FULL_COMMIT_SHA_PATTERN.fullmatch(value) is None:
        msg = "commit_sha must be a 40-character lowercase hexadecimal commit SHA"
        raise ValueError(msg)


def _validate_choice(value: str, allowed_values: frozenset[str], field_name: str) -> None:
    if value not in allowed_values:
        options = ", ".join(sorted(allowed_values))
        msg = f"{field_name} must be one of: {options}"
        raise ValueError(msg)


def _apply_schema_migrations(connection: sqlite3.Connection, now: str) -> None:
    current_version = _schema_version(connection)
    if current_version == 0:
        _record_schema_migrations(connection, now, starting_after=0)
        return
    if current_version < CURRENT_PLANNING_SCHEMA_VERSION:
        _rebuild_tables_with_current_constraints(connection)
    _record_schema_migrations(connection, now, starting_after=current_version)


def _schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
    if row is None or row["version"] is None:
        return 0
    return int(row["version"])


def _record_schema_migrations(
    connection: sqlite3.Connection,
    now: str,
    *,
    starting_after: int,
) -> None:
    connection.executemany(
        """
        INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
        VALUES (?, ?, ?)
        """,
        tuple(
            (version, name, now)
            for version, name in PLANNING_SCHEMA_MIGRATIONS
            if version > starting_after
        ),
    )


def _rebuild_tables_with_current_constraints(connection: sqlite3.Connection) -> None:
    old_names = {table: f"__old_{table}" for table in CONSTRAINED_TABLE_REBUILD_ORDER}
    for table, old_name in old_names.items():
        connection.execute(f"ALTER TABLE {table} RENAME TO {old_name}")
    connection.executescript(PLANNING_SCHEMA_SQL)
    for table in CONSTRAINED_TABLE_REBUILD_ORDER:
        columns = ", ".join(PLANNING_SCHEMA_TABLE_COLUMNS[table])
        connection.execute(
            f"""
            INSERT INTO {table} ({columns})
            SELECT {columns}
            FROM {old_names[table]}
            """
        )
    for table in reversed(CONSTRAINED_TABLE_REBUILD_ORDER):
        connection.execute(f"DROP TABLE {old_names[table]}")
    connection.executescript(PLANNING_SCHEMA_SQL)


def _normalize_schema_sql(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _raise_missing(rowcount: int, label: str, identifier: str) -> None:
    if rowcount == 0:
        msg = f"No {label} found: {identifier}"
        raise KeyError(msg)


def _sync_task_and_plan_for_worker_run(
    connection: sqlite3.Connection,
    task_id: str,
    worker_status: str,
    updated_at: str,
) -> None:
    row = connection.execute(
        "SELECT plan_id, status, review_required FROM supervisor_tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    _raise_missing(0 if row is None else 1, "task", task_id)
    plan_id = str(row["plan_id"])
    task_status = _task_status_for_worker_status(
        worker_status,
        current_task_status=str(row["status"]),
        review_required=bool(row["review_required"]),
    )
    if task_status is not None:
        connection.execute(
            "UPDATE supervisor_tasks SET status = ?, updated_at = ? WHERE task_id = ?",
            (task_status, updated_at, task_id),
        )
    _touch_plan(connection, plan_id, updated_at)


def _link_worker_result_artifact(
    connection: sqlite3.Connection,
    task_id: str,
    result_path: str,
) -> None:
    row = connection.execute(
        "SELECT plan_id FROM supervisor_tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    _raise_missing(0 if row is None else 1, "task", task_id)
    connection.execute(
        """
        INSERT OR IGNORE INTO plan_artifact_links(plan_id, artifact_id, relationship)
        VALUES (?, ?, 'worker-result')
        """,
        (str(row["plan_id"]), result_path),
    )


def _task_status_for_worker_status(
    worker_status: str,
    *,
    current_task_status: str,
    review_required: bool,
) -> str | None:
    if current_task_status in {"completed", "failed", "cancelled"}:
        return None
    if worker_status in {"queued", "running"}:
        return "running"
    if worker_status == "blocked":
        return "blocked"
    if worker_status == "needs_review":
        return "reviewing"
    if worker_status == "completed":
        return "reviewing" if review_required else "completed"
    if worker_status == "failed":
        return "failed"
    if worker_status == "cancelled":
        return "cancelled"
    return None


PLANNING_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL CHECK(length(name) > 0),
    applied_at TEXT NOT NULL CHECK(length(applied_at) > 0)
);

CREATE TABLE IF NOT EXISTS plans (
    plan_id TEXT PRIMARY KEY CHECK(length(plan_id) > 0),
    slug TEXT NOT NULL UNIQUE CHECK(length(slug) > 0),
    title TEXT NOT NULL CHECK(length(title) > 0),
    goal TEXT NOT NULL CHECK(length(goal) > 0),
    non_goals_json TEXT NOT NULL DEFAULT '{}',
    context_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL CHECK(status IN (
        'active', 'blocked', 'completed', 'abandoned', 'superseded'
    )),
    priority INTEGER NOT NULL DEFAULT 0,
    owner_agent TEXT,
    superseded_by_plan_id TEXT REFERENCES plans(plan_id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plans_status ON plans(status);
CREATE INDEX IF NOT EXISTS idx_plans_priority ON plans(priority);

CREATE TABLE IF NOT EXISTS plan_milestones (
    milestone_id TEXT PRIMARY KEY CHECK(length(milestone_id) > 0),
    plan_id TEXT NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
    title TEXT NOT NULL CHECK(length(title) > 0),
    status TEXT NOT NULL CHECK(status IN (
        'pending', 'active', 'blocked', 'completed', 'cancelled'
    )),
    sort_order INTEGER NOT NULL DEFAULT 0,
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_plan_milestones_plan_id ON plan_milestones(plan_id);

CREATE TABLE IF NOT EXISTS plan_acceptance_criteria (
    criterion_id TEXT PRIMARY KEY CHECK(length(criterion_id) > 0),
    plan_id TEXT NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
    description TEXT NOT NULL CHECK(length(description) > 0),
    status TEXT NOT NULL CHECK(status IN (
        'pending', 'blocked', 'completed', 'failed', 'cancelled'
    )),
    verification_command TEXT
);

CREATE INDEX IF NOT EXISTS idx_plan_acceptance_plan_id ON plan_acceptance_criteria(plan_id);

CREATE TABLE IF NOT EXISTS plan_decisions (
    decision_id TEXT PRIMARY KEY CHECK(length(decision_id) > 0),
    plan_id TEXT NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
    decision TEXT NOT NULL CHECK(length(decision) > 0),
    rationale TEXT NOT NULL CHECK(length(rationale) > 0),
    alternatives_considered TEXT,
    consequences TEXT,
    decided_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plan_decisions_plan_id ON plan_decisions(plan_id);

CREATE TABLE IF NOT EXISTS plan_progress_events (
    progress_id TEXT PRIMARY KEY CHECK(length(progress_id) > 0),
    plan_id TEXT NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK(length(event_type) > 0),
    summary TEXT NOT NULL CHECK(length(summary) > 0),
    details TEXT,
    linked_artifact_id TEXT,
    occurred_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plan_progress_plan_id ON plan_progress_events(plan_id);
CREATE INDEX IF NOT EXISTS idx_plan_progress_occurred_at ON plan_progress_events(occurred_at);

CREATE TABLE IF NOT EXISTS plan_artifact_links (
    plan_id TEXT NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
    artifact_id TEXT NOT NULL CHECK(length(artifact_id) > 0),
    relationship TEXT NOT NULL CHECK(length(relationship) > 0),
    PRIMARY KEY(plan_id, artifact_id, relationship)
);

CREATE TABLE IF NOT EXISTS plan_commit_links (
    plan_id TEXT NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
    commit_sha TEXT NOT NULL CHECK(
        length(commit_sha) = 40 AND commit_sha NOT GLOB '*[^0-9a-f]*'
    ),
    relationship TEXT NOT NULL CHECK(length(relationship) > 0),
    PRIMARY KEY(plan_id, commit_sha, relationship)
);

CREATE TABLE IF NOT EXISTS supervisor_tasks (
    task_id TEXT PRIMARY KEY CHECK(length(task_id) > 0),
    plan_id TEXT NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
    title TEXT NOT NULL CHECK(length(title) > 0),
    goal TEXT NOT NULL CHECK(length(goal) > 0),
    task_type TEXT NOT NULL CHECK(task_type IN ('AFK', 'HITL')),
    status TEXT NOT NULL CHECK(status IN (
        'pending', 'ready', 'running', 'blocked', 'reviewing', 'completed', 'failed', 'cancelled'
    )),
    scope_json TEXT NOT NULL DEFAULT '{}',
    out_of_scope_json TEXT NOT NULL DEFAULT '{}',
    acceptance_criteria_json TEXT NOT NULL DEFAULT '[]',
    verification_commands_json TEXT NOT NULL DEFAULT '[]',
    allowed_paths_json TEXT NOT NULL DEFAULT '[]',
    blocked_by_json TEXT NOT NULL DEFAULT '[]',
    worker_backend TEXT NOT NULL DEFAULT 'codex_exec',
    review_required INTEGER NOT NULL DEFAULT 1 CHECK(review_required IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_supervisor_tasks_plan_id ON supervisor_tasks(plan_id);
CREATE INDEX IF NOT EXISTS idx_supervisor_tasks_status ON supervisor_tasks(status);

CREATE TABLE IF NOT EXISTS worker_runs (
    worker_run_id TEXT PRIMARY KEY CHECK(length(worker_run_id) > 0),
    task_id TEXT NOT NULL REFERENCES supervisor_tasks(task_id) ON DELETE CASCADE,
    backend TEXT NOT NULL CHECK(length(backend) > 0),
    status TEXT NOT NULL CHECK(status IN (
        'queued', 'running', 'blocked', 'completed', 'failed', 'cancelled', 'needs_review'
    )),
    worktree_path TEXT,
    prompt_path TEXT,
    jsonl_path TEXT,
    result_path TEXT,
    started_at TEXT,
    completed_at TEXT,
    failure_class TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_worker_runs_task_id ON worker_runs(task_id);
CREATE INDEX IF NOT EXISTS idx_worker_runs_status ON worker_runs(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_worker_runs_one_nonterminal_per_task
ON worker_runs(task_id)
WHERE status IN ('queued', 'running', 'blocked', 'needs_review');
"""
