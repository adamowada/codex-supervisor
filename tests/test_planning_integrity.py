from __future__ import annotations

import hashlib
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
    WorkerResultRecord,
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


def test_planning_integrity_requires_completed_full_afk_task_commit_link(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-full-afk",
            slug="full-afk",
            title="Full AFK Plan",
            goal="Do unattended work.",
            status="completed",
        )
    )
    store.upsert_plan_acceptance_criterion(
        PlanAcceptanceCriterionRecord(
            criterion_id="criterion-full-afk",
            plan_id="plan-full-afk",
            description="Implementation completed.",
            status="completed",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-full-afk",
            plan_id="plan-full-afk",
            title="Build app",
            goal="Finish the app.",
            task_type="AFK",
            status="completed",
            scope={"full_afk": True, "publication_required": True, "final_commit_required": True},
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "completed_publication_required_task_without_commit_link"
        and "task-full-afk" in failure.reason
        for failure in failures
    )


def test_planning_integrity_accepts_completed_full_afk_task_with_commit_link(tmp_path):
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
    commit_sha = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-full-afk",
            slug="full-afk",
            title="Full AFK Plan",
            goal="Do unattended work.",
            status="completed",
        )
    )
    store.upsert_plan_acceptance_criterion(
        PlanAcceptanceCriterionRecord(
            criterion_id="criterion-full-afk",
            plan_id="plan-full-afk",
            description="Implementation completed.",
            status="completed",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-full-afk",
            plan_id="plan-full-afk",
            title="Build app",
            goal="Finish the app.",
            task_type="AFK",
            status="completed",
            scope={"final_commit_required": True},
        )
    )
    store.add_plan_commit_link(
        PlanCommitLinkRecord(
            plan_id="plan-full-afk",
            commit_sha=commit_sha,
            relationship="final-project-state",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert not any(
        failure.check_name == "completed_publication_required_task_without_commit_link"
        for failure in failures
    )


def test_planning_integrity_requires_final_state_commit_relationship(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-full-afk",
            slug="full-afk",
            title="Full AFK Plan",
            goal="Do unattended work.",
            status="completed",
        )
    )
    store.upsert_plan_acceptance_criterion(
        PlanAcceptanceCriterionRecord(
            criterion_id="criterion-full-afk",
            plan_id="plan-full-afk",
            description="Implementation completed.",
            status="completed",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-full-afk",
            plan_id="plan-full-afk",
            title="Build app",
            goal="Finish the app.",
            task_type="AFK",
            status="completed",
            scope={"final_commit_required": True},
        )
    )
    store.add_plan_commit_link(
        PlanCommitLinkRecord(
            plan_id="plan-full-afk",
            commit_sha=FULL_COMMIT_SHA,
            relationship="implementation",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "completed_final_commit_required_task_without_final_state_commit_link"
        for failure in failures
    )


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


def test_planning_integrity_requires_completed_worker_run_result_record(tmp_path):
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
        failure.check_name == "completed_worker_run_without_result_record" for failure in failures
    )


def test_planning_integrity_requires_full_afk_codex_exec_raw_evidence_paths(tmp_path):
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
            status="completed",
            scope={"full_afk": True},
        )
    )
    result_id = _upsert_db_worker_result(store)
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="codex_exec",
            status="completed",
            result_id=result_id,
            metadata={},
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "completed_codex_exec_run_without_raw_evidence_paths"
        for failure in failures
    )


