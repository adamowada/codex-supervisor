"""SQLite helpers for the simplified attempt and evidence schema."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from codex_supervisor.attempts import (
    AttemptEvidence,
    RunAttempt,
    RunAttemptStatus,
    json_string_array,
    normalize_attempt_status,
    parse_json_string_array,
    validate_attempt_timestamps,
    validate_attempt_transition,
)
from codex_supervisor.policy import normalize_assurance


@dataclass(frozen=True)
class PlanRecord:
    """Plan row needed by the simplified execution layer."""

    plan_id: str
    title: str
    status: str
    priority: int
    goal: str


@dataclass(frozen=True)
class TaskRecord:
    """Task row needed by the simplified execution layer."""

    task_id: str
    plan_id: str
    title: str
    status: str
    assurance: str
    intent: str
    acceptance_criteria: tuple[str, ...]


@dataclass(frozen=True)
class QueuedTaskRecord:
    """Next queue item with its owning plan."""

    plan_id: str
    plan_title: str
    plan_status: str
    priority: int
    task: TaskRecord


class AttemptStore:
    """Small store for `attempts` and `evidence_bundles` rows."""

    def __init__(self, database_path: Path, *, read_only: bool = False) -> None:
        self.database_path = database_path
        self.read_only = read_only

    def ensure_active_plan(
        self,
        *,
        plan_id: str,
        title: str,
        goal: str,
        priority: int,
        created_at: str | None = None,
    ) -> PlanRecord:
        """Ensure an active plan row exists for new task intents."""

        created_at = created_at or _now()
        with self._connect() as connection:
            connection.execute(
                """insert into plans(plan_id, title, status, priority, goal, created_at, updated_at)
                   values (?, ?, 'active', ?, ?, ?, ?)
                   on conflict(plan_id) do nothing""",
                (
                    _non_empty(plan_id, "plan_id"),
                    _non_empty(title, "title"),
                    priority,
                    _non_empty(goal, "goal"),
                    created_at,
                    created_at,
                ),
            )
            row = connection.execute(
                """select plan_id, title, status, priority, goal
                   from plans
                   where plan_id = ?""",
                (plan_id,),
            ).fetchone()
        if row is None:
            raise LookupError(f"unknown plan {plan_id!r}")
        plan = PlanRecord(
            plan_id=row["plan_id"],
            title=row["title"],
            status=row["status"],
            priority=row["priority"],
            goal=row["goal"],
        )
        if plan.status != "active":
            raise LookupError(f"unknown active plan {plan_id!r}")
        return plan

    def create_task(
        self,
        *,
        plan_id: str,
        title: str,
        intent: str,
        assurance: str,
        acceptance_criteria: tuple[str, ...],
        task_id: str | None = None,
        created_at: str | None = None,
    ) -> TaskRecord:
        """Create one durable task intent."""

        created_at = created_at or _now()
        task_id = task_id or _stable_id("task")
        normalized_acceptance = _string_array(acceptance_criteria, "acceptance_criteria")
        if not normalized_acceptance:
            raise ValueError("acceptance_criteria must include at least one item")
        task = TaskRecord(
            task_id=_non_empty(task_id, "task_id"),
            plan_id=_non_empty(plan_id, "plan_id"),
            title=_non_empty(title, "title"),
            status="ready",
            assurance=normalize_assurance(assurance).value,
            intent=_non_empty(intent, "intent"),
            acceptance_criteria=normalized_acceptance,
        )

        with self._connect() as connection:
            plan = connection.execute(
                "select 1 from plans where plan_id = ? and status = 'active'",
                (task.plan_id,),
            ).fetchone()
            if plan is None:
                raise LookupError(f"unknown active plan {task.plan_id!r}")
            connection.execute(
                """insert into tasks(
                       task_id, plan_id, title, status, assurance, intent,
                       acceptance_json, created_at, updated_at
                   ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task.task_id,
                    task.plan_id,
                    task.title,
                    task.status,
                    task.assurance,
                    task.intent,
                    json.dumps(list(task.acceptance_criteria), indent=2),
                    created_at,
                    created_at,
                ),
            )
        return task

    def create_attempt(
        self,
        *,
        task_id: str,
        executor: str,
        summary: str,
        attempt_id: str | None = None,
    ) -> RunAttempt:
        """Create a planned attempt for a task."""

        attempt_id = attempt_id or _stable_id("attempt")
        attempt = RunAttempt(
            attempt_id=attempt_id,
            task_id=task_id,
            executor=_non_empty(executor, "executor"),
            status=RunAttemptStatus.PLANNED,
            summary=_non_empty(summary, "summary"),
        )
        validate_attempt_timestamps(attempt)

        with self._connect() as connection:
            self._require_task(connection, task_id)
            active_attempt = connection.execute(
                """select attempt_id from attempts
                   where task_id = ?
                     and status in ('planned', 'running')
                   limit 1""",
                (task_id,),
            ).fetchone()
            if active_attempt is not None:
                raise ValueError(
                    f"task {task_id!r} already has non-terminal attempt "
                    f"{active_attempt['attempt_id']!r}"
                )
            connection.execute(
                """insert into attempts(
                       attempt_id, task_id, executor, status, summary, started_at, finished_at
                   ) values (?, ?, ?, ?, ?, ?, ?)""",
                (
                    attempt.attempt_id,
                    attempt.task_id,
                    attempt.executor,
                    attempt.status.value,
                    attempt.summary,
                    attempt.started_at,
                    attempt.finished_at,
                ),
            )
        return attempt

    def start_attempt(
        self,
        attempt_id: str,
        *,
        task_id: str | None = None,
        summary: str | None = None,
        started_at: str | None = None,
    ) -> RunAttempt:
        """Move a planned attempt to running."""

        started_at = started_at or _now()
        with self._connect() as connection:
            current = self._read_attempt(connection, attempt_id)
            _validate_attempt_task(current, task_id)
            validate_attempt_transition(current.status, RunAttemptStatus.RUNNING)
            attempt = RunAttempt(
                attempt_id=current.attempt_id,
                task_id=current.task_id,
                executor=current.executor,
                status=RunAttemptStatus.RUNNING,
                summary=_non_empty(summary, "summary") if summary is not None else current.summary,
                started_at=started_at,
                finished_at=None,
            )
            validate_attempt_timestamps(attempt)
            connection.execute(
                """update attempts
                   set status = ?, summary = ?, started_at = ?, finished_at = null
                   where attempt_id = ?""",
                (attempt.status.value, attempt.summary, attempt.started_at, attempt.attempt_id),
            )
            connection.execute(
                "update tasks set status = 'running', updated_at = ? where task_id = ?",
                (started_at, attempt.task_id),
            )
        return attempt

    def complete_attempt(
        self,
        attempt_id: str,
        *,
        status: str | RunAttemptStatus,
        summary: str,
        task_id: str | None = None,
        finished_at: str | None = None,
    ) -> RunAttempt:
        """Move an attempt to a terminal status."""

        target_status = normalize_attempt_status(status)
        if target_status is RunAttemptStatus.PLANNED or target_status is RunAttemptStatus.RUNNING:
            raise ValueError("complete_attempt requires a terminal status")

        finished_at = finished_at or _now()
        with self._connect() as connection:
            current = self._read_attempt(connection, attempt_id)
            _validate_attempt_task(current, task_id)
            validate_attempt_transition(current.status, target_status)
            attempt = RunAttempt(
                attempt_id=current.attempt_id,
                task_id=current.task_id,
                executor=current.executor,
                status=target_status,
                summary=_non_empty(summary, "summary"),
                started_at=current.started_at or finished_at,
                finished_at=finished_at,
            )
            validate_attempt_timestamps(attempt)
            connection.execute(
                """update attempts
                   set status = ?, summary = ?, started_at = ?, finished_at = ?
                   where attempt_id = ?""",
                (
                    attempt.status.value,
                    attempt.summary,
                    attempt.started_at,
                    attempt.finished_at,
                    attempt.attempt_id,
                ),
            )
        return attempt

    def attach_evidence_bundle(
        self,
        *,
        task_id: str,
        attempt_id: str | None,
        assurance: str,
        summary: str,
        checks: tuple[str, ...],
        artifacts: tuple[str, ...],
        bundle_id: str | None = None,
        created_at: str | None = None,
    ) -> AttemptEvidence:
        """Attach a compact evidence bundle to a task or attempt."""

        bundle_id = bundle_id or _stable_id("evidence")
        created_at = created_at or _now()
        assurance_level = normalize_assurance(assurance).value
        checks_json = json_string_array(checks, field_name="checks")
        artifacts_json = json_string_array(artifacts, field_name="artifacts")

        with self._connect() as connection:
            self._require_task(connection, task_id)
            if attempt_id is not None:
                attempt = self._read_attempt(connection, attempt_id)
                if attempt.task_id != task_id:
                    raise ValueError("evidence task_id must match attempt task_id")
            connection.execute(
                """insert into evidence_bundles(
                       bundle_id, task_id, attempt_id, assurance, summary,
                       checks_json, artifacts_json, created_at
                   ) values (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    bundle_id,
                    task_id,
                    attempt_id,
                    assurance_level,
                    _non_empty(summary, "summary"),
                    checks_json,
                    artifacts_json,
                    created_at,
                ),
            )
        return AttemptEvidence(
            bundle_id=bundle_id,
            task_id=task_id,
            attempt_id=attempt_id,
            assurance=assurance_level,
            summary=summary,
            checks=parse_json_string_array(checks_json, field_name="checks"),
            artifacts=parse_json_string_array(artifacts_json, field_name="artifacts"),
            created_at=created_at,
        )

    def read_task(self, task_id: str) -> TaskRecord:
        """Read a simplified task row."""

        with self._connect() as connection:
            return self._read_task(connection, task_id)

    def read_next_task(self) -> QueuedTaskRecord | None:
        """Read the next ready task from the active queue."""

        with self._connect() as connection:
            row = connection.execute(
                """select
                       plans.plan_id,
                       plans.title as plan_title,
                       plans.status as plan_status,
                       plans.priority,
                       tasks.task_id,
                       tasks.title as task_title,
                       tasks.status as task_status,
                       tasks.assurance,
                       tasks.intent,
                       tasks.acceptance_json
                   from tasks
                   join plans on plans.plan_id = tasks.plan_id
                   where plans.status = 'active'
                     and tasks.status = 'ready'
                   order by plans.priority desc, tasks.created_at asc, tasks.task_id asc
                   limit 1""",
            ).fetchone()
        if row is None:
            return None
        return QueuedTaskRecord(
            plan_id=row["plan_id"],
            plan_title=row["plan_title"],
            plan_status=row["plan_status"],
            priority=row["priority"],
            task=TaskRecord(
                task_id=row["task_id"],
                plan_id=row["plan_id"],
                title=row["task_title"],
                status=row["task_status"],
                assurance=row["assurance"],
                intent=row["intent"],
                acceptance_criteria=_acceptance_criteria_from_json(row["acceptance_json"]),
            ),
        )

    def read_attempt(self, attempt_id: str) -> RunAttempt:
        """Read one attempt."""

        with self._connect() as connection:
            return self._read_attempt(connection, attempt_id)

    def list_attempts(self, task_id: str) -> tuple[RunAttempt, ...]:
        """List attempts for a task."""

        with self._connect() as connection:
            rows = connection.execute(
                """select attempt_id, task_id, executor, status, summary, started_at, finished_at
                   from attempts
                   where task_id = ?
                   order by coalesce(started_at, ''), attempt_id""",
                (task_id,),
            ).fetchall()
        return tuple(_attempt_from_row(row) for row in rows)

    def list_active_attempts(self, task_id: str) -> tuple[RunAttempt, ...]:
        """List planned or running attempts for a task."""

        return tuple(
            attempt
            for attempt in self.list_attempts(task_id)
            if attempt.status in {RunAttemptStatus.PLANNED, RunAttemptStatus.RUNNING}
        )

    def read_active_attempt(self, task_id: str) -> RunAttempt | None:
        """Read the first planned or running attempt for a task."""

        with self._connect() as connection:
            row = connection.execute(
                """select attempt_id, task_id, executor, status, summary, started_at, finished_at
                   from attempts
                   where task_id = ?
                     and status in ('planned', 'running')
                   order by coalesce(started_at, ''), attempt_id
                   limit 1""",
                (task_id,),
            ).fetchone()
        return _attempt_from_row(row) if row is not None else None

    def read_latest_evidence(self, task_id: str) -> AttemptEvidence | None:
        """Read the latest evidence bundle for a task."""

        with self._connect() as connection:
            row = connection.execute(
                """select bundle_id, task_id, attempt_id, assurance, summary,
                          checks_json, artifacts_json, created_at
                   from evidence_bundles
                   where task_id = ?
                   order by created_at desc, bundle_id desc
                   limit 1""",
                (task_id,),
            ).fetchone()
        return _evidence_from_row(row) if row is not None else None

    def update_task_status(
        self,
        task_id: str,
        status: str,
        *,
        updated_at: str | None = None,
    ) -> None:
        """Update task status without hiding the underlying state transition."""

        updated_at = updated_at or _now()
        with self._connect() as connection:
            self._require_task(connection, task_id)
            connection.execute(
                "update tasks set status = ?, updated_at = ? where task_id = ?",
                (status, updated_at, task_id),
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self.read_only:
            uri = f"file:{self.database_path.as_posix()}?mode=ro"
            connection = sqlite3.connect(uri, uri=True)
        else:
            connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("pragma foreign_keys = on")
        try:
            yield connection
            if not self.read_only:
                connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _require_task(connection: sqlite3.Connection, task_id: str) -> None:
        row = connection.execute("select 1 from tasks where task_id = ?", (task_id,)).fetchone()
        if row is None:
            raise LookupError(f"unknown task {task_id!r}")

    @staticmethod
    def _read_task(connection: sqlite3.Connection, task_id: str) -> TaskRecord:
        row = connection.execute(
            """select task_id, plan_id, title, status, assurance, intent, acceptance_json
               from tasks
               where task_id = ?""",
            (task_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"unknown task {task_id!r}")
        return TaskRecord(
            task_id=row["task_id"],
            plan_id=row["plan_id"],
            title=row["title"],
            status=row["status"],
            assurance=row["assurance"],
            intent=row["intent"],
            acceptance_criteria=_acceptance_criteria_from_json(row["acceptance_json"]),
        )

    @staticmethod
    def _read_attempt(connection: sqlite3.Connection, attempt_id: str) -> RunAttempt:
        row = connection.execute(
            """select attempt_id, task_id, executor, status, summary, started_at, finished_at
               from attempts
               where attempt_id = ?""",
            (attempt_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"unknown attempt {attempt_id!r}")
        return _attempt_from_row(row)


def _attempt_from_row(row: sqlite3.Row) -> RunAttempt:
    attempt = RunAttempt(
        attempt_id=row["attempt_id"],
        task_id=row["task_id"],
        executor=row["executor"],
        status=normalize_attempt_status(row["status"]),
        summary=row["summary"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )
    validate_attempt_timestamps(attempt)
    return attempt


def _evidence_from_row(row: sqlite3.Row) -> AttemptEvidence:
    return AttemptEvidence(
        bundle_id=row["bundle_id"],
        task_id=row["task_id"],
        attempt_id=row["attempt_id"],
        assurance=row["assurance"],
        summary=row["summary"],
        checks=parse_json_string_array(row["checks_json"], field_name="checks_json"),
        artifacts=parse_json_string_array(row["artifacts_json"], field_name="artifacts_json"),
        created_at=row["created_at"],
    )


def _acceptance_criteria_from_json(raw_json: str) -> tuple[str, ...]:
    acceptance_criteria = json.loads(raw_json)
    if not isinstance(acceptance_criteria, list) or not all(
        isinstance(item, str) for item in acceptance_criteria
    ):
        raise ValueError("task acceptance_json must be a JSON array of strings")
    return tuple(acceptance_criteria)


def _string_array(items: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized = tuple(item.strip() for item in items if item.strip())
    if len(normalized) != len(items):
        raise ValueError(f"{field_name} entries must be non-empty strings")
    return normalized


def _validate_attempt_task(attempt: RunAttempt, expected_task_id: str | None) -> None:
    if expected_task_id is not None and attempt.task_id != expected_task_id:
        raise ValueError(
            f"attempt {attempt.attempt_id!r} belongs to task {attempt.task_id!r}, "
            f"not {expected_task_id!r}"
        )


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized
