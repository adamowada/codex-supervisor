from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from codex_supervisor.planning import (
    PlanAcceptanceCriterionRecord,
    PlanArtifactLinkRecord,
    PlanCommitLinkRecord,
    PlanMilestoneRecord,
    PlanProgressRecord,
    PlanRecord,
    SupervisorTaskRecord,
    WorkerRunRecord,
    initialize_planning_database,
)

FULL_COMMIT_SHA = "0123456789abcdef0123456789abcdef01234567"


def test_planning_integrity_passes_for_valid_database(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-valid",
            slug="valid",
            title="Valid Plan",
            goal="Stay coherent.",
            status="active",
        )
    )
    store.upsert_plan_milestone(
        PlanMilestoneRecord(
            milestone_id="milestone-valid",
            plan_id="plan-valid",
            title="Milestone",
            status="pending",
        )
    )
    store.upsert_plan_acceptance_criterion(
        PlanAcceptanceCriterionRecord(
            criterion_id="criterion-valid",
            plan_id="plan-valid",
            description="Valid criterion.",
            status="pending",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-valid",
            plan_id="plan-valid",
            title="HITL checkpoint",
            goal="Keep active plan structured.",
            task_type="HITL",
            status="ready",
        )
    )

    assert module.check_planning_integrity(db_path) == ()


def test_planning_integrity_requires_current_queue_plan_structure(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-empty",
            slug="empty",
            title="Empty Plan",
            goal="Should not look executable.",
            status="active",
        )
    )
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-blocked-empty",
            slug="blocked-empty",
            title="Blocked Empty Plan",
            goal="Blocked current-queue plans still need structure.",
            status="blocked",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(failure.check_name == "current_queue_plan_without_milestone" for failure in failures)
    assert any(
        failure.check_name == "current_queue_plan_without_acceptance_criterion"
        for failure in failures
    )
    assert any(failure.check_name == "current_queue_plan_without_task" for failure in failures)
    assert any(
        failure.check_name == "current_queue_plan_without_task"
        and failure.reason == "plan-blocked-empty"
        for failure in failures
    )


def test_planning_integrity_requires_open_task_for_current_queue_pending_criteria(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-pending",
            slug="pending",
            title="Pending Plan",
            goal="Expose orphan pending criteria.",
            status="blocked",
        )
    )
    store.upsert_plan_acceptance_criterion(
        PlanAcceptanceCriterionRecord(
            criterion_id="criterion-pending",
            plan_id="plan-pending",
            description="Needs work.",
            status="pending",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "current_queue_pending_criterion_without_open_task"
        for failure in failures
    )


def test_planning_integrity_requires_completed_plans_to_complete_criteria(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-completed",
            slug="completed",
            title="Completed Plan",
            goal="Expose incomplete criteria.",
            status="completed",
        )
    )
    store.upsert_plan_acceptance_criterion(
        PlanAcceptanceCriterionRecord(
            criterion_id="criterion-failed",
            plan_id="plan-completed",
            description="Should have passed.",
            status="failed",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "completed_plan_has_incomplete_criterion"
        and "criterion-failed" in failure.reason
        and "failed" in failure.reason
        for failure in failures
    )


def test_planning_integrity_detects_invalid_json_shapes(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-json",
            slug="json",
            title="JSON Plan",
            goal="Validate JSON.",
            status="active",
        )
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE plans SET context_json = ? WHERE plan_id = ?",
            ('["not", "object"]', "plan-json"),
        )

    failures = module.check_planning_integrity(db_path)

    assert any(failure.check_name == "unexpected_json_type" for failure in failures)


def test_plan_commit_links_reject_short_sha_at_sqlite_layer(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-commit",
            slug="commit",
            title="Commit Evidence Plan",
            goal="Require durable commit evidence.",
            status="active",
        )
    )
    store.add_plan_commit_link(
        PlanCommitLinkRecord(
            plan_id="plan-commit",
            commit_sha=FULL_COMMIT_SHA,
            relationship="implementation",
        )
    )
    with (
        sqlite3.connect(db_path) as connection,
        pytest.raises(sqlite3.IntegrityError),
    ):
        connection.execute(
            "UPDATE plan_commit_links SET commit_sha = ? WHERE plan_id = ?",
            ("abc123", "plan-commit"),
        )


def test_planning_integrity_rejects_commit_links_missing_from_git(tmp_path):
    module = _load_planning_integrity_module()
    subprocess.run(("git", "init"), cwd=tmp_path, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(
        ("git", "config", "user.email", "test@example.com"),
        cwd=tmp_path,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        ("git", "config", "user.name", "Test User"),
        cwd=tmp_path,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        ("git", "config", "commit.gpgsign", "false"),
        cwd=tmp_path,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    (tmp_path / "README.md").write_text("# Test\n", encoding="utf-8")
    subprocess.run(("git", "add", "README.md"), cwd=tmp_path, check=True)
    subprocess.run(
        ("git", "commit", "-m", "Initial"),
        cwd=tmp_path,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-commit",
            slug="commit",
            title="Commit Evidence Plan",
            goal="Require existing commit evidence.",
            status="active",
        )
    )
    store.add_plan_commit_link(
        PlanCommitLinkRecord(
            plan_id="plan-commit",
            commit_sha=FULL_COMMIT_SHA,
            relationship="implementation",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(failure.check_name == "plan_commit_link_missing_git_commit" for failure in failures)


def test_planning_integrity_detects_invalid_status_and_queue_drift(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-drift",
            slug="drift",
            title="Drift Plan",
            goal="Expose drift.",
            status="completed",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-drift",
            plan_id="plan-drift",
            title="Drift task",
            goal="Should not be ready.",
            task_type="AFK",
            status="ready",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(failure.check_name == "open_task_on_inactive_plan" for failure in failures)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE supervisor_tasks SET status = 'wat' WHERE task_id = 'task-drift'"
        )

    failures = module.check_planning_integrity(db_path)

    assert any(failure.check_name == "supervisor_tasks_status" for failure in failures)


def test_planning_integrity_rejects_hidden_nonterminal_worker_runs(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate worker task state.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Run.",
            task_type="AFK",
            status="ready",
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="subagent_explorer",
            status="running",
        )
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE supervisor_tasks SET status = 'completed' WHERE task_id = 'task-worker'"
        )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "nonterminal_worker_run_hidden_by_task_status" for failure in failures
    )


def test_planning_integrity_requires_completed_worker_run_result_path(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate worker evidence.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Run.",
            task_type="AFK",
            status="ready",
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="subagent_explorer",
            status="running",
        )
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE worker_runs SET status = 'completed' WHERE worker_run_id = 'run-worker'"
        )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "completed_worker_run_without_result_path" for failure in failures
    )


def test_planning_integrity_rejects_completed_afk_task_without_worker_evidence(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-blocked",
            slug="blocked",
            title="Blocked Plan",
            goal="Do not hide completed AFK work without evidence.",
            status="blocked",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-completed",
            plan_id="plan-blocked",
            title="Completed task",
            goal="Should have durable evidence.",
            task_type="AFK",
            status="completed",
            acceptance_criteria=["done"],
            verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "completed_afk_task_without_worker_evidence" for failure in failures
    )


def test_planning_integrity_requires_completed_worker_result_artifact_link(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate worker evidence links.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Run.",
            task_type="AFK",
            status="ready",
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="subagent_explorer",
            status="completed",
            result_path="runs/run-worker/result.json",
        )
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            DELETE FROM plan_artifact_links
            WHERE plan_id = 'plan-worker'
              AND artifact_id = 'runs/run-worker/result.json'
              AND relationship = 'worker-result'
            """
        )
    result_path = tmp_path / "runs" / "run-worker" / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(json_worker_result(), encoding="utf-8")

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "completed_worker_run_result_not_linked" for failure in failures
    )

    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-worker",
            artifact_id="runs/run-worker/result.json",
            relationship="supporting-evidence",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "completed_worker_run_result_not_linked" for failure in failures
    )

    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-worker",
            artifact_id="runs/run-worker/result.json",
            relationship="worker-result",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert not any(
        failure.check_name == "completed_worker_run_result_not_linked" for failure in failures
    )


def test_planning_integrity_requires_completed_worker_result_file(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate worker evidence files.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Run.",
            task_type="AFK",
            status="ready",
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="subagent_explorer",
            status="completed",
            result_path="runs/run-worker/result.json",
        )
    )
    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-worker",
            artifact_id="runs/run-worker/result.json",
            relationship="worker-result",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "completed_worker_run_result_missing_on_disk" for failure in failures
    )


def test_planning_integrity_validates_completed_json_worker_result_schema(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate worker evidence schema.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Run.",
            task_type="AFK",
            status="ready",
        )
    )
    result_path = tmp_path / "runs" / "run-worker" / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text('{"status":"done"}', encoding="utf-8")
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="subagent_explorer",
            status="completed",
            result_path="runs/run-worker/result.json",
        )
    )
    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-worker",
            artifact_id="runs/run-worker/result.json",
            relationship="worker-result",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "completed_worker_run_invalid_result_schema" for failure in failures
    )

    result_path.write_text(json_worker_result(), encoding="utf-8")

    failures = module.check_planning_integrity(db_path)

    assert not any(
        failure.check_name == "completed_worker_run_invalid_result_schema" for failure in failures
    )


def test_planning_integrity_requires_worker_result_to_identify_run(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate worker result identity.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Run.",
            task_type="AFK",
            status="ready",
        )
    )
    result_path = tmp_path / "runs" / "run-worker" / "result.json"
    result_path.parent.mkdir(parents=True)
    payload = json.loads(json_worker_result())
    payload.pop("worker_run_id")
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="subagent_explorer",
            status="completed",
            result_path="runs/run-worker/result.json",
        )
    )
    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-worker",
            artifact_id="runs/run-worker/result.json",
            relationship="worker-result",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        "must declare worker_run_id or worker_run_ids" in failure.reason for failure in failures
    )


def test_planning_integrity_allows_shared_worker_result_with_explicit_run_ids(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate shared worker result identity.",
            status="active",
        )
    )
    for worker_run_id in ("run-worker", "run-second"):
        store.upsert_supervisor_task(
            SupervisorTaskRecord(
                task_id=f"task-{worker_run_id}",
                plan_id="plan-worker",
                title=f"Worker task {worker_run_id}",
                goal="Run.",
                task_type="AFK",
                status="ready",
            )
        )
        store.upsert_worker_run(
            WorkerRunRecord(
                worker_run_id=worker_run_id,
                task_id=f"task-{worker_run_id}",
                backend="subagent_explorer",
                status="completed",
                result_path="runs/shared/result.json",
            )
        )
    result_path = tmp_path / "runs" / "shared" / "result.json"
    result_path.parent.mkdir(parents=True)
    payload = json.loads(json_worker_result())
    payload.pop("worker_run_id")
    payload["worker_run_ids"] = ["run-worker", "run-second"]
    payload["changed_files"] = ["runs/shared/result.json"]
    payload["artifacts"] = ["runs/shared/result.json"]
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-worker",
            artifact_id="runs/shared/result.json",
            relationship="worker-result",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert not any(
        "worker_run_ids does not cover this run" in failure.reason for failure in failures
    )

    payload["worker_run_ids"] = ["run-worker"]
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    failures = module.check_planning_integrity(db_path)

    assert any(
        "run-second: worker_run_ids does not cover this run" in failure.reason
        for failure in failures
    )


def test_planning_integrity_rejects_shared_worker_result_with_unknown_run_id(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate shared worker result identity.",
            status="active",
        )
    )
    for worker_run_id in ("run-worker", "run-second"):
        store.upsert_supervisor_task(
            SupervisorTaskRecord(
                task_id=f"task-{worker_run_id}",
                plan_id="plan-worker",
                title=f"Worker task {worker_run_id}",
                goal="Run.",
                task_type="AFK",
                status="ready",
            )
        )
        store.upsert_worker_run(
            WorkerRunRecord(
                worker_run_id=worker_run_id,
                task_id=f"task-{worker_run_id}",
                backend="subagent_explorer",
                status="completed",
                result_path="runs/shared/result.json",
            )
        )
    result_path = tmp_path / "runs" / "shared" / "result.json"
    result_path.parent.mkdir(parents=True)
    payload = json.loads(json_worker_result())
    payload.pop("worker_run_id")
    payload["worker_run_ids"] = ["run-worker", "run-second", "run-missing"]
    payload["changed_files"] = ["runs/shared/result.json"]
    payload["artifacts"] = ["runs/shared/result.json"]
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-worker",
            artifact_id="runs/shared/result.json",
            relationship="worker-result",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        "worker_run_ids entry 'run-missing' does not match a completed worker run" in failure.reason
        for failure in failures
    )


def test_planning_integrity_rejects_shared_worker_result_with_mismatched_result_path(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate shared worker result identity.",
            status="active",
        )
    )
    for worker_run_id in ("run-worker", "run-second"):
        store.upsert_supervisor_task(
            SupervisorTaskRecord(
                task_id=f"task-{worker_run_id}",
                plan_id="plan-worker",
                title=f"Worker task {worker_run_id}",
                goal="Run.",
                task_type="AFK",
                status="ready",
            )
        )
        store.upsert_worker_run(
            WorkerRunRecord(
                worker_run_id=worker_run_id,
                task_id=f"task-{worker_run_id}",
                backend="subagent_explorer",
                status="completed",
                result_path="runs/shared/result.json",
            )
        )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-run-third",
            plan_id="plan-worker",
            title="Worker task run-third",
            goal="Run.",
            task_type="AFK",
            status="ready",
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-third",
            task_id="task-run-third",
            backend="subagent_explorer",
            status="completed",
            result_path="runs/other/result.json",
        )
    )

    shared_path = tmp_path / "runs" / "shared" / "result.json"
    shared_path.parent.mkdir(parents=True)
    shared_payload = json.loads(json_worker_result())
    shared_payload.pop("worker_run_id")
    shared_payload["worker_run_ids"] = ["run-worker", "run-second", "run-third"]
    shared_payload["changed_files"] = ["runs/shared/result.json"]
    shared_payload["artifacts"] = ["runs/shared/result.json"]
    shared_path.write_text(json.dumps(shared_payload), encoding="utf-8")

    other_path = tmp_path / "runs" / "other" / "result.json"
    other_path.parent.mkdir(parents=True)
    other_payload = json.loads(json_worker_result())
    other_payload["worker_run_id"] = "run-third"
    other_payload["changed_files"] = ["runs/other/result.json"]
    other_payload["artifacts"] = ["runs/other/result.json"]
    other_path.write_text(json.dumps(other_payload), encoding="utf-8")

    for artifact_id in ("runs/shared/result.json", "runs/other/result.json"):
        store.add_plan_artifact_link(
            PlanArtifactLinkRecord(
                plan_id="plan-worker",
                artifact_id=artifact_id,
                relationship="worker-result",
            )
        )

    failures = module.check_planning_integrity(db_path)

    assert any(
        "worker_run_ids entry 'run-third' points at runs/other/result.json" in failure.reason
        for failure in failures
    )


def test_planning_integrity_rejects_boolean_acceptance_evidence(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate worker evidence schema.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Run.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["criterion"],
            verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["runs/run-worker/result.json"],
        )
    )
    result_path = tmp_path / "runs" / "run-worker" / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json_worker_result().replace(
            '"acceptance_results":{'
            '"criterion":{"status":"passed","evidence":"Generic criterion satisfied."}'
            "},",
            '"acceptance_results":{"criterion":true},',
        ),
        encoding="utf-8",
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="subagent_explorer",
            status="completed",
            result_path="runs/run-worker/result.json",
        )
    )
    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-worker",
            artifact_id="runs/run-worker/result.json",
            relationship="worker-result",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        "acceptance_results missing passing evidence for criterion" in failure.reason
        for failure in failures
    )


def test_planning_integrity_requires_completed_run_result_status_completed(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate worker result status alignment.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Run.",
            task_type="AFK",
            status="ready",
        )
    )
    result_path = tmp_path / "runs" / "run-worker" / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json_worker_result().replace('"status":"completed"', '"status":"failed"'),
        encoding="utf-8",
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="subagent_explorer",
            status="completed",
            result_path="runs/run-worker/result.json",
        )
    )
    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-worker",
            artifact_id="runs/run-worker/result.json",
            relationship="worker-result",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any("result status must be 'completed'" in failure.reason for failure in failures)


def test_planning_integrity_requires_repo_local_json_worker_result_path(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate worker evidence path.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Run.",
            task_type="AFK",
            status="ready",
        )
    )
    for worker_run_id, result_path in (
        ("run-url", "https://example.test/result.json"),
        ("run-parent", "../result.json"),
        ("run-markdown", "insights/result.md"),
        ("run-fragment", "runs/run-fragment/result.json#summary"),
    ):
        store.upsert_worker_run(
            WorkerRunRecord(
                worker_run_id=worker_run_id,
                task_id="task-worker",
                backend="subagent_explorer",
                status="completed",
                result_path=f"runs/{worker_run_id}/result.json",
            )
        )
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE worker_runs SET result_path = ? WHERE worker_run_id = ?",
                (result_path, worker_run_id),
            )
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                """
                INSERT INTO plan_artifact_links (plan_id, artifact_id, relationship)
                VALUES ('plan-worker', ?, 'worker-result')
                """,
                (result_path,),
            )

    failures = module.check_planning_integrity(db_path)

    assert (
        sum(
            failure.check_name == "completed_worker_run_result_not_repo_local_json"
            for failure in failures
        )
        == 4
    )


def test_planning_integrity_validates_worker_result_field_types(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate worker evidence field types.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Run.",
            task_type="AFK",
            status="ready",
        )
    )
    result_path = tmp_path / "runs" / "run-worker" / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json_worker_result().replace(
            '"changed_files":["runs/run-worker/result.json"]', '"changed_files":{}'
        ),
        encoding="utf-8",
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="subagent_explorer",
            status="completed",
            result_path="runs/run-worker/result.json",
        )
    )
    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-worker",
            artifact_id="runs/run-worker/result.json",
            relationship="worker-result",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any("changed_files" in failure.reason for failure in failures)


def test_planning_integrity_validates_worker_result_test_run_records(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate worker test evidence.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Run.",
            task_type="AFK",
            status="ready",
        )
    )
    result_path = tmp_path / "runs" / "run-worker" / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json_worker_result().replace('"exit_code":0', '"exit_code":1'),
        encoding="utf-8",
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="subagent_explorer",
            status="completed",
            result_path="runs/run-worker/result.json",
        )
    )
    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-worker",
            artifact_id="runs/run-worker/result.json",
            relationship="worker-result",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any("exit_code is 1" in failure.reason for failure in failures)


def test_planning_integrity_requires_completed_worker_result_evidence(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate nonempty worker evidence.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Run.",
            task_type="AFK",
            status="ready",
        )
    )
    result_path = tmp_path / "runs" / "run-worker" / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        "{"
        '"status":"completed",'
        '"summary":" ",'
        '"changed_files":[],'
        '"tests_run":[],'
        '"acceptance_results":{},'
        '"risks":[],'
        '"follow_up_tasks":[],'
        '"artifacts":[],'
        '"handoff_notes":""'
        "}",
        encoding="utf-8",
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="subagent_explorer",
            status="completed",
            result_path="runs/run-worker/result.json",
        )
    )
    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-worker",
            artifact_id="runs/run-worker/result.json",
            relationship="worker-result",
        )
    )

    failures = module.check_planning_integrity(db_path)

    reasons = "\n".join(failure.reason for failure in failures)
    assert "nonempty changed_files" in reasons
    assert "nonempty tests_run" in reasons
    assert "acceptance_results evidence" in reasons
    assert "nonempty artifacts" in reasons
    assert "summary must be nonblank" in reasons
    assert "handoff_notes must be nonblank" in reasons


def test_planning_integrity_requires_worker_result_paths_to_exist(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate worker evidence paths.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Run.",
            task_type="AFK",
            status="ready",
        )
    )
    result_path = tmp_path / "runs" / "run-worker" / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json_worker_result().replace(
            '"changed_files":["runs/run-worker/result.json"]',
            '"changed_files":["src/missing.py"]',
        ),
        encoding="utf-8",
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="subagent_explorer",
            status="completed",
            result_path="runs/run-worker/result.json",
        )
    )
    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-worker",
            artifact_id="runs/run-worker/result.json",
            relationship="worker-result",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any("changed_files entry does not exist" in failure.reason for failure in failures)


def test_planning_integrity_requires_worker_result_artifacts_to_include_result_path(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate self-describing worker evidence.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Run.",
            task_type="AFK",
            status="ready",
        )
    )
    result_path = tmp_path / "runs" / "run-worker" / "result.json"
    result_path.parent.mkdir(parents=True)
    supporting_path = tmp_path / "runs" / "run-worker" / "supporting.json"
    supporting_path.write_text("{}", encoding="utf-8")
    result_path.write_text(
        json_worker_result().replace(
            '"artifacts":["runs/run-worker/result.json"]',
            '"artifacts":["runs/run-worker/supporting.json"]',
        ),
        encoding="utf-8",
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="subagent_explorer",
            status="completed",
            result_path="runs/run-worker/result.json",
        )
    )
    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-worker",
            artifact_id="runs/run-worker/result.json",
            relationship="worker-result",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        "artifacts must include result_path runs/run-worker/result.json" in failure.reason
        for failure in failures
    )


def test_planning_integrity_allows_worker_result_changed_files_to_omit_result_path(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate worker result changed-file evidence.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Run.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["criterion"],
            verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )
    result_path = tmp_path / "runs" / "run-worker" / "result.json"
    result_path.parent.mkdir(parents=True)
    changed_path = tmp_path / "src" / "worker.py"
    changed_path.parent.mkdir(parents=True)
    changed_path.write_text("print('changed')\n", encoding="utf-8")
    result_path.write_text(
        json_worker_result().replace(
            '"changed_files":["runs/run-worker/result.json"]',
            '"changed_files":["src/worker.py"]',
        ),
        encoding="utf-8",
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="subagent_explorer",
            status="completed",
            result_path="runs/run-worker/result.json",
        )
    )
    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-worker",
            artifact_id="runs/run-worker/result.json",
            relationship="worker-result",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert not any(
        "changed_files" in failure.reason and "result_path" in failure.reason
        for failure in failures
    )


def test_planning_integrity_requires_worker_result_to_cover_task_contract(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate worker evidence alignment.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Run.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["one", "two"],
            verification_commands=[
                "uv run --no-sync python -B -m pytest -p no:cacheprovider",
                "python scripts/check_protected_files.py",
            ],
            allowed_paths=["src/**"],
        )
    )
    result_path = tmp_path / "runs" / "run-worker" / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(json_worker_result(), encoding="utf-8")
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="subagent_explorer",
            status="completed",
            result_path="runs/run-worker/result.json",
        )
    )
    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-worker",
            artifact_id="runs/run-worker/result.json",
            relationship="worker-result",
        )
    )

    failures = module.check_planning_integrity(db_path)
    reasons = "\n".join(failure.reason for failure in failures)

    assert (
        "tests_run missing task verification command python scripts/check_protected_files.py"
        in reasons
    )
    assert "acceptance_results does not cover all task criteria" in reasons


def test_planning_integrity_rejects_unsafe_completed_worker_result_commands(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate worker command evidence.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Run.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["criterion"],
            verification_commands=["uv run pytest"],
            allowed_paths=["runs/run-worker/result.json"],
        )
    )
    result_path = tmp_path / "runs" / "run-worker" / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json_worker_result().replace(
            "uv run --no-sync python -B -m pytest -p no:cacheprovider",
            "uv run pytest",
        ),
        encoding="utf-8",
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="subagent_explorer",
            status="completed",
            result_path="runs/run-worker/result.json",
        )
    )
    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-worker",
            artifact_id="runs/run-worker/result.json",
            relationship="worker-result",
        )
    )

    failures = module.check_planning_integrity(db_path)
    reasons = "\n".join(failure.reason for failure in failures)

    assert "tests_run[0].command is unsafe" in reasons
    assert "task verification_commands is unsafe" in reasons


def test_planning_integrity_requires_nonstale_worker_test_summaries(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate worker test summaries.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Run.",
            task_type="AFK",
            status="ready",
        )
    )
    result_path = tmp_path / "runs" / "run-worker" / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json_worker_result().replace(
            '"summary":"passed"',
            '"summary":"Passed at the time of the synthesized audit."',
        ),
        encoding="utf-8",
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="subagent_explorer",
            status="completed",
            result_path="runs/run-worker/result.json",
        )
    )
    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-worker",
            artifact_id="runs/run-worker/result.json",
            relationship="worker-result",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any("summary uses stale evidence phrasing" in failure.reason for failure in failures)


def test_planning_integrity_requires_changed_files_to_match_allowed_paths(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate worker changed-file boundaries.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Run.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["criterion"],
            verification_commands=["uv run pytest"],
            allowed_paths=["src/**"],
        )
    )
    result_path = tmp_path / "runs" / "run-worker" / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(json_worker_result(), encoding="utf-8")
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="subagent_explorer",
            status="completed",
            result_path="runs/run-worker/result.json",
        )
    )
    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-worker",
            artifact_id="runs/run-worker/result.json",
            relationship="worker-result",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "completed_worker_run_changed_file_outside_allowed_paths"
        for failure in failures
    )


@pytest.mark.parametrize(
    ("changed_file", "expected_fragment"),
    [
        ("Src/worker.py", "not covered by allowed_paths"),
        ("src/../README.md", "parent traversal is not allowed"),
    ],
)
def test_planning_integrity_normalizes_worker_result_changed_files_strictly(
    tmp_path,
    changed_file,
    expected_fragment,
):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate worker changed-file normalization.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Run.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["criterion"],
            verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )
    result_path = tmp_path / "runs" / "run-worker" / "result.json"
    result_path.parent.mkdir(parents=True)
    if ".." not in changed_file:
        changed_path = tmp_path / changed_file
        changed_path.parent.mkdir(parents=True)
        changed_path.write_text("print('changed')\n", encoding="utf-8")
    payload = json.loads(json_worker_result())
    payload["changed_files"] = [changed_file]
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="subagent_explorer",
            status="completed",
            result_path="runs/run-worker/result.json",
        )
    )
    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-worker",
            artifact_id="runs/run-worker/result.json",
            relationship="worker-result",
        )
    )

    failures = module.check_planning_integrity(db_path)
    reasons = "\n".join(failure.reason for failure in failures)

    assert expected_fragment in reasons


def test_planning_integrity_reports_schema_drift_without_traceback(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE plans(plan_id TEXT)")

    failures = module.check_planning_integrity(db_path)

    assert any(failure.check_name == "planning_schema" for failure in failures)


def test_planning_integrity_reports_schema_index_drift(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    initialize_planning_database(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP INDEX idx_worker_runs_one_nonterminal_per_task")

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "planning_schema"
        and "idx_worker_runs_one_nonterminal_per_task" in failure.reason
        for failure in failures
    )


def test_planning_integrity_requires_ready_afk_execution_contract(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-ready",
            slug="ready",
            title="Ready Plan",
            goal="Validate ready task contracts.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-ready",
            plan_id="plan-ready",
            title="Ready task",
            goal="Looks ready but cannot run.",
            task_type="AFK",
            status="ready",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "open_afk_task_missing_execution_contract" for failure in failures
    )


def test_planning_integrity_rejects_blank_ready_afk_contract_values(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-ready",
            slug="ready",
            title="Ready Plan",
            goal="Validate ready task contracts.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-ready",
            plan_id="plan-ready",
            title="Ready task",
            goal="Looks ready but cannot run.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["placeholder"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            UPDATE supervisor_tasks
            SET acceptance_criteria_json = ?,
                verification_commands_json = ?,
                allowed_paths_json = ?
            WHERE task_id = ?
            """,
            ('[""]', "[null]", '[" "]', "task-ready"),
        )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "open_afk_task_invalid_execution_contract" for failure in failures
    )


def test_planning_integrity_rejects_bad_string_array_elements_on_historical_tasks(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-history",
            slug="history",
            title="Historical Plan",
            goal="Catch corrupt historical arrays before readers do.",
            status="completed",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-history",
            plan_id="plan-history",
            title="Historical HITL",
            goal="Already handled.",
            task_type="HITL",
            status="completed",
        )
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE supervisor_tasks SET blocked_by_json = ? WHERE task_id = ?",
            ("[null]", "task-history"),
        )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "invalid_json_string_array_value"
        and "blocked_by_json" in failure.reason
        for failure in failures
    )


def test_planning_integrity_rejects_unsafe_ready_afk_contract_values(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-ready",
            slug="ready",
            title="Ready Plan",
            goal="Validate ready task contracts.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-ready",
            plan_id="plan-ready",
            title="Ready task",
            goal="Looks ready but should not run.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["done"],
            verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            UPDATE supervisor_tasks
            SET allowed_paths_json = ?,
                verification_commands_json = ?
            WHERE task_id = ?
            """,
            ('["../**"]', '["rm -rf ."]', "task-ready"),
        )

    failures = module.check_planning_integrity(db_path)
    reasons = "\n".join(failure.reason for failure in failures)

    assert "allowed_paths is unsafe" in reasons
    assert "verification_commands is unsafe" in reasons


def test_planning_integrity_rejects_unsafe_blocked_afk_contract_values(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-blocked",
            slug="blocked",
            title="Blocked Plan",
            goal="Validate blocked task contracts before they become ready.",
            status="blocked",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-blocked",
            plan_id="plan-blocked",
            title="Blocked task",
            goal="Looks blocked but should already have a safe contract.",
            task_type="AFK",
            status="blocked",
            acceptance_criteria=["done"],
            verification_commands=["uv run pytest"],
            allowed_paths=["src/**"],
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "open_afk_task_invalid_execution_contract" for failure in failures
    )


@pytest.mark.parametrize(
    "command",
    [
        "python -c \"open('x', 'w').write('bad')\"",
        "uv run codex-supervisor task-upsert --task-id bad",
        "uv run --no-sync python -B scripts/print_protected_hashes.py "
        "> scripts/check_protected_files.py",
        "pytest",
        "uv run pytest",
        "uv run pytest -p random no:cacheprovider",
        "ruff check .",
        "uv run ruff check .",
        "ruff check --fix . --no-cache",
        "uv run ruff format . --no-cache",
        "mypy src scripts",
        "uv run mypy src scripts",
        "python -m codex_supervisor.cli task-upsert --task-id bad",
        "uv run --no-sync python -B -m codex_supervisor.cli task-list "
        "--path plans/planning.sqlite3",
        "uv run --no-sync python -B -m codex_supervisor.cli task-show ../task",
        "uv run --no-sync codex-supervisor plan-summary --plan-id ../plan",
    ],
)
def test_planning_integrity_rejects_mutating_ready_afk_verification_commands(tmp_path, command):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-ready",
            slug="ready",
            title="Ready Plan",
            goal="Validate ready task commands.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-ready",
            plan_id="plan-ready",
            title="Ready task",
            goal="Looks ready but should not run.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["done"],
            verification_commands=[command],
            allowed_paths=["src/**"],
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any("verification_commands is unsafe" in failure.reason for failure in failures)


def test_planning_integrity_rejects_unsafe_acceptance_criterion_verification_command(
    tmp_path,
):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Exercise integrity drift checks.",
            status="active",
        )
    )
    with store.connect() as connection:
        connection.execute(
            """
            INSERT INTO plan_acceptance_criteria (
                criterion_id, plan_id, description, status, verification_command
            )
            VALUES ('criterion-test', 'plan-test', 'Criterion', 'pending', 'uv run pytest')
            """
        )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "acceptance_criterion_verification_command"
        and "criterion-test.verification_command is unsafe" in failure.reason
        for failure in failures
    )


def test_planning_integrity_rejects_drive_relative_artifact_paths(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Exercise artifact path drift checks.",
            status="active",
        )
    )
    with store.connect() as connection:
        connection.execute(
            """
            INSERT INTO plan_artifact_links (plan_id, artifact_id, relationship)
            VALUES ('plan-test', 'C:relative/path.md', 'evidence')
            """
        )
        connection.execute(
            """
            INSERT INTO plan_progress_events (
                progress_id, plan_id, event_type, summary, details,
                linked_artifact_id, occurred_at
            )
            VALUES (
                'progress-test', 'plan-test', 'noted', 'Progress', NULL,
                'C:relative/path.md', '2026-05-24T00:00:00Z'
            )
            """
        )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "planning_artifact_path" and "C:relative/path.md" in failure.reason
        for failure in failures
    )


@pytest.mark.parametrize(
    "command",
    [
        "python -B -m pytest -p no:cacheprovider",
        "uv run --no-sync python -B -m pytest -p no:cacheprovider",
        "ruff check . --no-cache",
        "uv run --no-sync ruff format --check . --no-cache",
        "mypy --no-incremental src scripts",
        "uv run --no-sync mypy --no-incremental src scripts",
        "python -B -m codex_supervisor.cli --help",
        "uv run --no-sync python -B -m codex_supervisor.cli --help",
        "uv run --no-sync python -B -m codex_supervisor.cli story-loop-status",
        "uv run --no-sync python -B -m codex_supervisor.cli task-list --status ready",
        "uv run --no-sync python -B -m codex_supervisor.cli task-show task-ready --json",
        "uv run --no-sync codex-supervisor goal-contract-render --task-id task-ready --json",
    ],
)
def test_planning_integrity_accepts_cache_safe_ready_afk_verification_commands(
    tmp_path,
    command,
):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-ready",
            slug="ready",
            title="Ready Plan",
            goal="Validate ready task commands.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-ready",
            plan_id="plan-ready",
            title="Ready task",
            goal="Looks ready.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["done"],
            verification_commands=[command],
            allowed_paths=["src/**"],
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert not any("verification_commands is unsafe" in failure.reason for failure in failures)


def test_planning_integrity_requires_progress_links_to_be_declared_artifacts(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-progress",
            slug="progress",
            title="Progress Plan",
            goal="Validate progress links.",
            status="active",
        )
    )
    store.add_plan_progress(
        PlanProgressRecord(
            progress_id="progress-linked",
            plan_id="plan-progress",
            event_type="linked",
            summary="Links an undeclared artifact.",
            linked_artifact_id="insights/missing.md",
        )
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "DELETE FROM plan_artifact_links WHERE plan_id = ? AND artifact_id = ?",
            ("plan-progress", "insights/missing.md"),
        )

    failures = module.check_planning_integrity(db_path)

    assert any(failure.check_name == "progress_link_missing_artifact_link" for failure in failures)

    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-progress",
            artifact_id="insights/missing.md",
            relationship="progress-evidence",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert not any(
        failure.check_name == "progress_link_missing_artifact_link" for failure in failures
    )


def test_planning_integrity_requires_plan_timestamps_to_cover_progress(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-timestamp",
            slug="timestamp",
            title="Timestamp Plan",
            goal="Validate progress timestamp coverage.",
            status="active",
        )
    )
    store.add_plan_progress(
        PlanProgressRecord(
            progress_id="progress-future",
            plan_id="plan-timestamp",
            event_type="future",
            summary="Future progress.",
        )
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE plan_progress_events SET occurred_at = ? WHERE progress_id = ?",
            ("2099-01-01T00:00:00Z", "progress-future"),
        )

    failures = module.check_planning_integrity(db_path)

    assert any(failure.check_name == "plan_updated_at_trails_progress" for failure in failures)


def json_worker_result() -> str:
    return (
        "{"
        '"worker_run_id":"run-worker",'
        '"status":"completed",'
        '"summary":"Done.",'
        '"changed_files":["runs/run-worker/result.json"],'
        '"tests_run":[{'
        '"command":"uv run --no-sync python -B -m pytest -p no:cacheprovider",'
        '"exit_code":0,'
        '"summary":"passed"'
        "}],"
        '"acceptance_results":{'
        '"criterion":{"status":"passed","evidence":"Generic criterion satisfied."}'
        "},"
        '"risks":[],'
        '"follow_up_tasks":[],'
        '"artifacts":["runs/run-worker/result.json"],'
        '"handoff_notes":"Recorded."'
        "}"
    )


def _load_planning_integrity_module() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "check_planning_integrity.py"
    spec = importlib.util.spec_from_file_location("check_planning_integrity", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