def test_planning_integrity_allows_ignored_evidence_paths_in_clean_checkout(tmp_path):
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
            status="completed",
            scope={"full_afk": True},
        )
    )
    result_id = _upsert_db_worker_result(store)
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="codex_exec",
            status="completed",
            result_id=result_id,
            prompt_path="runs/run-worker/prompt.md",
            jsonl_path="runs/run-worker/events.jsonl",
            metadata={
                "raw_evidence_paths": {
                    "artifact_directory": "artifacts/run-worker",
                    "jsonl": "runs/run-worker/events.jsonl",
                    "prompt": "runs/run-worker/prompt.md",
                    "raw_result": "artifacts/run-worker/worker-result.raw.json",
                    "run_directory": "runs/run-worker",
                    "worktree": "worktrees/run-worker",
                },
                "evidence_manifest_path": "artifacts/run-worker/evidence-manifest.json",
            },
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert not any(
        failure.check_name
        in {
            "completed_worker_run_indexed_evidence_missing",
            "completed_worker_run_evidence_manifest_missing",
        }
        for failure in failures
    )


def test_planning_integrity_rejects_missing_ignored_evidence_when_root_exists(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    (tmp_path / "runs").mkdir()
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
            status="completed",
            scope={"full_afk": True},
        )
    )
    result_id = _upsert_db_worker_result(store)
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="codex_exec",
            status="completed",
            result_id=result_id,
            prompt_path="runs/run-worker/prompt.md",
            metadata={"raw_evidence_paths": {"prompt": "runs/run-worker/prompt.md"}},
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "completed_worker_run_indexed_evidence_missing"
        and "runs/run-worker/prompt.md" in failure.reason
        for failure in failures
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


def test_planning_integrity_allows_completed_afk_review_task_with_review_evidence(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-review",
            slug="review",
            title="Review Plan",
            goal="Allow separate AFK review tasks to close with review evidence.",
            status="blocked",
        )
    )
    store.add_plan_progress(
        PlanProgressRecord(
            progress_id="progress-review",
            plan_id="plan-review",
            event_type="review_result_recorded",
            summary="Review accepted.",
            details=json.dumps(
                {
                    "review_id": "review-task-source",
                    "target": "task-source",
                    "finding_counts": {"accepted": 0, "waived": 0, "needs_hitl": 0},
                    "accepted_findings": [],
                }
            ),
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-review",
            plan_id="plan-review",
            title="Review source task",
            goal="Review the source worker result.",
            task_type="AFK",
            status="completed",
            scope={
                "review_gate": "separate_review_required_task",
                "source_task_id": "task-source",
            },
            acceptance_criteria=["review done"],
            verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["plans/planning.sqlite3"],
            worker_backend="codex_review",
            review_required=False,
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert not any(
        failure.check_name == "completed_afk_task_without_worker_evidence"
        and "task-review" in failure.reason
        for failure in failures
    )


def test_planning_integrity_allows_completed_manual_promotion_task_with_progress_evidence(
    tmp_path,
):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-promotion",
            slug="promotion",
            title="Promotion Plan",
            goal="Allow controller promotion bookkeeping with durable evidence.",
            status="blocked",
        )
    )
    store.add_plan_progress(
        PlanProgressRecord(
            progress_id="progress-promotion-completed",
            plan_id="plan-promotion",
            event_type="promotion_completed",
            summary="Promotion copied worker output into the main checkout.",
            details=json.dumps(
                {
                    "task_id": "task-promote",
                    "source_task_id": "task-build",
                    "commit_sha": FULL_COMMIT_SHA,
                }
            ),
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-promote",
            plan_id="plan-promotion",
            title="Promote worker output",
            goal="Copy reviewed worker output into the main checkout.",
            task_type="AFK",
            status="completed",
            acceptance_criteria=["promotion done"],
            verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["plans/planning.sqlite3"],
            worker_backend="manual",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert not any(
        failure.check_name == "completed_afk_task_without_worker_evidence"
        and "task-promote" in failure.reason
        for failure in failures
    )


def test_planning_integrity_rejects_promotion_of_review_required_source_without_review(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-promotion",
            slug="promotion",
            title="Promotion Plan",
            goal="Require review before promotion closes reviewed work.",
            status="blocked",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-source",
            plan_id="plan-promotion",
            title="Source task",
            goal="Produce review-required work.",
            task_type="AFK",
            status="cancelled",
            acceptance_criteria=["done"],
            verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
            review_required=True,
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-promote",
            plan_id="plan-promotion",
            title="Promote worker output",
            goal="Copy reviewed worker output into the main checkout.",
            task_type="AFK",
            status="completed",
            acceptance_criteria=["promotion done"],
            verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["plans/planning.sqlite3"],
            worker_backend="manual",
        )
    )
    store.add_plan_progress(
        PlanProgressRecord(
            progress_id="progress-promotion-completed",
            plan_id="plan-promotion",
            event_type="promotion_completed",
            summary="Promotion copied worker output into the main checkout.",
            details=json.dumps(
                {
                    "task_id": "task-promote",
                    "source_task_id": "task-source",
                    "commit_sha": FULL_COMMIT_SHA,
                }
            ),
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "promotion_of_review_required_task_without_review_result"
        for failure in failures
    )


def test_planning_integrity_rejects_completed_review_required_task_without_review_result(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-review-required",
            slug="review-required",
            title="Review Required Plan",
            goal="Do not hide completed review-required work without review evidence.",
            status="active",
        )
    )
    store.add_plan_progress(
        PlanProgressRecord(
            progress_id="progress-review-enforcement",
            plan_id="plan-review-required",
            event_type="review_enforcement_enabled",
            summary="Review enforcement is active.",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-review-required",
            title="Completed task",
            goal="Should have durable review evidence.",
            task_type="AFK",
            status="completed",
            acceptance_criteria=["criterion"],
            verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["runs/**"],
            review_required=True,
        )
    )
    result_id = _upsert_db_worker_result(store)
    _complete_worker_run_with_result(store, task_id="task-worker", result_id=result_id)

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "completed_review_required_task_without_review_result"
        for failure in failures
    )


