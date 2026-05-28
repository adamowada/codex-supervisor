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
class TaskRecord:
    """Task row needed by the simplified execution layer."""

    task_id: str
    plan_id: str
    title: str
    status: str
    assurance: str
    intent: str
    acceptance_criteria: tuple[str, ...]


class AttemptStore:
    """Small store for `attempts` and `evidence_bundles` rows."""

    def __init__(self, database_path: Path, *, read_only: bool = False) -> None:
        self.database_path = database_path
        self.read_only = read_only

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
        summary: str | None = None,
        started_at: str | None = None,
    ) -> RunAttempt:
        """Move a planned attempt to running."""

        started_at = started_at or _now()
        with self._connect() as connection:
            current = self._read_attempt(connection, attempt_id)
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
        finished_at: str | None = None,
    ) -> RunAttempt:
        """Move an attempt to a terminal status."""

        target_status = normalize_attempt_status(status)
        if target_status is RunAttemptStatus.PLANNED or target_status is RunAttemptStatus.RUNNING:
            raise ValueError("complete_attempt requires a terminal status")

        finished_at = finished_at or _now()
        with self._connect() as connection:
            current = self._read_attempt(connection, attempt_id)
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
        acceptance_criteria = json.loads(row["acceptance_json"])
        if not isinstance(acceptance_criteria, list) or not all(
            isinstance(item, str) for item in acceptance_criteria
        ):
            raise ValueError("task acceptance_json must be a JSON array of strings")
        return TaskRecord(
            task_id=row["task_id"],
            plan_id=row["plan_id"],
            title=row["title"],
            status=row["status"],
            assurance=row["assurance"],
            intent=row["intent"],
            acceptance_criteria=tuple(acceptance_criteria),
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


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized
