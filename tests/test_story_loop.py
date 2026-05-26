from __future__ import annotations

import json

from codex_supervisor.cli import main
from codex_supervisor.planning import (
    PlanAcceptanceCriterionRecord,
    PlanRecord,
    SupervisorTaskRecord,
    WorkerRunRecord,
    initialize_planning_database,
    open_existing_planning_database,
)
from codex_supervisor.story_loop import run_live_story_loop_once
from codex_supervisor.worker_backends import CommandExecutionResult


def test_story_loop_status_reports_empty_blocked_ready_and_completed_states(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-empty",
            slug="empty",
            title="Empty",
            goal="No work yet.",
            status="active",
            priority=1,
        )
    )
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-blocked",
            slug="blocked",
            title="Blocked",
            goal="Blocked work.",
            status="blocked",
            priority=2,
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-blocked",
            plan_id="plan-blocked",
            title="Blocked task",
            goal="Wait for dependency.",
            task_type="AFK",
            status="blocked",
            blocked_by=["task-parent"],
        )
    )
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-completed",
            slug="completed",
            title="Completed",
            goal="Done work.",
            status="active",
            priority=3,
        )
    )
    store.upsert_plan_acceptance_criterion(
        PlanAcceptanceCriterionRecord(
            criterion_id="criterion-completed",
            plan_id="plan-completed",
            description="Done.",
            status="completed",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-completed",
            plan_id="plan-completed",
            title="Completed task",
            goal="Already done.",
            task_type="AFK",
            status="completed",
        )
    )
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-hitl",
            slug="hitl",
            title="HITL",
            goal="Needs human.",
            status="active",
            priority=4,
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-hitl",
            plan_id="plan-hitl",
            title="Human task",
            goal="Ask for input.",
            task_type="HITL",
            status="ready",
        )
    )
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-ready",
            slug="ready",
            title="Ready",
            goal="Ready work.",
            status="active",
            priority=100,
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-ready",
            plan_id="plan-ready",
            title="Ready task",
            goal="Do this now.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )

    assert main(["story-loop-status", "--path", str(db_path), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    states = {plan["plan_id"]: plan["state"] for plan in payload["plans"]}
    assert payload["queue_state"] == "ready"
    assert payload["current_task_id"] == "task-ready"
    assert payload["current_hitl_task_id"] is None
    assert payload["current_afk_task"]["task_id"] == "task-ready"
    assert payload["current_task"]["task_id"] == "task-ready"
    assert states == {
        "plan-ready": "ready",
        "plan-hitl": "hitl",
        "plan-completed": "completed",
        "plan-blocked": "blocked",
        "plan-empty": "empty",
    }
    blocked_plan = next(plan for plan in payload["plans"] if plan["plan_id"] == "plan-blocked")
    assert blocked_plan["blocked_task_ids"] == ["task-blocked"]
    hitl_plan = next(plan for plan in payload["plans"] if plan["plan_id"] == "plan-hitl")
    assert hitl_plan["hitl_task_ids"] == ["task-hitl"]


def test_story_loop_status_blocks_failed_tasks_until_reconciled(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-failed",
            slug="failed",
            title="Failed",
            goal="A failed terminal task still needs reconciliation.",
            status="active",
            priority=100,
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-failed",
            plan_id="plan-failed",
            title="Failed task",
            goal="This failed and needs an explicit outcome.",
            task_type="AFK",
            status="failed",
        )
    )

    assert main(["story-loop-status", "--path", str(db_path), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["queue_state"] == "blocked"
    assert payload["current_task_id"] is None
    assert payload["plans"][0]["state"] == "blocked"
    assert payload["plans"][0]["summary"] == "Failed task requires reconciliation: task-failed"
    assert payload["plans"][0]["blocked_task_ids"] == ["task-failed"]
    assert payload["plans"][0]["open_task_ids"] == []


def test_story_loop_default_reports_blocked_successor_plan(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-successor",
            slug="successor",
            title="Blocked Successor",
            goal="Future implementation after checkpoint.",
            status="blocked",
            priority=90,
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-successor",
            plan_id="plan-successor",
            title="Blocked successor task",
            goal="Wait for checkpoint approval.",
            task_type="AFK",
            status="blocked",
            acceptance_criteria=["checkpoint approved"],
            verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )

    assert main(["story-loop-status", "--path", str(db_path), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["queue_state"] == "blocked"
    assert payload["plans"][0]["plan_id"] == "plan-successor"
    assert payload["plans"][0]["blocked_task_ids"] == ["task-successor"]


def test_story_loop_status_reports_top_level_hitl_state(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-hitl",
            slug="hitl",
            title="HITL",
            goal="Needs human.",
            status="active",
            priority=4,
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-hitl",
            plan_id="plan-hitl",
            title="Human task",
            goal="Ask for input.",
            task_type="HITL",
            status="ready",
        )
    )

    assert main(["story-loop-status", "--path", str(db_path), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["queue_state"] == "hitl"
    assert payload["current_task"]["task_id"] == "task-hitl"
    assert payload["current_afk_task"] is None
    assert payload["current_task_id"] == "task-hitl"
    assert payload["current_hitl_task_id"] == "task-hitl"


def test_story_loop_plan_id_selection_uses_full_afk_contract(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-underspecified",
            slug="underspecified",
            title="Underspecified",
            goal="Do not select unsafe work.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-underspecified",
            plan_id="plan-underspecified",
            title="Missing contract",
            goal="Looks ready but lacks verification and allowed paths.",
            task_type="AFK",
            status="ready",
        )
    )

    assert (
        main(
            [
                "story-loop-status",
                "--path",
                str(db_path),
                "--plan-id",
                "plan-underspecified",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["queue_state"] == "blocked"
    assert payload["current_afk_task"] is None
    assert payload["current_task"] is None
    assert payload["plans"][0]["ready_task_ids"] == []
    assert payload["plans"][0]["blocked_task_ids"] == ["task-underspecified"]


def test_story_loop_excludes_ready_task_with_active_worker_run(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker",
            goal="Avoid double-claiming ready work.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Ready but claimed",
            goal="Already has a worker.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
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

    assert main(["story-loop-status", "--path", str(db_path), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["queue_state"] == "running"
    assert payload["current_running_task_id"] == "task-worker"
    assert payload["current_task"]["task_id"] == "task-worker"
    assert payload["current_afk_task"] is None
    assert payload["plans"][0]["ready_task_ids"] == []
    assert payload["plans"][0]["running_task_ids"] == ["task-worker"]
    assert payload["plans"][0]["blocked_task_ids"] == []


def test_story_loop_allows_ready_rework_after_completed_worker_run(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-rework",
            slug="rework",
            title="Rework",
            goal="Allow review-requested rework after completed worker evidence.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-rework",
            plan_id="plan-rework",
            title="Ready rework",
            goal="Fix review findings.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["review findings fixed"],
            verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-rework-previous",
            task_id="task-rework",
            backend="codex_exec",
            status="completed",
            result_path="insights/previous-result.json",
        )
    )
    store.update_supervisor_task_status("task-rework", "ready")

    assert main(["story-loop-status", "--path", str(db_path), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["queue_state"] == "ready"
    assert payload["current_task_id"] == "task-rework"
    assert payload["plans"][0]["ready_task_ids"] == ["task-rework"]


def test_story_loop_surfaces_pending_task_ids(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-pending",
            slug="pending",
            title="Pending",
            goal="Expose pending non-ready work.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-pending",
            plan_id="plan-pending",
            title="Pending task",
            goal="Wait for shaping.",
            task_type="AFK",
            status="pending",
        )
    )

    assert main(["story-loop-status", "--path", str(db_path), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["queue_state"] == "blocked"
    assert payload["plans"][0]["pending_task_ids"] == ["task-pending"]
    assert "Pending task" in payload["plans"][0]["summary"]
    assert payload["current_afk_task"] is None
    assert payload["plans"][0]["ready_task_ids"] == []
    assert payload["plans"][0]["blocked_task_ids"] == []


def test_story_loop_reports_reviewing_worker_as_hitl(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-review",
            slug="review",
            title="Review",
            goal="Surface review as a human checkpoint.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-review",
            plan_id="plan-review",
            title="Ready for review",
            goal="Needs review.",
            task_type="AFK",
            status="reviewing",
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-review",
            task_id="task-review",
            backend="codex_exec",
            status="needs_review",
        )
    )

    assert main(["story-loop-status", "--path", str(db_path), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["queue_state"] == "hitl"
    assert payload["current_task_id"] == "task-review"
    assert payload["current_task"]["task_id"] == "task-review"
    assert payload["current_afk_task"] is None
    assert payload["plans"][0]["hitl_task_ids"] == ["task-review"]
    assert payload["plans"][0]["running_task_ids"] == []


def test_story_loop_reports_completed_review_required_worker_as_hitl(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker",
            slug="worker",
            title="Worker",
            goal="Avoid rerunning completed evidence.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker",
            title="Ready but completed",
            goal="Already has completed worker evidence.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="codex_exec",
            status="completed",
            result_path="runs/run-worker/result.json",
        )
    )

    assert main(["story-loop-status", "--path", str(db_path), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["queue_state"] == "hitl"
    assert payload["current_task_id"] == "task-worker"
    assert payload["current_task"]["status"] == "reviewing"
    assert payload["current_afk_task"] is None
    assert payload["plans"][0]["ready_task_ids"] == []
    assert payload["plans"][0]["hitl_task_ids"] == ["task-worker"]


def test_story_loop_plan_id_reports_inactive_or_missing_plan(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-completed",
            slug="completed",
            title="Completed",
            goal="Already done.",
            status="completed",
        )
    )
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-blocked",
            slug="blocked",
            title="Blocked",
            goal="Current queue but blocked.",
            status="blocked",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-blocked",
            plan_id="plan-blocked",
            title="Blocked task",
            goal="Wait.",
            task_type="AFK",
            status="blocked",
            acceptance_criteria=["unblocked"],
            verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )

    assert (
        main(
            [
                "story-loop-status",
                "--path",
                str(db_path),
                "--plan-id",
                "plan-completed",
                "--json",
            ]
        )
        == 1
    )
    assert "rerun with --all" in capsys.readouterr().err

    assert (
        main(
            [
                "story-loop-status",
                "--path",
                str(db_path),
                "--plan-id",
                "plan-blocked",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["plans"][0]["plan_id"] == "plan-blocked"
    assert payload["queue_state"] == "blocked"

    assert (
        main(
            [
                "story-loop-status",
                "--path",
                str(db_path),
                "--plan-id",
                "plan-missing",
                "--json",
            ]
        )
        == 1
    )
    assert "No plan found: plan-missing" in capsys.readouterr().err

    assert (
        main(
            [
                "story-loop-status",
                "--path",
                str(db_path),
                "--plan-id",
                "plan-completed",
                "--all",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["plans"][0]["plan_id"] == "plan-completed"


def test_story_loop_record_writes_progress_and_artifact_links(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-story",
            slug="story",
            title="Story",
            goal="Record loop progress.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-story",
            plan_id="plan-story",
            title="Story task",
            goal="Record loop progress for a real task.",
            task_type="AFK",
            status="running",
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-story",
            task_id="task-story",
            backend="codex_exec",
            status="running",
        )
    )

    assert (
        main(
            [
                "story-loop-record",
                "--path",
                str(db_path),
                "--progress-id",
                "progress-story",
                "--plan-id",
                "plan-story",
                "--summary",
                "Recorded a story iteration.",
                "--details",
                "Verification passed.",
                "--task-id",
                "task-story",
                "--worker-run-id",
                "run-story",
                "--artifact-id",
                "src/example.py",
                "--artifact-id",
                "tests/test_example.py",
                "--artifact-relationship",
                "iteration-evidence",
                "--linked-artifact-id",
                "reports/story.md",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["progress"]["linked_artifact_id"] == "reports/story.md"
    assert "task_id=task-story" in payload["progress"]["details"]
    assert "worker_run_id=run-story" in payload["progress"]["details"]
    assert [link["artifact_id"] for link in payload["artifact_links"]] == [
        "src/example.py",
        "tests/test_example.py",
        "reports/story.md",
    ]

    read_store = open_existing_planning_database(db_path)
    progress = read_store.list_plan_progress(plan_id="plan-story")
    artifact_links = read_store.list_plan_artifact_links(plan_id="plan-story")
    assert progress[0].progress_id == "progress-story"
    assert {link.artifact_id for link in artifact_links} == {
        "reports/story.md",
        "src/example.py",
        "tests/test_example.py",
    }
    assert {link.relationship for link in artifact_links} == {
        "iteration-evidence",
        "progress-linked-artifact",
    }


def test_story_loop_record_rejects_cross_plan_task_reference(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-a",
            slug="a",
            title="A",
            goal="Record progress.",
            status="active",
        )
    )
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-b",
            slug="b",
            title="B",
            goal="Own a different task.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-b",
            plan_id="plan-b",
            title="Task B",
            goal="Belongs elsewhere.",
            task_type="AFK",
            status="running",
        )
    )

    assert (
        main(
            [
                "story-loop-record",
                "--path",
                str(db_path),
                "--progress-id",
                "progress-story",
                "--plan-id",
                "plan-a",
                "--summary",
                "Invalid task link.",
                "--task-id",
                "task-b",
            ]
        )
        == 1
    )
    assert "belongs to plan-b, not plan-a" in capsys.readouterr().err


def test_live_story_loop_run_claims_worktree_launches_and_ingests_result(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = _live_story_loop_store(db_path)
    calls: list[tuple[str, ...]] = []

    def codex_runner(argv, cwd, environment):
        calls.append(argv)
        if argv == ("C:/Tools/codex.exe", "--version"):
            return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")
        _write_live_worker_result(tmp_path, worker_run_id="run-live")
        return CommandExecutionResult(exit_code=0, stdout='{"event":"done"}\n')

    git_calls: list[tuple[str, ...]] = []

    def git_runner(argv, cwd, environment):
        git_calls.append(argv)
        assert environment == {"GIT_OPTIONAL_LOCKS": "0"}
        if argv == ("git", "rev-parse", "HEAD") and cwd == tmp_path:
            return CommandExecutionResult(exit_code=0, stdout="base-sha\n")
        if argv == (
            "git",
            "worktree",
            "add",
            "--detach",
            str(tmp_path / "worktrees" / "run-live"),
            "base-sha",
        ):
            return CommandExecutionResult(exit_code=0, stdout="")
        if argv == ("git", "rev-parse", "--abbrev-ref", "HEAD"):
            return CommandExecutionResult(exit_code=0, stdout="HEAD\n")
        if argv == ("git", "rev-parse", "base-sha"):
            return CommandExecutionResult(exit_code=0, stdout="base-sha\n")
        if argv == ("git", "rev-parse", "HEAD"):
            return CommandExecutionResult(exit_code=0, stdout="head-sha\n")
        if argv == ("git", "status", "--porcelain=v1"):
            return CommandExecutionResult(exit_code=0, stdout=" M src/live_story.py\n")
        if argv == ("git", "diff", "--name-only", "base-sha...head-sha"):
            return CommandExecutionResult(exit_code=0, stdout="")
        raise AssertionError(f"unexpected git argv: {argv}")

    result = run_live_story_loop_once(
        store,
        repo_root=tmp_path,
        worker_run_id="run-live",
        codex_executable="C:/Tools/codex.exe",
        command_runner=codex_runner,
        git_command_runner=git_runner,
    )

    assert result.status == "completed"
    assert result.task_id == "task-live"
    assert result.result_id is not None
    assert result.result_path == "artifacts/run-live/worker-result.raw.json"
    assert result.worktree_path == "worktrees/run-live"
    assert result.changed_files == ("src/live_story.py",)
    assert result.changed_files_source == "git_worktree"
    assert result.worktree_created is True
    assert calls[0] == ("C:/Tools/codex.exe", "--version")
    assert calls[1][1:4] == ("exec", "--json", "--output-schema")
    assert calls[1][-1] == "-"
    assert (
        "git",
        "worktree",
        "add",
        "--detach",
        str(tmp_path / "worktrees" / "run-live"),
        "base-sha",
    ) in tuple(git_calls)

    read_store = open_existing_planning_database(db_path)
    worker = next(run for run in read_store.list_worker_runs() if run.worker_run_id == "run-live")
    assert worker.status == "completed"
    assert worker.result_id == result.result_id
    assert worker.result_path is None
    task = next(task for task in read_store.list_supervisor_tasks() if task.task_id == "task-live")
    assert task.status == "completed"


def test_live_story_loop_run_fails_claimed_run_when_worktree_creation_fails(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = _live_story_loop_store(db_path)
    codex_calls: list[tuple[str, ...]] = []

    def codex_runner(argv, cwd, environment):
        codex_calls.append(argv)
        return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")

    def git_runner(argv, cwd, environment):
        if argv == ("git", "rev-parse", "HEAD"):
            return CommandExecutionResult(exit_code=0, stdout="base-sha\n")
        if argv[:4] == ("git", "worktree", "add", "--detach"):
            return CommandExecutionResult(exit_code=1, stderr="cannot create worktree\n")
        raise AssertionError(f"unexpected git argv: {argv}")

    result = run_live_story_loop_once(
        store,
        repo_root=tmp_path,
        worker_run_id="run-live",
        codex_executable="C:/Tools/codex.exe",
        command_runner=codex_runner,
        git_command_runner=git_runner,
    )

    assert result.status == "failed"
    assert result.failure_class == "worktree_create_failed"
    assert result.worktree_created is False
    assert codex_calls == []

    read_store = open_existing_planning_database(db_path)
    worker = next(run for run in read_store.list_worker_runs() if run.worker_run_id == "run-live")
    assert worker.status == "failed"
    assert worker.failure_class == "worktree_create_failed"


def _live_story_loop_store(db_path):
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-live",
            slug="live",
            title="Live",
            goal="Run a live worker.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-live",
            plan_id="plan-live",
            title="Live task",
            goal="Exercise live Story Loop worker execution.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
            worker_backend="codex_exec",
            review_required=False,
        ),
        validate_current_queue_contract=True,
    )
    return store


def _write_live_worker_result(repo_root, *, worker_run_id):
    changed_file = repo_root / "src" / "live_story.py"
    changed_file.parent.mkdir(parents=True, exist_ok=True)
    changed_file.write_text("print('ok')\n", encoding="utf-8")
    result_path = f"artifacts/{worker_run_id}/worker-result.raw.json"
    result_file = repo_root / result_path
    result_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "worker_run_id": worker_run_id,
        "status": "completed",
        "summary": "Live Story Loop worker completed.",
        "changed_files": ["src/live_story.py"],
        "tests_run": [
            {
                "command": "python -B -m pytest -p no:cacheprovider",
                "exit_code": 0,
                "summary": "passed",
            }
        ],
        "acceptance_results": {
            "done": {
                "status": "passed",
                "evidence": "Live Story Loop test wrote and ingested the result.",
            }
        },
        "risks": [],
        "follow_up_tasks": [],
        "artifacts": [result_path],
        "completion_notes": "Ready.",
    }
    result_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