def test_planning_integrity_requires_full_afk_review_required_task_to_use_afk_review(
    tmp_path,
):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-review-required",
            slug="review-required",
            title="Review Required Plan",
            goal="Do not hide full-AFK review behind manual bookkeeping.",
            status="active",
        )
    )
    store.add_plan_progress(
        PlanProgressRecord(
            progress_id="progress-review-enforcement",
            plan_id="plan-review-required",
            event_type="review_enforcement_enabled",
            summary="Review enforcement is active.",
        )
    )
    store.add_plan_progress(
        PlanProgressRecord(
            progress_id="progress-review-result",
            plan_id="plan-review-required",
            event_type="review_result_recorded",
            summary="Review recorded.",
            details=json.dumps(
                {
                    "review_id": "review-worker",
                    "target": "task-worker",
                    "accepted_findings": [],
                }
            ),
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-review-required",
            title="Completed task",
            goal="Should have an AFK review lane.",
            task_type="AFK",
            status="completed",
            scope={"full_afk": True},
            acceptance_criteria=["criterion"],
            verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["runs/**"],
            review_required=True,
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-review-worker",
            plan_id="plan-review-required",
            title="Manual review task",
            goal="This should not satisfy full-AFK review by default.",
            task_type="HITL",
            status="completed",
            scope={
                "review_gate": "separate_review_required_task",
                "source_task_id": "task-worker",
            },
            worker_backend="manual",
            review_required=False,
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "completed_full_afk_review_required_task_without_afk_review_task"
        for failure in failures
    )


def test_planning_integrity_rejects_unrouted_accepted_review_findings(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-review-required",
            slug="review-required",
            title="Review Required Plan",
            goal="Require accepted review findings to route into repair tasks.",
            status="active",
        )
    )
    store.add_plan_progress(
        PlanProgressRecord(
            progress_id="progress-review-enforcement",
            plan_id="plan-review-required",
            event_type="review_enforcement_enabled",
            summary="Review enforcement is active.",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-review-required",
            title="Completed task",
            goal="Should have routed review findings.",
            task_type="AFK",
            status="completed",
            acceptance_criteria=["criterion"],
            verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["runs/**"],
            review_required=True,
        )
    )
    result_id = _upsert_db_worker_result(store)
    _complete_worker_run_with_result(store, task_id="task-worker", result_id=result_id)
    store.add_plan_progress(
        PlanProgressRecord(
            progress_id="progress-review",
            plan_id="plan-review-required",
            event_type="review_result_recorded",
            summary="Recorded review.",
            details=json.dumps(
                {
                    "review_id": "review-worker",
                    "target": "task-worker",
                    "accepted_findings": [{"finding_id": "finding-accepted"}],
                    "waived_findings": [],
                    "needs_hitl_findings": [],
                }
            ),
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "completed_review_required_task_without_routed_finding"
        for failure in failures
    )


def test_planning_integrity_requires_worker_result_run_link(tmp_path):
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
    _upsert_db_worker_result(store)

    failures = module.check_planning_integrity(db_path)

    assert any(failure.check_name == "worker_result_without_run_link" for failure in failures)

    _complete_worker_run_with_result(store)
    failures = module.check_planning_integrity(db_path)

    assert not any(failure.check_name == "worker_result_without_run_link" for failure in failures)


def test_planning_integrity_rejects_completed_run_that_lost_indexed_evidence_paths(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Preserve raw worker evidence paths.",
            status="blocked",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Produce evidence.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["done"],
            verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
            review_required=False,
        )
    )
    _upsert_db_worker_result(store)
    _complete_worker_run_with_result(store)
    evidence_dir = tmp_path / "runs" / "run-worker"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "prompt.md").write_text("prompt", encoding="utf-8")
    (evidence_dir / "session.jsonl").write_text("{}", encoding="utf-8")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            UPDATE worker_runs
            SET prompt_path = ?,
                jsonl_path = ?,
                metadata_json = ?
            WHERE worker_run_id = 'run-worker'
            """,
            (
                "runs/run-worker/prompt.md",
                "runs/run-worker/session.jsonl",
                json.dumps(
                    {
                        "raw_evidence_paths": {
                            "prompt": "runs/run-worker/original-prompt.md",
                            "jsonl": "runs/run-worker/session.jsonl",
                        }
                    },
                    sort_keys=True,
                ),
            ),
        )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "completed_worker_run_indexed_evidence_drift" for failure in failures
    )


def test_planning_integrity_rejects_mutated_raw_worker_result_evidence(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Preserve immutable worker result evidence.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker task",
            goal="Produce evidence.",
            task_type="AFK",
            status="running",
            acceptance_criteria=["criterion"],
            verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="codex_exec",
            status="running",
        )
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "worker.py").write_text("print('ok')\n", encoding="utf-8")
    result_path = tmp_path / "artifacts" / "run-worker" / "worker-result.raw.json"
    result_path.parent.mkdir(parents=True)
    payload = json.loads(json_worker_result())
    payload["changed_files"] = ["src/worker.py"]
    payload["artifacts"] = ["artifacts/run-worker/worker-result.raw.json"]
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    raw_bytes = result_path.read_bytes()
    manifest_path = tmp_path / "artifacts" / "run-worker" / "evidence-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "worker_run_id": "run-worker",
                "task_id": "task-worker",
                "status": "completed",
                "paths": {
                    "raw_result": {
                        "exists": True,
                        "bytes": len(raw_bytes),
                        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    store.ingest_worker_result("run-worker", "artifacts/run-worker/worker-result.raw.json")
    payload["summary"] = "Edited."
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            UPDATE worker_runs
            SET metadata_json = ?
            WHERE worker_run_id = 'run-worker'
            """,
            (
                json.dumps(
                    {"evidence_manifest_path": "artifacts/run-worker/evidence-manifest.json"}
                ),
            ),
        )

    failures = module.check_planning_integrity(db_path)

    assert any(failure.check_name == "worker_result_source_hash_drift" for failure in failures)
    assert any(
        failure.check_name == "completed_worker_run_evidence_manifest_hash_drift"
        for failure in failures
    )


