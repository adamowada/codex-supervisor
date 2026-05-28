"""Simplified run-attempt model.

This module defines the in-memory contract for Stage 3. It does not know about
SQLite, CLI commands, MCP, plugins, or worker launch details.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class AttemptTransitionError(ValueError):
    """Raised when an attempt status transition is invalid."""


class RunAttemptStatus(StrEnum):
    """Status values stored in the simplified planning database."""

    PLANNED = "planned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


TERMINAL_STATUSES = frozenset(
    {
        RunAttemptStatus.SUCCEEDED,
        RunAttemptStatus.FAILED,
        RunAttemptStatus.BLOCKED,
    }
)

NONTERMINAL_STATUSES = frozenset(
    {
        RunAttemptStatus.PLANNED,
        RunAttemptStatus.RUNNING,
    }
)

ALLOWED_TRANSITIONS = {
    RunAttemptStatus.PLANNED: frozenset({RunAttemptStatus.RUNNING, RunAttemptStatus.BLOCKED}),
    RunAttemptStatus.RUNNING: TERMINAL_STATUSES,
    RunAttemptStatus.SUCCEEDED: frozenset(),
    RunAttemptStatus.FAILED: frozenset(),
    RunAttemptStatus.BLOCKED: frozenset(),
}


@dataclass(frozen=True)
class RunAttempt:
    """One try at satisfying a task intent."""

    attempt_id: str
    task_id: str
    executor: str
    status: RunAttemptStatus
    summary: str
    started_at: str | None = None
    finished_at: str | None = None


@dataclass(frozen=True)
class AttemptEvidence:
    """Evidence bundle as read from or written to the simplified planning schema."""

    bundle_id: str
    task_id: str
    attempt_id: str | None
    assurance: str
    summary: str
    checks: tuple[str, ...]
    artifacts: tuple[str, ...]
    created_at: str


def normalize_attempt_status(value: str | RunAttemptStatus) -> RunAttemptStatus:
    """Return a status enum for stored or in-memory values."""

    if isinstance(value, RunAttemptStatus):
        return value
    try:
        return RunAttemptStatus(value.strip().casefold())
    except ValueError as exc:
        allowed = ", ".join(status.value for status in RunAttemptStatus)
        raise AttemptTransitionError(
            f"unknown attempt status {value!r}; expected one of {allowed}"
        ) from exc


def is_terminal_status(value: str | RunAttemptStatus) -> bool:
    """Return whether a status is terminal."""

    return normalize_attempt_status(value) in TERMINAL_STATUSES


def validate_attempt_transition(
    current: str | RunAttemptStatus,
    next_status: str | RunAttemptStatus,
) -> None:
    """Validate a status transition."""

    current_status = normalize_attempt_status(current)
    target_status = normalize_attempt_status(next_status)
    if target_status not in ALLOWED_TRANSITIONS[current_status]:
        raise AttemptTransitionError(
            f"invalid attempt transition {current_status.value!r} -> {target_status.value!r}"
        )


def validate_attempt_timestamps(attempt: RunAttempt) -> None:
    """Validate timestamps against attempt status."""

    if attempt.status is RunAttemptStatus.PLANNED:
        if attempt.started_at is not None or attempt.finished_at is not None:
            raise AttemptTransitionError("planned attempts cannot have timestamps")
        return

    if attempt.status is RunAttemptStatus.RUNNING:
        if attempt.started_at is None:
            raise AttemptTransitionError("running attempts require started_at")
        if attempt.finished_at is not None:
            raise AttemptTransitionError("running attempts cannot have finished_at")
        return

    if attempt.started_at is None:
        raise AttemptTransitionError("terminal attempts require started_at")
    if attempt.finished_at is None:
        raise AttemptTransitionError("terminal attempts require finished_at")
    if attempt.finished_at < attempt.started_at:
        raise AttemptTransitionError("attempt finished_at cannot precede started_at")


def normalize_string_tuple(values: Iterable[str], *, field_name: str) -> tuple[str, ...]:
    """Normalize non-empty strings for storage."""

    raw_values = tuple(values)
    if not all(isinstance(value, str) for value in raw_values):
        raise ValueError(f"{field_name} must contain only strings")
    normalized = tuple(value.strip() for value in raw_values if value.strip())
    if len(normalized) != len(raw_values):
        raise ValueError(f"{field_name} must contain only non-empty strings")
    return normalized


def parse_json_string_array(raw: str, *, field_name: str) -> tuple[str, ...]:
    """Parse a JSON array of strings."""

    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} is invalid JSON: {exc}") from exc
    if not isinstance(decoded, list):
        raise ValueError(f"{field_name} must be a JSON array")
    if not all(isinstance(item, str) and item.strip() for item in decoded):
        raise ValueError(f"{field_name} must contain only non-empty strings")
    return tuple(decoded)


def json_string_array(values: Iterable[str], *, field_name: str) -> str:
    """Serialize non-empty strings as a JSON array."""

    return json.dumps(
        list(normalize_string_tuple(values, field_name=field_name)),
        indent=2,
    )
