"""Tracked SQLite planning store."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

JsonObject = dict[str, Any]

CURRENT_PLANNING_SCHEMA_VERSION = 1


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


class PlanningSQLiteStore:
    """Repository wrapper around the tracked planning SQLite database."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self, *, create: bool = False) -> Iterator[sqlite3.Connection]:
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
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
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
                VALUES (?, ?, ?)
                """,
                (
                    CURRENT_PLANNING_SCHEMA_VERSION,
                    "initial_supervisor_planning_schema",
                    _format_datetime(_utc_now()),
                ),
            )

    def schema_version(self) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT MAX(version) AS version FROM schema_migrations"
            ).fetchone()
        if row is None or row["version"] is None:
            return 0
        return int(row["version"])

    def upsert_plan(self, record: PlanRecord) -> None:
        _validate_required(record.plan_id, "plan_id")
        _validate_required(record.slug, "slug")
        _validate_required(record.title, "title")
        _validate_required(record.goal, "goal")
        _validate_required(record.status, "status")
        now = _format_datetime(_utc_now())
        with self.connect() as connection:
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

    def list_plans(self, *, status: str | None = None) -> tuple[PlanRecord, ...]:
        with self.connect() as connection:
            if status is None:
                rows = connection.execute(
                    "SELECT * FROM plans ORDER BY priority DESC, updated_at DESC, plan_id"
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

    def add_plan_progress(self, record: PlanProgressRecord) -> None:
        _validate_required(record.progress_id, "progress_id")
        _validate_required(record.plan_id, "plan_id")
        _validate_required(record.event_type, "event_type")
        _validate_required(record.summary, "summary")
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


def initialize_planning_database(path: Path) -> PlanningSQLiteStore:
    """Initialize and return the planning store."""

    store = PlanningSQLiteStore(path)
    store.initialize()
    return store


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


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _format_datetime(value: datetime) -> str:
    normalized = value.astimezone(UTC).replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")


def _dump_json(value: JsonObject) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json_object(value: str) -> JsonObject:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        msg = "Expected JSON object"
        raise ValueError(msg)
    return parsed


def _validate_required(value: str, field_name: str) -> None:
    if not value.strip():
        msg = f"{field_name} is required"
        raise ValueError(msg)


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
    status TEXT NOT NULL CHECK(length(status) > 0),
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
    status TEXT NOT NULL CHECK(length(status) > 0),
    sort_order INTEGER NOT NULL DEFAULT 0,
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_plan_milestones_plan_id ON plan_milestones(plan_id);

CREATE TABLE IF NOT EXISTS plan_acceptance_criteria (
    criterion_id TEXT PRIMARY KEY CHECK(length(criterion_id) > 0),
    plan_id TEXT NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
    description TEXT NOT NULL CHECK(length(description) > 0),
    status TEXT NOT NULL CHECK(length(status) > 0),
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
    commit_sha TEXT NOT NULL CHECK(length(commit_sha) > 0),
    relationship TEXT NOT NULL CHECK(length(relationship) > 0),
    PRIMARY KEY(plan_id, commit_sha, relationship)
);

CREATE TABLE IF NOT EXISTS supervisor_tasks (
    task_id TEXT PRIMARY KEY CHECK(length(task_id) > 0),
    plan_id TEXT NOT NULL REFERENCES plans(plan_id) ON DELETE CASCADE,
    title TEXT NOT NULL CHECK(length(title) > 0),
    goal TEXT NOT NULL CHECK(length(goal) > 0),
    task_type TEXT NOT NULL CHECK(task_type IN ('AFK', 'HITL')),
    status TEXT NOT NULL CHECK(length(status) > 0),
    scope_json TEXT NOT NULL DEFAULT '{}',
    out_of_scope_json TEXT NOT NULL DEFAULT '{}',
    acceptance_criteria_json TEXT NOT NULL DEFAULT '[]',
    verification_commands_json TEXT NOT NULL DEFAULT '[]',
    allowed_paths_json TEXT NOT NULL DEFAULT '[]',
    blocked_by_json TEXT NOT NULL DEFAULT '[]',
    worker_backend TEXT NOT NULL DEFAULT 'codex_exec',
    review_required INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_supervisor_tasks_plan_id ON supervisor_tasks(plan_id);
CREATE INDEX IF NOT EXISTS idx_supervisor_tasks_status ON supervisor_tasks(status);

CREATE TABLE IF NOT EXISTS worker_runs (
    worker_run_id TEXT PRIMARY KEY CHECK(length(worker_run_id) > 0),
    task_id TEXT NOT NULL REFERENCES supervisor_tasks(task_id) ON DELETE CASCADE,
    backend TEXT NOT NULL CHECK(length(backend) > 0),
    status TEXT NOT NULL CHECK(length(status) > 0),
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
"""