def test_planning_integrity_rejects_worker_results_directory(tmp_path):
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
    (tmp_path / "worker-results").mkdir()

    failures = module.check_planning_integrity(db_path)

    assert any(failure.check_name == "worker_results_directory_exists" for failure in failures)


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
    _upsert_db_worker_result(store, payload={"status": "done"})
    _complete_worker_run_with_result(store)

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "completed_worker_run_invalid_result_schema" for failure in failures
    )

    _upsert_db_worker_result(store, payload=json.loads(json_worker_result()))

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
    payload = json.loads(json_worker_result())
    payload.pop("worker_run_id")
    _upsert_db_worker_result(store, payload=payload)
    _complete_worker_run_with_result(store)

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
    payload = json.loads(json_worker_result())
    payload.pop("worker_run_id")
    payload["worker_run_ids"] = ["run-worker", "run-second"]
    _upsert_db_worker_result(store, payload=payload, result_id="worker-result-shared")
    for worker_run_id in ("run-worker", "run-second"):
        _complete_worker_run_with_result(
            store,
            worker_run_id=worker_run_id,
            task_id=f"task-{worker_run_id}",
            result_id="worker-result-shared",
        )

    failures = module.check_planning_integrity(db_path)

    assert not any(
        "worker_run_ids does not cover this run" in failure.reason for failure in failures
    )

    payload["worker_run_ids"] = ["run-worker"]
    _upsert_db_worker_result(store, payload=payload, result_id="worker-result-shared")

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
    payload = json.loads(json_worker_result())
    payload.pop("worker_run_id")
    payload["worker_run_ids"] = ["run-worker", "run-second", "run-missing"]
    _upsert_db_worker_result(store, payload=payload, result_id="worker-result-shared")
    for worker_run_id in ("run-worker", "run-second"):
        _complete_worker_run_with_result(
            store,
            worker_run_id=worker_run_id,
            task_id=f"task-{worker_run_id}",
            result_id="worker-result-shared",
        )

    failures = module.check_planning_integrity(db_path)

    assert any(
        "worker_run_ids entry 'run-missing' does not match a completed worker run" in failure.reason
        for failure in failures
    )


