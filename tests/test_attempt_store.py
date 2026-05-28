from __future__ import annotations

from pathlib import Path

import pytest
from planning_db_factory import insert_task, make_planning_db

from codex_supervisor.attempt_store import AttemptStore
from codex_supervisor.attempts import AttemptTransitionError, RunAttemptStatus


def test_attempt_store_runs_lifecycle_and_attaches_evidence(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)
    store = AttemptStore(db_path)

    planned = store.create_attempt(
        task_id="task-1",
        executor="manual",
        summary="Manual attempt planned.",
        attempt_id="attempt-1",
    )
    running = store.start_attempt(
        "attempt-1",
        summary="Manual attempt running.",
        started_at="2026-05-28T17:00:00Z",
    )
    completed = store.complete_attempt(
        "attempt-1",
        status="succeeded",
        summary="Manual attempt succeeded.",
        finished_at="2026-05-28T17:01:00Z",
    )
    evidence = store.attach_evidence_bundle(
        task_id="task-1",
        attempt_id="attempt-1",
        assurance="medium",
        summary="Evidence attached.",
        checks=("pytest tests/test_attempt_store.py",),
        artifacts=("src/codex_supervisor/attempt_store.py",),
        bundle_id="evidence-1",
        created_at="2026-05-28T17:01:00Z",
    )

    assert planned.status == RunAttemptStatus.PLANNED
    assert running.status == RunAttemptStatus.RUNNING
    assert completed.status == RunAttemptStatus.SUCCEEDED
    assert evidence.checks == ("pytest tests/test_attempt_store.py",)
    assert store.read_attempt("attempt-1").finished_at == "2026-05-28T17:01:00Z"
    assert store.list_active_attempts("task-1") == ()


def test_attempt_store_rejects_invalid_transition(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)
    store = AttemptStore(db_path)
    store.create_attempt(
        task_id="task-1",
        executor="manual",
        summary="Manual attempt planned.",
        attempt_id="attempt-1",
    )

    with pytest.raises(AttemptTransitionError, match="invalid attempt transition"):
        store.complete_attempt(
            "attempt-1",
            status="succeeded",
            summary="Cannot skip running.",
            finished_at="2026-05-28T17:01:00Z",
        )


def test_attempt_store_rejects_evidence_for_another_task(tmp_path: Path) -> None:
    db_path = make_planning_db(tmp_path)
    store = AttemptStore(db_path)
    store.create_attempt(
        task_id="task-1",
        executor="manual",
        summary="Manual attempt planned.",
        attempt_id="attempt-1",
    )
    insert_task(db_path, task_id="task-2", status="ready")

    with pytest.raises(ValueError, match="task_id must match"):
        store.attach_evidence_bundle(
            task_id="task-2",
            attempt_id="attempt-1",
            assurance="medium",
            summary="Wrong task.",
            checks=("pytest",),
            artifacts=("artifact",),
        )
