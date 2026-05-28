from __future__ import annotations

import json
from types import SimpleNamespace

from codex_supervisor.cli import main
from codex_supervisor.planning import (
    PlanAcceptanceCriterionRecord,
    PlanRecord,
    SupervisorTaskRecord,
    WorkerRunEventRecord,
    WorkerRunRecord,
    initialize_planning_database,
    open_existing_planning_database,
)
from codex_supervisor.story_loop import (
    WORKER_CONTRACT_GIT_PATHS,
    advance_story_loop_once,
    build_story_loop_status,
    poll_story_loop_run_async,
    run_live_story_loop_once,
)
from codex_supervisor.worker_backends import CommandExecutionResult, WorkerLaunchResult


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


def test_story_loop_cli_accepts_codex_executable_aliases(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    initialize_planning_database(db_path)
    captured_run: dict[str, object] = {}
    captured_advance: dict[str, object] = {}

    def fake_run_live_story_loop_once(store, **kwargs):
        captured_run["store_path"] = store.path
        captured_run.update(kwargs)
        return SimpleNamespace(
            status="completed",
            task_id="task-live",
            worker_run_id=kwargs["worker_run_id"],
            failure_class=None,
            result_id=None,
        )

    def fake_advance_story_loop_once(store, **kwargs):
        captured_advance["store_path"] = store.path
        captured_advance.update(kwargs)
        return SimpleNamespace(
            transition="run_live_worker",
            state_before="ready",
            state_after="completed",
            task_id="task-live",
            failure_class=None,
        )

    monkeypatch.setattr(
        "codex_supervisor.cli.run_live_story_loop_once",
        fake_run_live_story_loop_once,
    )
    monkeypatch.setattr(
        "codex_supervisor.cli.advance_story_loop_once",
        fake_advance_story_loop_once,
    )

    assert (
        main(
            [
                "story-loop-run-once",
                "--path",
                str(db_path),
                "--worker-run-id",
                "run-live",
                "--codex-executable",
                "preferred-codex",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "story-loop-advance",
                "--path",
                str(db_path),
                "--worker-run-id",
                "run-live",
                "--codex-bin",
                "legacy-codex",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert captured_run["codex_executable"] == "preferred-codex"
    assert captured_advance["codex_executable"] == "legacy-codex"


def test_story_loop_cli_start_and_poll_route_to_async_controller(
    tmp_path,
    monkeypatch,
    capsys,
):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    initialize_planning_database(db_path)
    captured_start: dict[str, object] = {}
    captured_poll: dict[str, object] = {}

    def fake_start_story_loop_run_async(**kwargs):
        captured_start.update(kwargs)
        return SimpleNamespace(
            status="started",
            worker_run_id=kwargs["worker_run_id"],
            controller_pid=123,
            poll_tool="codex_supervisor.story_loop_poll",
            liveness_probe_path="runs/run-async/liveness.json",
        )

    def fake_poll_story_loop_run_async(**kwargs):
        captured_poll.update(kwargs)
        return SimpleNamespace(
            status="running",
            worker_run_id=kwargs["worker_run_id"],
            done=False,
            worker_run_status="running",
            controller_running=True,
        )

    monkeypatch.setattr(
        "codex_supervisor.cli.start_story_loop_run_async",
        fake_start_story_loop_run_async,
    )
    monkeypatch.setattr(
        "codex_supervisor.cli.poll_story_loop_run_async",
        fake_poll_story_loop_run_async,
    )

    assert (
        main(
            [
                "story-loop-start",
                "--path",
                str(db_path),
                "--repo-root",
                str(tmp_path),
                "--worker-run-id",
                "run-async",
                "--codex-bin",
                "codex",
                "--environment-json",
                '{"CODEX_SUPERVISOR_TEST":"1"}',
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "story-loop-poll",
                "--path",
                str(db_path),
                "--repo-root",
                str(tmp_path),
                "--worker-run-id",
                "run-async",
                "--controller-pid",
                "123",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert captured_start["planning_path"] == db_path
    assert captured_start["repo_root"] == tmp_path
    assert captured_start["worker_run_id"] == "run-async"
    assert captured_start["codex_executable"] == "codex"
    assert captured_start["environment"] == {"CODEX_SUPERVISOR_TEST": "1"}
    assert captured_poll["controller_pid"] == 123


def test_story_loop_async_poll_reports_liveness_probe_and_latest_events(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-async",
            slug="async",
            title="Async",
            goal="Poll a running controller.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-async",
            plan_id="plan-async",
            title="Async task",
            goal="Run async.",
            task_type="AFK",
            status="running",
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-async",
            task_id="task-async",
            backend="codex_exec",
            status="running",
            metadata={"raw_evidence_paths": {"liveness_probe": "runs/run-async/liveness.json"}},
        )
    )
    store.add_worker_run_event(
        WorkerRunEventRecord(
            event_id="run-async-event",
            worker_run_id="run-async",
            event_type="codex_exec_liveness_probe",
            summary="Worker process is still alive.",
        )
    )
    (tmp_path / "runs" / "run-async").mkdir(parents=True)
    (tmp_path / "runs" / "run-async" / "liveness.json").write_text(
        json.dumps({"stage": "exec_started", "pid": 456}) + "\n",
        encoding="utf-8",
    )

    result = poll_story_loop_run_async(
        planning_path=db_path,
        repo_root=tmp_path,
        worker_run_id="run-async",
        controller_pid=456,
        process_probe=lambda pid: pid == 456,
    )

    assert result.status == "running"
    assert result.done is False
    assert result.controller_running is True
    assert result.liveness_probe == {"stage": "exec_started", "pid": 456}
    assert result.latest_events[0]["event_type"] == "codex_exec_liveness_probe"


def test_story_loop_async_poll_can_finalize_orphaned_running_worker(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-async",
            slug="async",
            title="Async",
            goal="Poll a running controller.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-async",
            plan_id="plan-async",
            title="Async task",
            goal="Run async.",
            task_type="AFK",
            status="running",
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-async",
            task_id="task-async",
            backend="codex_exec",
            status="running",
        )
    )
    (tmp_path / "runs" / "run-async").mkdir(parents=True)

    observed = poll_story_loop_run_async(
        planning_path=db_path,
        repo_root=tmp_path,
        worker_run_id="run-async",
        controller_pid=456,
        process_probe=lambda pid: False,
    )
    finalized = poll_story_loop_run_async(
        planning_path=db_path,
        repo_root=tmp_path,
        worker_run_id="run-async",
        controller_pid=456,
        finalize_orphaned=True,
        process_probe=lambda pid: False,
    )

    assert observed.status == "orphaned_running"
    assert observed.done is False
    assert finalized.status == "failed"
    assert finalized.done is True
    assert finalized.failure_class == "story_loop_controller_exited"
    assert finalized.latest_events[-1]["event_type"] == "story_loop_controller_exited"


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
        _write_live_worker_result(tmp_path, worker_run_id="run-live", browser_smoke=True)
        return CommandExecutionResult(exit_code=0, stdout='{"event":"done"}\n')

    git_calls: list[tuple[str, ...]] = []

    def git_runner(argv, cwd, environment):
        git_calls.append(argv)
        assert environment == {"GIT_OPTIONAL_LOCKS": "0"}
        if argv == ("git", "status", "--porcelain=v1", "--", *WORKER_CONTRACT_GIT_PATHS):
            return CommandExecutionResult(exit_code=0, stdout="")
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
    events = read_store.list_worker_run_events(worker_run_id="run-live")
    assert events[0].event_type == "codex_exec_launch_result"
    assert events[0].details["changed_files"] == ["src/live_story.py"]
    progress = read_store.list_plan_progress(plan_id="plan-live")
    assert any(event.event_type == "browser_smoke_passed" for event in progress)
    artifact_links = read_store.list_plan_artifact_links(plan_id="plan-live")
    assert {(link.artifact_id, link.relationship) for link in artifact_links} == {
        ("artifacts/run-live/evidence-manifest.json", "worker-evidence-manifest"),
        ("artifacts/run-live/worker-result.raw.json", "worker-result"),
        ("artifacts/run-live/worker-result.normalized.json", "worker-result-normalized"),
    }
    task = next(task for task in read_store.list_supervisor_tasks() if task.task_id == "task-live")
    assert task.status == "completed"


def test_live_story_loop_creates_separate_review_task_when_review_required(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = _live_story_loop_store(db_path, review_required=True)

    def codex_runner(argv, cwd, environment):
        if argv == ("C:/Tools/codex.exe", "--version"):
            return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")
        _write_live_worker_result(tmp_path, worker_run_id="run-review")
        return CommandExecutionResult(exit_code=0, stdout='{"event":"done"}\n')

    def git_runner(argv, cwd, environment):
        if argv == ("git", "status", "--porcelain=v1", "--", *WORKER_CONTRACT_GIT_PATHS):
            return CommandExecutionResult(exit_code=0, stdout="")
        if argv == ("git", "rev-parse", "HEAD") and cwd == tmp_path:
            return CommandExecutionResult(exit_code=0, stdout="base-sha\n")
        if argv == (
            "git",
            "worktree",
            "add",
            "--detach",
            str(tmp_path / "worktrees" / "run-review"),
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
        worker_run_id="run-review",
        codex_executable="C:/Tools/codex.exe",
        command_runner=codex_runner,
        git_command_runner=git_runner,
    )

    assert result.status == "completed"
    read_store = open_existing_planning_database(db_path)
    tasks = read_store.list_supervisor_tasks()
    source = next(task for task in tasks if task.task_id == "task-live")
    review = next(task for task in tasks if task.task_id == "task-review-task-live-run-review")
    assert source.status == "reviewing"
    assert review.task_type == "AFK"
    assert review.status == "ready"
    assert review.worker_backend == "codex_review"
    assert review.review_required is False
    assert review.scope["source_task_id"] == "task-live"
    assert review.scope["worker_run_id"] == "run-review"
    status = build_story_loop_status(read_store)
    assert status.queue_state == "ready"
    assert status.current_task_id == review.task_id


def test_live_story_loop_refuses_completion_when_evidence_paths_are_missing(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = _live_story_loop_store(db_path)

    class MissingEvidenceBackend:
        def run(self, request):
            _write_live_worker_result(tmp_path, worker_run_id="run-missing-evidence")
            return WorkerLaunchResult(
                worker_run_id=request.worker_run_id,
                task_id=request.task_id,
                status="completed",
                result_path=request.result_path,
                exit_code=0,
                changed_files=("src/live_story.py",),
                prompt_path=request.prompt_path,
                jsonl_path=request.jsonl_path,
                stdout_path=request.stdout_path,
                stderr_path=request.stderr_path,
                final_message_path=request.final_message_path,
                diff_summary_path=request.diff_summary_path,
                metadata={"evidence_manifest_path": request.evidence_manifest_path},
            )

    def git_runner(argv, cwd, environment):
        if argv == ("git", "status", "--porcelain=v1", "--", *WORKER_CONTRACT_GIT_PATHS):
            return CommandExecutionResult(exit_code=0, stdout="")
        if argv == ("git", "rev-parse", "HEAD") and cwd == tmp_path:
            return CommandExecutionResult(exit_code=0, stdout="base-sha\n")
        if argv == (
            "git",
            "worktree",
            "add",
            "--detach",
            str(tmp_path / "worktrees" / "run-missing-evidence"),
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
        worker_run_id="run-missing-evidence",
        backend=MissingEvidenceBackend(),
        git_command_runner=git_runner,
    )

    assert result.status == "failed"
    assert result.failure_class == "worker_evidence_missing"
    read_store = open_existing_planning_database(db_path)
    worker = next(
        run for run in read_store.list_worker_runs() if run.worker_run_id == "run-missing-evidence"
    )
    assert worker.status == "failed"
    assert worker.failure_class == "worker_evidence_missing"
    event = next(
        event
        for event in read_store.list_worker_run_events(worker_run_id="run-missing-evidence")
        if event.event_type == "worker_evidence_missing"
    )
    assert "runs/run-missing-evidence/stdout.txt" in event.details["missing_evidence_paths"]


def test_story_loop_advance_runs_one_ready_transition(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = _live_story_loop_store(db_path)

    def codex_runner(argv, cwd, environment):
        if argv == ("C:/Tools/codex.exe", "--version"):
            return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")
        _write_live_worker_result(tmp_path, worker_run_id="run-advance")
        return CommandExecutionResult(exit_code=0, stdout='{"event":"done"}\n')

    def git_runner(argv, cwd, environment):
        if argv == ("git", "status", "--porcelain=v1", "--", *WORKER_CONTRACT_GIT_PATHS):
            return CommandExecutionResult(exit_code=0, stdout="")
        if argv == ("git", "rev-parse", "HEAD") and cwd == tmp_path:
            return CommandExecutionResult(exit_code=0, stdout="base-sha\n")
        if argv == (
            "git",
            "worktree",
            "add",
            "--detach",
            str(tmp_path / "worktrees" / "run-advance"),
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

    result = advance_story_loop_once(
        store,
        repo_root=tmp_path,
        worker_run_id="run-advance",
        codex_executable="C:/Tools/codex.exe",
        command_runner=codex_runner,
        git_command_runner=git_runner,
    )

    assert result.transition == "ready_to_worker_result"
    assert result.state_before == "ready"
    assert result.worker_run_id == "run-advance"
    assert result.live_run is not None
    assert result.live_run.status == "completed"


def test_live_story_loop_run_fails_claimed_run_when_worktree_creation_fails(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = _live_story_loop_store(db_path)
    codex_calls: list[tuple[str, ...]] = []

    def codex_runner(argv, cwd, environment):
        codex_calls.append(argv)
        return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")

    def git_runner(argv, cwd, environment):
        if argv == ("git", "status", "--porcelain=v1", "--", *WORKER_CONTRACT_GIT_PATHS):
            return CommandExecutionResult(exit_code=0, stdout="")
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
    events = read_store.list_worker_run_events(worker_run_id="run-live")
    assert events[0].event_type == "worker_launch_failed"


def test_live_story_loop_refuses_uncommitted_worker_contract_before_claim(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = _live_story_loop_store(db_path)
    codex_calls: list[tuple[str, ...]] = []

    def codex_runner(argv, cwd, environment):
        codex_calls.append(argv)
        return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")

    def git_runner(argv, cwd, environment):
        if argv == ("git", "status", "--porcelain=v1", "--", *WORKER_CONTRACT_GIT_PATHS):
            return CommandExecutionResult(exit_code=0, stdout=" M plans/planning.sqlite3\n")
        raise AssertionError(f"unexpected git argv: {argv}")

    result = run_live_story_loop_once(
        store,
        repo_root=tmp_path,
        worker_run_id="run-dirty-contract",
        codex_executable="C:/Tools/codex.exe",
        command_runner=codex_runner,
        git_command_runner=git_runner,
    )

    assert result.status == "failed"
    assert result.failure_class == "worker_contract_uncommitted"
    assert result.worktree_created is False
    assert codex_calls == []

    read_store = open_existing_planning_database(db_path)
    task = next(task for task in read_store.list_supervisor_tasks() if task.task_id == "task-live")
    worker = next(
        run for run in read_store.list_worker_runs() if run.worker_run_id == "run-dirty-contract"
    )
    assert task.status == "ready"
    assert worker.status == "failed"
    assert worker.metadata["launch_preflight"]["dirty_contract_paths"] == ["plans/planning.sqlite3"]
    events = read_store.list_worker_run_events(worker_run_id="run-dirty-contract")
    assert events[0].event_type == "worker_launch_preflight_failed"


def test_live_story_loop_policy_lint_blocks_codex_exec_controller_owned_paths(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
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
            goal="Try to hand controller state to a product worker.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["plans/planning.sqlite3"],
            worker_backend="codex_exec",
        )
    )
    codex_calls: list[tuple[str, ...]] = []
    git_calls: list[tuple[str, ...]] = []

    def codex_runner(argv, cwd, environment):
        codex_calls.append(argv)
        return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")

    def git_runner(argv, cwd, environment):
        git_calls.append(argv)
        return CommandExecutionResult(exit_code=0, stdout="")

    result = run_live_story_loop_once(
        store,
        repo_root=tmp_path,
        worker_run_id="run-policy",
        codex_executable="C:/Tools/codex.exe",
        command_runner=codex_runner,
        git_command_runner=git_runner,
    )

    assert result.status == "failed"
    assert result.failure_class == "worker_contract_policy_violation"
    assert result.worktree_created is False
    assert codex_calls == []
    assert git_calls == []
    worker = open_existing_planning_database(db_path).list_worker_runs()[0]
    assert worker.metadata["launch_preflight"]["violations"] == [
        "plans/planning.sqlite3: controller-owned path"
    ]


def test_live_story_loop_policy_lint_does_not_trust_broad_controller_owned_flag(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
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
            goal="Try to smuggle controller state into product scope.",
            task_type="AFK",
            status="ready",
            scope={"controller_owned_paths_allowed": True},
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["plans/planning.sqlite3"],
            worker_backend="codex_exec",
        )
    )

    result = run_live_story_loop_once(
        store,
        repo_root=tmp_path,
        worker_run_id="run-policy-flag",
        codex_executable="C:/Tools/codex.exe",
    )

    assert result.status == "failed"
    assert result.failure_class == "worker_contract_policy_violation"
    worker = open_existing_planning_database(db_path).list_worker_runs()[0]
    assert worker.metadata["launch_preflight"]["violations"] == [
        "plans/planning.sqlite3: controller-owned path"
    ]


def test_live_story_loop_policy_lint_requires_typed_controller_mutation_kind(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
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
            goal="Legacy controller labels cannot hand controller state to a worker.",
            task_type="AFK",
            status="ready",
            scope={"controller_task": True, "task_role": "controller"},
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["plans/planning.sqlite3"],
            worker_backend="codex_exec",
        )
    )

    result = run_live_story_loop_once(
        store,
        repo_root=tmp_path,
        worker_run_id="run-policy-legacy-role",
        codex_executable="C:/Tools/codex.exe",
    )

    assert result.status == "failed"
    assert result.failure_class == "worker_contract_policy_violation"
    worker = open_existing_planning_database(db_path).list_worker_runs()[0]
    assert worker.metadata["launch_preflight"]["violations"] == [
        "controller_task: legacy controller role is ignored without controller_mutation_kind",
        "plans/planning.sqlite3: controller-owned path",
    ]


def test_live_story_loop_policy_lint_blocks_worker_must_not_edit_overlap(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
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
            goal="Try contradictory scope.",
            task_type="AFK",
            status="ready",
            scope={"worker_must_not_edit": ["src/**"]},
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
            worker_backend="codex_exec",
        )
    )

    result = run_live_story_loop_once(
        store,
        repo_root=tmp_path,
        worker_run_id="run-policy-overlap",
        codex_executable="C:/Tools/codex.exe",
    )

    assert result.status == "failed"
    assert result.failure_class == "worker_contract_policy_violation"
    worker = open_existing_planning_database(db_path).list_worker_runs()[0]
    assert worker.metadata["launch_preflight"]["violations"] == [
        "src/**: allowed path overlaps worker_must_not_edit `src/**`"
    ]


def test_live_story_loop_preserves_rejected_worker_result_when_changed_paths_fail(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = _live_story_loop_store(db_path)

    class OutOfScopeBackend:
        def run(self, request):
            worktree_file = request.worktree_path / "plans" / "planning.sqlite3"
            worktree_file.parent.mkdir(parents=True, exist_ok=True)
            worktree_file.write_text("worker-local mutation\n", encoding="utf-8")
            result_file = request.repo_root / request.result_path
            result_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "worker_run_id": request.worker_run_id,
                "status": "completed",
                "summary": "Worker changed controller state.",
                "changed_files": ["plans/planning.sqlite3"],
                "tests_run": [
                    {
                        "command": "python -B -m pytest -p no:cacheprovider",
                        "exit_code": 0,
                        "summary": "passed",
                    }
                ],
                "acceptance_results": {
                    "done": {"status": "passed", "evidence": "Worker reported success."}
                },
                "risks": [],
                "follow_up_tasks": [],
                "artifacts": [request.result_path],
                "completion_notes": "Ready.",
            }
            result_file.write_text(json.dumps(payload), encoding="utf-8")
            return WorkerLaunchResult(
                worker_run_id=request.worker_run_id,
                task_id=request.task_id,
                status="completed",
                result_path=request.result_path,
                exit_code=0,
                changed_files=("plans/planning.sqlite3",),
                prompt_path=request.prompt_path,
                jsonl_path=request.jsonl_path,
                stdout_path=request.stdout_path,
                stderr_path=request.stderr_path,
                final_message_path=request.final_message_path,
                diff_summary_path=request.diff_summary_path,
            )

    def git_runner(argv, cwd, environment):
        worktree = tmp_path / "worktrees" / "run-out-of-scope"
        if argv == ("git", "status", "--porcelain=v1", "--", *WORKER_CONTRACT_GIT_PATHS):
            return CommandExecutionResult(exit_code=0, stdout="")
        if argv == ("git", "rev-parse", "HEAD") and cwd == tmp_path:
            return CommandExecutionResult(exit_code=0, stdout="base-sha\n")
        if argv == (
            "git",
            "worktree",
            "add",
            "--detach",
            str(worktree),
            "base-sha",
        ):
            return CommandExecutionResult(exit_code=0, stdout="")
        if cwd == worktree and argv == ("git", "rev-parse", "--abbrev-ref", "HEAD"):
            return CommandExecutionResult(exit_code=0, stdout="HEAD\n")
        if cwd == worktree and argv == ("git", "rev-parse", "base-sha"):
            return CommandExecutionResult(exit_code=0, stdout="base-sha\n")
        if cwd == worktree and argv == ("git", "rev-parse", "HEAD"):
            return CommandExecutionResult(exit_code=0, stdout="head-sha\n")
        if cwd == worktree and argv == ("git", "status", "--porcelain=v1"):
            return CommandExecutionResult(exit_code=0, stdout=" M plans/planning.sqlite3\n")
        if cwd == worktree and argv == ("git", "diff", "--name-only", "base-sha...head-sha"):
            return CommandExecutionResult(exit_code=0, stdout="plans/planning.sqlite3\n")
        raise AssertionError(f"unexpected git argv: {argv}")

    result = run_live_story_loop_once(
        store,
        repo_root=tmp_path,
        worker_run_id="run-out-of-scope",
        backend=OutOfScopeBackend(),
        git_command_runner=git_runner,
    )

    assert result.status == "failed"
    assert result.failure_class == "changed_paths_out_of_scope"
    assert result.result_path == "artifacts/run-out-of-scope/worker-result.raw.json"
    read_store = open_existing_planning_database(db_path)
    rejected = read_store.list_worker_results()[0]
    assert rejected.status == "failed"
    assert rejected.source_kind == "rejected-worker-result-json"
    assert rejected.metadata["failure_class"] == "changed_paths_out_of_scope"
    assert rejected.metadata["rejection"]["changed_path_violations"][0]["path"] == (
        "plans/planning.sqlite3"
    )
    event = read_store.list_worker_run_events(worker_run_id="run-out-of-scope")[-1]
    assert event.event_type == "worker_result_rejected"


def _live_story_loop_store(db_path, *, review_required=False):
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
            scope={} if review_required else {"review_skipped": True},
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
            worker_backend="codex_exec",
            review_required=review_required,
        ),
        validate_current_queue_contract=True,
    )
    return store


def _write_live_worker_result(repo_root, *, worker_run_id, browser_smoke=False):
    changed_file = repo_root / "worktrees" / worker_run_id / "src" / "live_story.py"
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
    if browser_smoke:
        smoke_path = repo_root / "worktrees" / worker_run_id / "artifacts" / "browser" / "smoke.png"
        smoke_path.parent.mkdir(parents=True, exist_ok=True)
        smoke_path.write_bytes(b"png")
        payload["browser_smoke_results"] = [
            {
                "status": "passed",
                "summary": "Browser smoke passed.",
                "tool": "playwright",
                "command": "node scripts/browser-smoke.mjs",
                "exit_code": 0,
                "artifact": "artifacts/browser/smoke.png",
                "url": "http://127.0.0.1:5173",
            }
        ]
    result_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    final_file = repo_root / "runs" / worker_run_id / "final-message.txt"
    final_file.parent.mkdir(parents=True, exist_ok=True)
    final_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    jsonl_file = repo_root / "runs" / worker_run_id / "events.jsonl"
    jsonl_file.parent.mkdir(parents=True, exist_ok=True)
    jsonl_file.write_text(
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "item-test",
                    "type": "command_execution",
                    "command": "python -B -m pytest -p no:cacheprovider",
                    "aggregated_output": "passed\n",
                    "exit_code": 0,
                    "status": "completed",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