def test_planning_integrity_rejects_shared_worker_result_with_mismatched_result_id(tmp_path):
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
    shared_payload = json.loads(json_worker_result())
    shared_payload.pop("worker_run_id")
    shared_payload["worker_run_ids"] = ["run-worker", "run-second", "run-third"]
    other_payload = json.loads(json_worker_result())
    other_payload["worker_run_id"] = "run-third"
    _upsert_db_worker_result(store, payload=shared_payload, result_id="worker-result-shared")
    _upsert_db_worker_result(store, payload=other_payload, result_id="worker-result-other")
    for worker_run_id in ("run-worker", "run-second"):
        _complete_worker_run_with_result(
            store,
            worker_run_id=worker_run_id,
            task_id=f"task-{worker_run_id}",
            result_id="worker-result-shared",
        )
    _complete_worker_run_with_result(
        store,
        worker_run_id="run-third",
        task_id="task-run-third",
        result_id="worker-result-other",
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        "worker_run_ids entry 'run-third' points at worker-result-other" in failure.reason
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

    assert any(failure.check_name == "worker_result_status_mismatch" for failure in failures)


def test_planning_integrity_rejects_worker_run_result_path_references(tmp_path):
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
    _upsert_db_worker_result(store)
    _complete_worker_run_with_result(store)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE worker_runs SET result_path = ? WHERE worker_run_id = ?",
            ("worker-results/run-worker-result.json", "run-worker"),
        )

    failures = module.check_planning_integrity(db_path)

    assert any(failure.check_name == "worker_result_filesystem_reference" for failure in failures)


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
    assert "summary must be nonblank" in reasons
    assert "handoff_notes must be nonblank" in reasons


