from __future__ import annotations

import pytest

from codex_supervisor.attempts import (
    AttemptTransitionError,
    RunAttempt,
    RunAttemptStatus,
    json_string_array,
    normalize_attempt_status,
    parse_json_string_array,
    validate_attempt_timestamps,
    validate_attempt_transition,
)


def test_attempt_status_normalization_and_terminal_transitions() -> None:
    assert normalize_attempt_status(" SUCCEEDED ") == RunAttemptStatus.SUCCEEDED

    validate_attempt_transition("planned", "running")
    validate_attempt_transition("running", "succeeded")

    with pytest.raises(AttemptTransitionError, match="invalid attempt transition"):
        validate_attempt_transition("succeeded", "running")


def test_attempt_timestamps_follow_status_shape() -> None:
    validate_attempt_timestamps(
        RunAttempt(
            attempt_id="attempt-1",
            task_id="task-1",
            executor="manual",
            status=RunAttemptStatus.PLANNED,
            summary="Waiting to start.",
        )
    )
    validate_attempt_timestamps(
        RunAttempt(
            attempt_id="attempt-1",
            task_id="task-1",
            executor="manual",
            status=RunAttemptStatus.RUNNING,
            summary="Running.",
            started_at="2026-05-28T17:00:00Z",
        )
    )
    validate_attempt_timestamps(
        RunAttempt(
            attempt_id="attempt-1",
            task_id="task-1",
            executor="manual",
            status=RunAttemptStatus.SUCCEEDED,
            summary="Done.",
            started_at="2026-05-28T17:00:00Z",
            finished_at="2026-05-28T17:01:00Z",
        )
    )

    with pytest.raises(AttemptTransitionError, match="finished_at cannot precede"):
        validate_attempt_timestamps(
            RunAttempt(
                attempt_id="attempt-1",
                task_id="task-1",
                executor="manual",
                status=RunAttemptStatus.SUCCEEDED,
                summary="Impossible.",
                started_at="2026-05-28T17:01:00Z",
                finished_at="2026-05-28T17:00:00Z",
            )
        )


def test_evidence_json_arrays_are_non_empty_strings() -> None:
    raw = json_string_array((" pytest ", "artifact check"), field_name="checks")

    assert parse_json_string_array(raw, field_name="checks") == ("pytest", "artifact check")

    with pytest.raises(ValueError, match="JSON array"):
        parse_json_string_array('{"not": "an array"}', field_name="checks")
    with pytest.raises(ValueError, match="non-empty strings"):
        parse_json_string_array('["ok", ""]', field_name="checks")
