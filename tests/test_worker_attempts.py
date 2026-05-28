from __future__ import annotations

import sqlite3
from pathlib import Path

from planning_db_factory import make_planning_db

from codex_supervisor.attempt_store import AttemptStore
from codex_supervisor.worker_attempts import (
    FakeCodexWorker,
    WorkerResult,
    build_live_worker_verification_plan,
    build_worker_prompt,
    run_fake_worker_attempt,
)


def test_worker_prompt_includes_task_intent_and_assurance_policy(tmp_path: Path) -> None:
    db_path = _make_high_assurance_db(tmp_path)
    task = AttemptStore(db_path).read_task("task-1")

    prompt = build_worker_prompt(task)

    assert "task_id: task-1" in prompt
    assert "assurance: high" in prompt
    assert "Acceptance criterion" in prompt
    assert "- strict checks" in prompt
    assert "- risk notes" in prompt


def test_fake_worker_attempt_records_evidence_and_accepts_high_assurance(tmp_path: Path) -> None:
    db_path = _make_high_assurance_db(tmp_path)

    result = run_fake_worker_attempt(
        db_path,
        task_id="task-1",
        attempt_id="attempt-worker-1",
    )

    assert result.transition.task_status == "done"
    assert result.transition.acceptance is not None
    assert result.transition.acceptance["accepted"] is True
    assert result.transition.evidence is not None
    assert result.transition.evidence["assurance"] == "high"
    assert "assurance: high" in result.prompt


def test_high_assurance_worker_result_without_risk_blocks_task(tmp_path: Path) -> None:
    db_path = _make_high_assurance_db(tmp_path)
    worker = FakeCodexWorker(
        WorkerResult(
            status="succeeded",
            summary="Worker result is missing risk notes.",
            checks=("fake-worker: check",),
            artifacts=("worker-output: fake result",),
            acceptance_results={"Acceptance criterion": True},
        )
    )

    result = run_fake_worker_attempt(
        db_path,
        task_id="task-1",
        attempt_id="attempt-worker-1",
        worker=worker,
    )

    assert result.transition.task_status == "blocked"
    assert result.transition.acceptance is not None
    assert "risk_notes" in result.transition.acceptance["missing_requirements"]


def test_live_worker_verification_plan_is_bounded(tmp_path: Path) -> None:
    db_path = _make_high_assurance_db(tmp_path)
    task = AttemptStore(db_path).read_task("task-1")

    plan = build_live_worker_verification_plan(task, timeout_seconds=90)

    assert plan.timeout_seconds == 90
    assert plan.command[:2] == ("codex", "exec")
    assert "bounded timeout" in plan.required_evidence
    assert "acceptance evaluation" in plan.required_evidence


def _make_high_assurance_db(tmp_path: Path) -> Path:
    db_path = make_planning_db(tmp_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """update tasks
               set assurance = 'high',
                   intent = 'Connect a fresh-context Codex worker through the compact model'
               where task_id = 'task-1'"""
        )
        connection.commit()
    finally:
        connection.close()
    return db_path