def test_planning_integrity_rejects_worker_results_paths_in_db_records(tmp_path):
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
    payload = json.loads(json_worker_result())
    payload["changed_files"] = ["worker-results/run-worker-result.json"]
    _upsert_db_worker_result(store, payload=payload)
    _complete_worker_run_with_result(store)

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "worker_result_filesystem_artifact_recorded" for failure in failures
    )


def test_planning_integrity_rejects_worker_results_artifacts_in_db_records(tmp_path):
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
    payload = json.loads(json_worker_result())
    payload["artifacts"] = ["worker-results/run-worker-result.json"]
    _upsert_db_worker_result(store, payload=payload)
    _complete_worker_run_with_result(store)

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "worker_result_filesystem_artifact_recorded" for failure in failures
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


def test_planning_integrity_allows_worker_result_artifacts_to_omit_result_path(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Validate worker result supporting artifacts.",
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
    payload = json.loads(json_worker_result())
    payload["changed_files"] = ["src/worker.py"]
    payload["artifacts"] = ["src/worker.py"]
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

    assert not any("artifacts must include result_path" in failure.reason for failure in failures)


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


def test_planning_integrity_rejects_open_codex_exec_controller_owned_paths(tmp_path):
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
    store.upsert_plan_milestone(
        PlanMilestoneRecord(
            milestone_id="milestone-ready",
            plan_id="plan-ready",
            title="Milestone",
            status="pending",
        )
    )
    store.upsert_plan_acceptance_criterion(
        PlanAcceptanceCriterionRecord(
            criterion_id="criterion-ready",
            plan_id="plan-ready",
            description="done",
            status="pending",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-ready",
            plan_id="plan-ready",
            title="Ready task",
            goal="Looks ready but owns controller state.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["plans/planning.sqlite3"],
            worker_backend="live_codex_exec",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "open_codex_exec_task_allows_controller_owned_path"
        and "plans/planning.sqlite3" in failure.reason
        for failure in failures
    )


def test_planning_integrity_rejects_controller_owned_paths_despite_broad_flag(tmp_path):
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
    store.upsert_plan_milestone(
        PlanMilestoneRecord(
            milestone_id="milestone-ready",
            plan_id="plan-ready",
            title="Milestone",
            status="pending",
        )
    )
    store.upsert_plan_acceptance_criterion(
        PlanAcceptanceCriterionRecord(
            criterion_id="criterion-ready",
            plan_id="plan-ready",
            description="done",
            status="pending",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-ready",
            plan_id="plan-ready",
            title="Ready task",
            goal="Broad flag cannot make a product worker controller-owned.",
            task_type="AFK",
            status="ready",
            scope={"controller_owned_paths_allowed": True},
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["plans/planning.sqlite3"],
            worker_backend="live_codex_exec",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "open_codex_exec_task_allows_controller_owned_path"
        and "plans/planning.sqlite3" in failure.reason
        for failure in failures
    )


def test_planning_integrity_rejects_legacy_controller_role_without_typed_kind(tmp_path):
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
            goal="Legacy labels cannot authorize controller mutation.",
            task_type="AFK",
            status="ready",
            scope={"controller_task": True, "task_role": "controller"},
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["plans/planning.sqlite3"],
            worker_backend="live_codex_exec",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "open_codex_exec_task_allows_controller_owned_path"
        and "legacy controller role" in failure.reason
        for failure in failures
    )


def test_planning_integrity_rejects_worker_must_not_edit_overlap(tmp_path):
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
    store.upsert_plan_milestone(
        PlanMilestoneRecord(
            milestone_id="milestone-ready",
            plan_id="plan-ready",
            title="Milestone",
            status="pending",
        )
    )
    store.upsert_plan_acceptance_criterion(
        PlanAcceptanceCriterionRecord(
            criterion_id="criterion-ready",
            plan_id="plan-ready",
            description="done",
            status="pending",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-ready",
            plan_id="plan-ready",
            title="Ready task",
            goal="Contradictory paths cannot launch.",
            task_type="AFK",
            status="ready",
            scope={"worker_must_not_edit": ["src/**"]},
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
            worker_backend="live_codex_exec",
        )
    )

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "open_codex_exec_task_allows_controller_owned_path"
        and "worker_must_not_edit" in failure.reason
        for failure in failures
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


def test_planning_integrity_requires_browser_smoke_for_marked_completed_task(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker Plan",
            goal="Require UI evidence.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Worker",
            goal="Build a UI.",
            task_type="AFK",
            status="completed",
            scope={"browser_smoke_required": True},
            acceptance_criteria=["criterion"],
            verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**", "runs/run-worker/result.json"],
        )
    )
    result_path = tmp_path / "runs" / "run-worker" / "result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(json_worker_result(), encoding="utf-8")
    result_id = _upsert_db_worker_result(store)
    _complete_worker_run_with_result(store, result_id=result_id)

    failures = module.check_planning_integrity(db_path)

    assert any(
        failure.check_name == "completed_worker_run_missing_browser_smoke" for failure in failures
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


def test_planning_integrity_rejects_stale_review_handoff_after_completed_queue(tmp_path):
    module = _load_planning_integrity_module()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-done",
            slug="done",
            title="Done Plan",
            goal="Keep handoff aligned.",
            status="completed",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-done",
            plan_id="plan-done",
            title="Done",
            goal="Done.",
            task_type="HITL",
            status="completed",
        )
    )
    (tmp_path / "HANDOFF.md").write_text(
        "# Handoff\n\nThe work is review pending before completion.\n",
        encoding="utf-8",
    )

    failures = module.check_planning_integrity(db_path)

    assert any(failure.check_name == "handoff_snapshot_stale_review_state" for failure in failures)


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


def _upsert_db_worker_result(
    store,
    *,
    payload: dict[str, object] | None = None,
    result_id: str = "worker-result-run-worker",
    status: str = "completed",
) -> str:
    payload = dict(payload or json.loads(json_worker_result()))
    summary = payload.get("summary")
    tests_run = payload.get("tests_run")
    acceptance_results = payload.get("acceptance_results")
    changed_files = payload.get("changed_files")
    artifacts = payload.get("artifacts")
    risks = payload.get("risks")
    follow_up_tasks = payload.get("follow_up_tasks")
    notes = payload.get("completion_notes", payload.get("handoff_notes"))
    store.upsert_worker_result_record(
        WorkerResultRecord(
            result_id=result_id,
            status=status,
            summary=summary if isinstance(summary, str) and summary.strip() else "Recorded.",
            raw_payload=payload,
            tests_run=tests_run if isinstance(tests_run, list) else [],
            acceptance_results=acceptance_results if isinstance(acceptance_results, dict) else {},
            changed_files=changed_files if _is_string_list(changed_files) else [],
            artifacts=artifacts if _is_string_list(artifacts) else [],
            risks=risks if isinstance(risks, list) else [],
            follow_up_tasks=follow_up_tasks if isinstance(follow_up_tasks, list) else [],
            completion_notes=notes if isinstance(notes, str) else None,
            source_kind="test",
        )
    )
    return result_id


def _complete_worker_run_with_result(
    store,
    *,
    worker_run_id: str = "run-worker",
    task_id: str = "task-worker",
    result_id: str = "worker-result-run-worker",
) -> None:
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id=worker_run_id,
            task_id=task_id,
            backend="subagent_explorer",
            status="completed",
            result_id=result_id,
        )
    )


def _is_string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _load_planning_integrity_module() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "check_planning_integrity.py"
    spec = importlib.util.spec_from_file_location("check_planning_integrity", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
