from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

import pytest

import codex_supervisor.planning as planning_module
from codex_supervisor.cli import main
from codex_supervisor.paths import default_planning_database_path, find_repo_root
from codex_supervisor.planning import (
    CURRENT_PLANNING_SCHEMA_VERSION,
    PlanAcceptanceCriterionRecord,
    PlanArtifactLinkRecord,
    PlanCommitLinkRecord,
    PlanDecisionRecord,
    PlanMilestoneRecord,
    PlanProgressRecord,
    PlanRecord,
    SupervisorTaskRecord,
    WorkerRunRecord,
    initialize_planning_database,
    open_existing_planning_database,
)

FULL_COMMIT_SHA = "0123456789abcdef0123456789abcdef01234567"


def test_initialize_planning_database_is_idempotent(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"

    first = initialize_planning_database(db_path)
    second = initialize_planning_database(db_path)

    assert first.schema_version() == CURRENT_PLANNING_SCHEMA_VERSION
    assert second.schema_version() == CURRENT_PLANNING_SCHEMA_VERSION


def test_plan_round_trip_and_append_only_logs(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")

    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Prove the planning store works.",
            status="active",
            priority=10,
            owner_agent="pytest",
            non_goals={"x": "out"},
            context={"docs": ["README.md"]},
        )
    )
    store.add_plan_decision(
        PlanDecisionRecord(
            decision_id="decision-test",
            plan_id="plan-test",
            decision="Use SQLite.",
            rationale="Structured operational state.",
        )
    )
    store.add_plan_progress(
        PlanProgressRecord(
            progress_id="progress-test",
            plan_id="plan-test",
            event_type="started",
            summary="Started test plan.",
        )
    )

    plans = store.list_plans()

    assert len(plans) == 1
    assert plans[0].plan_id == "plan-test"
    assert plans[0].context == {"docs": ["README.md"]}
    assert store.list_plan_decisions(plan_id="plan-test")[0].decision == "Use SQLite."
    assert store.list_plan_progress(plan_id="plan-test")[0].event_type == "started"


def test_child_plan_mutations_touch_parent_updated_at(tmp_path, monkeypatch):
    moments = iter(
        [
            datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
            datetime(2026, 1, 1, 0, 0, 5, tzinfo=UTC),
            datetime(2026, 1, 1, 0, 0, 10, tzinfo=UTC),
            datetime(2026, 1, 1, 0, 0, 15, tzinfo=UTC),
        ]
    )
    monkeypatch.setattr(planning_module, "_utc_now", lambda: next(moments))
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-touch",
            slug="touch",
            title="Touch",
            goal="Prove child mutations update parent plans.",
            status="active",
        )
    )

    store.add_plan_progress(
        PlanProgressRecord(
            progress_id="progress-touch",
            plan_id="plan-touch",
            event_type="started",
            summary="Touch parent.",
        )
    )

    connection = sqlite3.connect(db_path)
    try:
        updated_at = connection.execute(
            "SELECT updated_at FROM plans WHERE plan_id = ?",
            ("plan-touch",),
        ).fetchone()[0]
    finally:
        connection.close()
    assert updated_at == "2026-01-01T00:00:10Z"


def test_duplicate_links_do_not_touch_parent_updated_at(tmp_path, monkeypatch):
    moments = iter(
        [
            datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
            datetime(2026, 1, 1, 0, 0, 5, tzinfo=UTC),
            datetime(2026, 1, 1, 0, 0, 10, tzinfo=UTC),
            datetime(2026, 1, 1, 0, 0, 15, tzinfo=UTC),
        ]
    )
    monkeypatch.setattr(planning_module, "_utc_now", lambda: next(moments))
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-touch",
            slug="touch",
            title="Touch",
            goal="Prove no-op child mutations leave parent timestamps stable.",
            status="active",
        )
    )
    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-touch",
            artifact_id="insights/example.md",
            relationship="evidence",
        )
    )
    with sqlite3.connect(db_path) as connection:
        after_insert = connection.execute(
            "SELECT updated_at FROM plans WHERE plan_id = ?",
            ("plan-touch",),
        ).fetchone()[0]

    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-touch",
            artifact_id="insights/example.md",
            relationship="evidence",
        )
    )

    with sqlite3.connect(db_path) as connection:
        after_duplicate = connection.execute(
            "SELECT updated_at FROM plans WHERE plan_id = ?",
            ("plan-touch",),
        ).fetchone()[0]
    assert after_duplicate == after_insert


def test_read_only_store_does_not_create_missing_database(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = open_existing_planning_database(db_path)

    with pytest.raises(sqlite3.OperationalError):
        store.list_plans()

    assert not db_path.exists()

    with (
        pytest.raises(ValueError, match="read-only planning store"),
        store.connect(read_only=False),
    ):
        pass


def test_planning_schema_validation_rejects_wrong_sqlite_file(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE plans(plan_id TEXT)")

    store = open_existing_planning_database(db_path)

    with pytest.raises(ValueError, match="planning schema missing table: schema_migrations"):
        store.validate_schema()


def test_planning_schema_validation_rejects_missing_required_index(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP INDEX idx_worker_runs_one_nonterminal_per_task")

    with pytest.raises(ValueError, match="idx_worker_runs_one_nonterminal_per_task"):
        store.validate_schema()


def test_planning_schema_validation_rejects_wrong_partial_index_predicate(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP INDEX idx_worker_runs_one_nonterminal_per_task")
        connection.execute(
            """
            CREATE UNIQUE INDEX idx_worker_runs_one_nonterminal_per_task
            ON worker_runs(task_id)
            WHERE status IN ('running')
            """
        )

    with pytest.raises(ValueError, match="predicate"):
        store.validate_schema()


def test_planning_schema_validation_rejects_weak_table_constraints(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    db_path.parent.mkdir(parents=True)
    weak_sql = planning_module.PLANNING_SCHEMA_SQL.replace(
        """status TEXT NOT NULL CHECK(status IN (
        'active', 'blocked', 'completed', 'abandoned', 'superseded'
    ))""",
        "status TEXT NOT NULL CHECK(length(status) > 0)",
    )
    with sqlite3.connect(db_path) as connection:
        connection.executescript(weak_sql)
        connection.executemany(
            """
            INSERT INTO schema_migrations(version, name, applied_at)
            VALUES (?, ?, '2026-01-01T00:00:00Z')
            """,
            planning_module.PLANNING_SCHEMA_MIGRATIONS,
        )

    store = open_existing_planning_database(db_path)
    with pytest.raises(ValueError, match="plans.*expected SQL"):
        store.validate_schema()


def test_cli_read_commands_return_json_for_empty_results(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    assert main(["plan-init", "--path", str(db_path)]) == 0
    capsys.readouterr()

    assert main(["plan-list", "--path", str(db_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == []

    assert main(["task-list", "--path", str(db_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == []

    assert main(["task-current", "--path", str(db_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out) is None


def test_cli_task_current_reports_empty_queue_in_text_mode(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    assert main(["plan-init", "--path", str(db_path)]) == 0
    capsys.readouterr()

    assert main(["task-current", "--path", str(db_path)]) == 0

    captured = capsys.readouterr()
    assert "No ready supervisor tasks found." in captured.out
    assert "story-loop-status" in captured.out


def test_cli_task_current_points_hitl_queues_to_story_loop_status(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-hitl",
            slug="hitl",
            title="HITL",
            goal="Require a human checkpoint.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-hitl",
            plan_id="plan-hitl",
            title="Human checkpoint",
            goal="Ask the human.",
            task_type="HITL",
            status="ready",
        )
    )

    assert main(["task-current", "--path", str(db_path)]) == 0

    captured = capsys.readouterr()
    assert "No unblocked ready AFK tasks" in captured.out
    assert "story-loop-status" in captured.out
    assert "task-hitl\tHITL\thitl\tplan=plan-hitl(active)" in captured.out


def test_cli_current_queue_views_include_blocked_plans(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-active",
            slug="active",
            title="Active",
            goal="Active checkpoint.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-active",
            plan_id="plan-active",
            title="Active HITL",
            goal="Wait for a human.",
            task_type="HITL",
            status="ready",
        )
    )
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-blocked",
            slug="blocked",
            title="Blocked",
            goal="Blocked successor.",
            status="blocked",
            priority=90,
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-blocked",
            plan_id="plan-blocked",
            title="Blocked AFK",
            goal="Wait for checkpoint.",
            task_type="AFK",
            status="blocked",
            acceptance_criteria=["checkpoint resolved"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )

    assert main(["plan-summary", "--path", str(db_path), "--current-queue", "--json"]) == 0
    summaries = json.loads(capsys.readouterr().out)
    assert [summary["plan"]["plan_id"] for summary in summaries] == [
        "plan-active",
        "plan-blocked",
    ]

    assert main(["task-list", "--path", str(db_path), "--current-queue-plans-only", "--json"]) == 0
    tasks = json.loads(capsys.readouterr().out)
    assert {task["task_id"] for task in tasks} == {"task-active", "task-blocked"}


def test_cli_read_command_reports_missing_database(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"

    assert main(["plan-list", "--path", str(db_path)]) == 1

    captured = capsys.readouterr()
    assert "Planning database is not initialized" in captured.err
    assert "plan-init" in captured.err
    assert not db_path.exists()


def test_cli_read_command_reports_schema_drift_before_late_failure(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE plans(plan_id TEXT)")

    assert main(["plan-list", "--path", str(db_path)]) == 1

    captured = capsys.readouterr()
    assert "Planning database schema is not valid" in captured.err
    assert "schema_migrations" in captured.err
    assert "check_planning_integrity.py" in captured.err
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out


def test_cli_seed_bootstrap_plan_creates_current_task(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    assert main(["plan-init", "--path", str(db_path), "--seed-bootstrap-plan"]) == 0
    capsys.readouterr()

    assert main(["task-current", "--path", str(db_path), "--json"]) == 0

    current_task = json.loads(capsys.readouterr().out)
    assert current_task["task_id"] == "task-bootstrap-orient-and-plan"
    assert current_task["task_type"] == "AFK"
    assert current_task["blocked_by"] == []
    assert current_task["acceptance_criteria"]
    assert "story-loop-status" in current_task["acceptance_criteria"][0]
    assert "task-current" not in " ".join(current_task["acceptance_criteria"])
    assert current_task["verification_commands"] == ["uv run --no-sync python -B scripts/verify.py"]
    assert "plans/planning.sqlite3" in current_task["allowed_paths"]

    store = open_existing_planning_database(db_path)
    plan = next(plan for plan in store.list_plans() if plan.plan_id == "plan-bootstrap-supervisor")
    assert plan.status == "active"
    assert plan.priority == 100
    assert plan.non_goals["full_runtime"].startswith("Do not implement")
    assert "nlp-stock-prediction planning SQLite" in plan.context["patterns"]
    decisions = store.list_plan_decisions(plan_id=plan.plan_id)
    progress = store.list_plan_progress(plan_id=plan.plan_id)
    assert [decision.decision_id for decision in decisions] == ["decision-bootstrap-python-first"]
    assert [event.progress_id for event in progress] == ["progress-bootstrap-created"]

    assert main(["story-loop-status", "--path", str(db_path), "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["queue_state"] == "ready"
    assert status["current_task_id"] == "task-bootstrap-orient-and-plan"


def test_cli_seed_bootstrap_plan_does_not_reactivate_existing_plan(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    assert main(["plan-init", "--path", str(db_path), "--seed-bootstrap-plan"]) == 0
    capsys.readouterr()

    store = open_existing_planning_database(db_path, read_only=False)
    plan = next(plan for plan in store.list_plans() if plan.plan_id == "plan-bootstrap-supervisor")
    store.update_supervisor_task_status("task-bootstrap-orient-and-plan", "completed")
    store.upsert_plan(
        PlanRecord(
            plan_id=plan.plan_id,
            slug=plan.slug,
            title=plan.title,
            goal=plan.goal,
            status="completed",
            priority=plan.priority,
            owner_agent=plan.owner_agent,
            non_goals=plan.non_goals,
            context=plan.context,
            superseded_by_plan_id=plan.superseded_by_plan_id,
        )
    )

    assert main(["plan-init", "--path", str(db_path), "--seed-bootstrap-plan"]) == 0
    capsys.readouterr()

    plans = open_existing_planning_database(db_path).list_plans()
    bootstrap = next(plan for plan in plans if plan.plan_id == "plan-bootstrap-supervisor")
    assert bootstrap.status == "completed"


def test_cli_seed_bootstrap_plan_repairs_stale_bootstrap_plan_metadata(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-bootstrap-supervisor",
            slug="old-slug",
            title="Old Title",
            goal="Old goal.",
            status="completed",
            priority=1,
            owner_agent="old-agent",
            non_goals={"old": "value"},
            context={"old": "value"},
        )
    )

    assert main(["plan-init", "--path", str(db_path), "--seed-bootstrap-plan"]) == 0
    capsys.readouterr()

    plan = next(
        plan
        for plan in open_existing_planning_database(db_path).list_plans()
        if plan.plan_id == "plan-bootstrap-supervisor"
    )
    assert plan.slug == "bootstrap-supervisor"
    assert plan.title == "Bootstrap Codex Supervisor"
    assert plan.goal.startswith("Create the Python-first supervisor repo")
    assert plan.status == "completed"
    assert plan.priority == 100
    assert plan.owner_agent == "codex"
    assert plan.non_goals["source_vendoring"].startswith("Do not vendor")
    assert plan.context["repo_root"] == "<repo-root>"


def test_cli_seed_bootstrap_plan_repairs_missing_bootstrap_task(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-bootstrap-supervisor",
            slug="bootstrap-supervisor",
            title="Bootstrap Codex Supervisor",
            goal="Existing plan row without seeded task.",
            status="active",
            priority=100,
        )
    )

    assert main(["plan-init", "--path", str(db_path), "--seed-bootstrap-plan"]) == 0
    capsys.readouterr()

    assert main(["task-current", "--path", str(db_path), "--json"]) == 0
    current_task = json.loads(capsys.readouterr().out)
    assert current_task["task_id"] == "task-bootstrap-orient-and-plan"


def test_cli_seed_bootstrap_plan_repairs_stale_bootstrap_task_contract(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    assert main(["plan-init", "--path", str(db_path), "--seed-bootstrap-plan"]) == 0
    capsys.readouterr()
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            UPDATE supervisor_tasks
            SET acceptance_criteria_json = '[]',
                verification_commands_json = '[]',
                allowed_paths_json = '[]'
            WHERE task_id = 'task-bootstrap-orient-and-plan'
            """
        )

    assert main(["plan-init", "--path", str(db_path), "--seed-bootstrap-plan"]) == 0
    capsys.readouterr()

    assert main(["task-current", "--path", str(db_path), "--json"]) == 0
    current_task = json.loads(capsys.readouterr().out)
    assert current_task["task_id"] == "task-bootstrap-orient-and-plan"
    assert current_task["verification_commands"] == ["uv run --no-sync python -B scripts/verify.py"]
    assert "plans/planning.sqlite3" in current_task["allowed_paths"]


def test_cli_seed_bootstrap_plan_preserves_existing_bootstrap_task_status(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    assert main(["plan-init", "--path", str(db_path), "--seed-bootstrap-plan"]) == 0
    capsys.readouterr()
    store = open_existing_planning_database(db_path, read_only=False)
    store.update_supervisor_task_status("task-bootstrap-orient-and-plan", "completed")

    assert main(["plan-init", "--path", str(db_path), "--seed-bootstrap-plan"]) == 0
    capsys.readouterr()

    tasks = open_existing_planning_database(db_path).list_supervisor_tasks()
    task = next(task for task in tasks if task.task_id == "task-bootstrap-orient-and-plan")
    assert task.status == "completed"


@pytest.mark.parametrize("unsafe_path", ["../**", "..\\**", "C:\\", "/tmp/**", "file://x"])
def test_supervisor_task_allowed_paths_reject_unsafe_patterns(tmp_path, unsafe_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-paths",
            slug="paths",
            title="Paths",
            goal="Validate repo-relative path contracts.",
            status="active",
        )
    )

    with pytest.raises(ValueError, match="unsafe repo-relative path"):
        store.upsert_supervisor_task(
            SupervisorTaskRecord(
                task_id="task-paths",
                plan_id="plan-paths",
                title="Unsafe paths",
                goal="Should be rejected.",
                task_type="AFK",
                status="ready",
                acceptance_criteria=["done"],
                verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
                allowed_paths=[unsafe_path],
            )
        )


def test_planning_status_fields_reject_unknown_values(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-status",
            slug="status",
            title="Status Plan",
            goal="Validate statuses.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-status",
            plan_id="plan-status",
            title="Task",
            goal="Validate worker status.",
            task_type="AFK",
            status="ready",
        )
    )

    with pytest.raises(ValueError, match="status must be one of"):
        store.upsert_plan_milestone(
            PlanMilestoneRecord(
                milestone_id="milestone-bad",
                plan_id="plan-status",
                title="Bad milestone",
                status="whatever",
            )
        )
    with pytest.raises(ValueError, match="status must be one of"):
        store.upsert_plan_acceptance_criterion(
            PlanAcceptanceCriterionRecord(
                criterion_id="criterion-bad",
                plan_id="plan-status",
                description="Bad criterion",
                status="whatever",
            )
        )
    with pytest.raises(ValueError, match="status must be one of"):
        store.upsert_worker_run(
            WorkerRunRecord(
                worker_run_id="worker-bad",
                task_id="task-status",
                backend="codex_exec",
                status="whatever",
            )
        )


def test_plan_status_rejects_terminal_state_with_open_work(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-open",
            slug="open",
            title="Open Plan",
            goal="Do not hide open work.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-open",
            plan_id="plan-open",
            title="Open task",
            goal="Still needs work.",
            task_type="AFK",
            status="ready",
        )
    )

    with pytest.raises(ValueError, match="close or move open tasks first"):
        store.update_plan_status("plan-open", "completed")
    with pytest.raises(ValueError, match="close or move open tasks first"):
        store.upsert_plan(
            PlanRecord(
                plan_id="plan-open",
                slug="open",
                title="Open Plan",
                goal="Do not hide open work.",
                status="superseded",
            )
        )


def test_plan_status_rejects_completed_state_with_failed_criterion(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-terminal",
            slug="terminal",
            title="Terminal Plan",
            goal="Reject unsatisfied criteria.",
            status="active",
        )
    )
    store.upsert_plan_acceptance_criterion(
        PlanAcceptanceCriterionRecord(
            criterion_id="criterion-failed",
            plan_id="plan-terminal",
            description="Must pass.",
            status="failed",
        )
    )

    with pytest.raises(ValueError, match="criterion criterion-failed is failed"):
        store.update_plan_status("plan-terminal", "completed")

    store.update_plan_status("plan-terminal", "abandoned")


def test_planning_schema_rejects_invalid_status_and_review_values(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    initialize_planning_database(db_path)

    with sqlite3.connect(db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO plans(plan_id, slug, title, goal, status, created_at, updated_at)
                VALUES ('plan-bad', 'bad', 'Bad', 'Reject bad status.', 'whatever', 'now', 'now')
                """
            )
        connection.execute(
            """
            INSERT INTO plans(plan_id, slug, title, goal, status, created_at, updated_at)
            VALUES ('plan-ok', 'ok', 'Ok', 'Seed valid plan.', 'active', 'now', 'now')
            """
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO supervisor_tasks(
                    task_id, plan_id, title, goal, task_type, status, review_required,
                    created_at, updated_at
                )
                VALUES (
                    'task-bad-review', 'plan-ok', 'Task', 'Reject review flag.', 'AFK',
                    'ready', 2, 'now', 'now'
                )
                """
            )


def test_supervisor_task_contract_arrays_reject_non_string_values(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-contract",
            slug="contract",
            title="Contract",
            goal="Validate task contract arrays.",
            status="active",
        )
    )

    with pytest.raises(ValueError, match="acceptance_criteria"):
        store.upsert_supervisor_task(
            SupervisorTaskRecord(
                task_id="task-contract",
                plan_id="plan-contract",
                title="Task",
                goal="Reject malformed contract values.",
                task_type="AFK",
                status="ready",
                acceptance_criteria=["done", ""],
            )
        )


def test_cli_write_commands_record_planning_rows(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-write",
            slug="write",
            title="Write Plan",
            goal="Exercise write CLI commands.",
            status="active",
        )
    )

    assert (
        main(
            [
                "decision-add",
                "--path",
                str(db_path),
                "--decision-id",
                "decision-write",
                "--plan-id",
                "plan-write",
                "--decision",
                "Use typed CLI writes.",
                "--rationale",
                "Fresh threads need durable state writes.",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "progress-add",
                "--path",
                str(db_path),
                "--progress-id",
                "progress-write",
                "--plan-id",
                "plan-write",
                "--event-type",
                "started",
                "--summary",
                "Started write command tests.",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "artifact-link-add",
                "--path",
                str(db_path),
                "--plan-id",
                "plan-write",
                "--artifact-id",
                "artifact.txt",
                "--relationship",
                "evidence",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "commit-link-add",
                "--path",
                str(db_path),
                "--plan-id",
                "plan-write",
                "--commit-sha",
                FULL_COMMIT_SHA,
                "--relationship",
                "implementation",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "task-upsert",
                "--path",
                str(db_path),
                "--task-id",
                "task-write",
                "--plan-id",
                "plan-write",
                "--title",
                "Write task",
                "--goal",
                "Write durable task state.",
                "--task-type",
                "AFK",
                "--status",
                "ready",
                "--scope-json",
                '{"area":"planning"}',
                "--acceptance-criterion",
                "Task exists.",
                "--verification-command",
                "python -B -m pytest -p no:cacheprovider",
                "--allowed-path",
                "src/**",
                "--no-review-required",
                "--json",
            ]
        )
        == 0
    )
    task_json = json.loads(capsys.readouterr().out)
    assert task_json["scope"] == {"area": "planning"}
    assert task_json["review_required"] is False
    assert (
        main(
            [
                "worker-run-upsert",
                "--path",
                str(db_path),
                "--worker-run-id",
                "run-write",
                "--task-id",
                "task-write",
                "--backend",
                "codex_exec",
                "--status",
                "completed",
                "--result-path",
                "runs/run-write/result.json",
                "--metadata-json",
                '{"ok":true}',
            ]
        )
        == 0
    )
    capsys.readouterr()

    read_store = open_existing_planning_database(db_path)
    assert read_store.list_plan_decisions(plan_id="plan-write")[0].decision == (
        "Use typed CLI writes."
    )
    assert read_store.list_plan_progress(plan_id="plan-write")[0].event_type == "started"
    assert read_store.list_plan_artifact_links(plan_id="plan-write")[0].artifact_id == (
        "artifact.txt"
    )
    assert read_store.list_plan_commit_links(plan_id="plan-write")[0].commit_sha == FULL_COMMIT_SHA
    task = read_store.list_supervisor_tasks()[0]
    assert task.task_id == "task-write"
    assert task.status == "completed"
    assert read_store.list_worker_runs(task_id="task-write")[0].metadata == {"ok": True}

    assert (
        main(["worker-run-list", "--path", str(db_path), "--task-id", "task-write", "--json"]) == 0
    )
    worker_runs = json.loads(capsys.readouterr().out)
    assert worker_runs[0]["worker_run_id"] == "run-write"

    assert main(["worker-run-show", "--path", str(db_path), "run-write", "--json"]) == 0
    worker_run = json.loads(capsys.readouterr().out)
    assert worker_run["result_path"] == "runs/run-write/result.json"

    assert main(["plan-summary", "--path", str(db_path), "--plan-id", "plan-write", "--json"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary[0]["worker_runs"][0]["worker_run_id"] == "run-write"


def test_cli_task_upsert_preserves_omitted_optional_fields_on_update(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-safe-upsert",
            slug="safe-upsert",
            title="Safe Upsert",
            goal="Preserve task contract fields.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-safe",
            plan_id="plan-safe-upsert",
            title="Original",
            goal="Original goal.",
            task_type="AFK",
            status="ready",
            scope={"area": "planning"},
            out_of_scope={"skip": "other"},
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
            blocked_by=["task-parent"],
            worker_backend="codex_exec",
            review_required=False,
        )
    )

    assert (
        main(
            [
                "task-upsert",
                "--path",
                str(db_path),
                "--task-id",
                "task-safe",
                "--plan-id",
                "plan-safe-upsert",
                "--title",
                "Updated",
                "--goal",
                "Updated goal.",
                "--task-type",
                "AFK",
                "--status",
                "running",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["title"] == "Updated"
    assert payload["scope"] == {"area": "planning"}
    assert payload["out_of_scope"] == {"skip": "other"}
    assert payload["acceptance_criteria"] == ["done"]
    assert payload["verification_commands"] == ["python -B -m pytest -p no:cacheprovider"]
    assert payload["allowed_paths"] == ["src/**"]
    assert payload["blocked_by"] == ["task-parent"]
    assert payload["worker_backend"] == "codex_exec"
    assert payload["review_required"] is False


def test_cli_task_upsert_replace_allows_contract_reset(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-replace",
            slug="replace",
            title="Replace",
            goal="Reset task contract fields intentionally.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-replace",
            plan_id="plan-replace",
            title="Original",
            goal="Original goal.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )

    assert (
        main(
            [
                "task-upsert",
                "--path",
                str(db_path),
                "--task-id",
                "task-replace",
                "--plan-id",
                "plan-replace",
                "--title",
                "Replaced",
                "--goal",
                "Replaced goal.",
                "--task-type",
                "AFK",
                "--status",
                "pending",
                "--replace",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["acceptance_criteria"] == []
    assert payload["verification_commands"] == []
    assert payload["allowed_paths"] == []
    assert payload["worker_backend"] == "codex_exec"
    assert payload["review_required"] is True


def test_cli_worker_run_upsert_preserves_omitted_evidence_fields(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker-safe-upsert",
            slug="worker-safe-upsert",
            title="Worker Safe Upsert",
            goal="Preserve worker evidence fields.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker-safe",
            plan_id="plan-worker-safe-upsert",
            title="Task",
            goal="Run worker.",
            task_type="AFK",
            status="ready",
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-safe",
            task_id="task-worker-safe",
            backend="codex_exec",
            status="failed",
            worktree_path="worktrees/run-safe",
            prompt_path="runs/run-safe/prompt.md",
            jsonl_path="runs/run-safe/out.jsonl",
            result_path="runs/run-safe/result.json",
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:01:00Z",
            failure_class="old",
            metadata={"kept": True},
        )
    )

    assert (
        main(
            [
                "worker-run-upsert",
                "--path",
                str(db_path),
                "--worker-run-id",
                "run-safe",
                "--task-id",
                "task-worker-safe",
                "--backend",
                "codex_exec",
                "--status",
                "failed",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "failed"
    assert payload["worktree_path"] == "worktrees/run-safe"
    assert payload["prompt_path"] == "runs/run-safe/prompt.md"
    assert payload["jsonl_path"] == "runs/run-safe/out.jsonl"
    assert payload["result_path"] == "runs/run-safe/result.json"
    assert payload["started_at"] == "2026-01-01T00:00:00Z"
    assert payload["completed_at"] == "2026-01-01T00:01:00Z"
    assert payload["failure_class"] == "old"
    assert payload["metadata"] == {"kept": True}


def test_cli_creation_commands_record_plan_milestone_and_criterion(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    assert main(["plan-init", "--path", str(db_path)]) == 0
    capsys.readouterr()

    assert (
        main(
            [
                "plan-upsert",
                "--path",
                str(db_path),
                "--plan-id",
                "plan-created",
                "--slug",
                "created",
                "--title",
                "Created Plan",
                "--goal",
                "Create durable planning rows from the CLI.",
                "--status",
                "active",
                "--priority",
                "25",
                "--owner-agent",
                "pytest",
                "--non-goals-json",
                '{"skip":"manual SQL"}',
                "--context-json",
                '{"docs":["PLANS.md"]}',
                "--json",
            ]
        )
        == 0
    )
    plan_json = json.loads(capsys.readouterr().out)
    assert plan_json["plan_id"] == "plan-created"
    assert plan_json["non_goals"] == {"skip": "manual SQL"}

    assert (
        main(
            [
                "milestone-upsert",
                "--path",
                str(db_path),
                "--milestone-id",
                "milestone-created",
                "--plan-id",
                "plan-created",
                "--title",
                "Created Milestone",
                "--status",
                "pending",
                "--sort-order",
                "10",
                "--details-json",
                '{"slice":"vertical"}',
                "--json",
            ]
        )
        == 0
    )
    milestone_json = json.loads(capsys.readouterr().out)
    assert milestone_json["details"] == {"slice": "vertical"}

    assert (
        main(
            [
                "criterion-upsert",
                "--path",
                str(db_path),
                "--criterion-id",
                "criterion-created",
                "--plan-id",
                "plan-created",
                "--description",
                "Typed creation commands are covered by tests.",
                "--status",
                "pending",
                "--verification-command",
                "uv run --no-sync python -B -m pytest -p no:cacheprovider",
                "--json",
            ]
        )
        == 0
    )
    criterion_json = json.loads(capsys.readouterr().out)
    assert criterion_json["verification_command"] == (
        "uv run --no-sync python -B -m pytest -p no:cacheprovider"
    )

    read_store = open_existing_planning_database(db_path)
    plan = read_store.list_plans()[0]
    assert plan.plan_id == "plan-created"
    assert plan.priority == 25
    assert plan.context == {"docs": ["PLANS.md"]}
    assert read_store.list_plan_milestones(plan_id="plan-created")[0].milestone_id == (
        "milestone-created"
    )
    assert read_store.list_plan_acceptance_criteria(plan_id="plan-created")[0].criterion_id == (
        "criterion-created"
    )


def test_cli_status_commands_update_lifecycle_state(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-status",
            slug="status",
            title="Status Plan",
            goal="Exercise status CLI commands.",
            status="active",
        )
    )
    store.upsert_plan_milestone(
        PlanMilestoneRecord(
            milestone_id="milestone-status",
            plan_id="plan-status",
            title="Milestone",
            status="pending",
        )
    )
    store.upsert_plan_acceptance_criterion(
        PlanAcceptanceCriterionRecord(
            criterion_id="criterion-status",
            plan_id="plan-status",
            description="Criterion",
            status="pending",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-status",
            plan_id="plan-status",
            title="Task",
            goal="Change state.",
            task_type="AFK",
            status="ready",
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-status",
            task_id="task-status",
            backend="codex_exec",
            status="running",
            result_path="runs/run-status/result.json",
        )
    )

    commands = [
        ["milestone-status", "--milestone-id", "milestone-status", "--status", "completed"],
        ["criterion-status", "--criterion-id", "criterion-status", "--status", "completed"],
        [
            "worker-run-status",
            "--worker-run-id",
            "run-status",
            "--status",
            "completed",
            "--result-path",
            "runs/run-status/result.json",
            "--completed-at",
            "2026-01-01T00:00:00Z",
        ],
        ["task-status", "--task-id", "task-status", "--status", "completed"],
        ["plan-status", "--plan-id", "plan-status", "--status", "completed"],
    ]
    for command in commands:
        assert main([command[0], "--path", str(db_path), *command[1:]]) == 0
        capsys.readouterr()

    read_store = open_existing_planning_database(db_path)
    assert read_store.list_plan_milestones(plan_id="plan-status")[0].status == "completed"
    assert read_store.list_plan_acceptance_criteria(plan_id="plan-status")[0].status == (
        "completed"
    )
    assert read_store.list_supervisor_tasks()[0].status == "completed"
    assert read_store.list_worker_runs(task_id="task-status")[0].status == "completed"
    assert read_store.list_plans()[0].status == "completed"


def test_supervisor_task_listing_prioritizes_active_plans(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-active",
            slug="active",
            title="Active Plan",
            goal="Do the active work.",
            status="active",
            priority=5,
        )
    )
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-completed",
            slug="completed",
            title="Completed Plan",
            goal="Historical work.",
            status="completed",
            priority=100,
        )
    )

    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-active",
            plan_id="plan-active",
            title="Active task",
            goal="Do the active task.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-completed",
            plan_id="plan-completed",
            title="Completed task",
            goal="Do old work.",
            task_type="AFK",
            status="ready",
        )
    )

    active_tasks = store.list_supervisor_tasks(status="ready", active_plans_only=True)
    all_tasks = store.list_supervisor_tasks(status="ready")
    current = store.next_ready_afk_task()

    assert [task.task_id for task in active_tasks] == ["task-active"]
    assert [task.task_id for task in all_tasks] == ["task-active", "task-completed"]
    assert active_tasks[0].verification_commands == ["python -B -m pytest -p no:cacheprovider"]
    assert current is not None
    assert current.task_id == "task-active"


def test_plan_listing_prioritizes_active_plans_before_historical_priority(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-completed",
            slug="completed",
            title="Completed Plan",
            goal="Historical work.",
            status="completed",
            priority=100,
        )
    )
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-active",
            slug="active",
            title="Active Plan",
            goal="Do active work.",
            status="active",
            priority=5,
        )
    )

    plans = store.list_plans()

    assert [plan.plan_id for plan in plans] == ["plan-active", "plan-completed"]


def test_next_ready_afk_task_excludes_hitl_and_blocked_tasks(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-active",
            slug="active",
            title="Active Plan",
            goal="Do the active work.",
            status="active",
            priority=5,
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-hitl",
            plan_id="plan-active",
            title="Human task",
            goal="Ask a human.",
            task_type="HITL",
            status="ready",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-blocked",
            plan_id="plan-active",
            title="Blocked task",
            goal="Wait for another task.",
            task_type="AFK",
            status="ready",
            blocked_by=["task-other"],
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-current",
            plan_id="plan-active",
            title="Current task",
            goal="Run now.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )

    current = store.next_ready_afk_task()

    assert current is not None
    assert current.task_id == "task-current"


def test_next_ready_afk_task_ignores_completed_dependency_blockers(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-active",
            slug="active",
            title="Active Plan",
            goal="Do the active work.",
            status="active",
            priority=5,
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-parent",
            plan_id="plan-active",
            title="Parent task",
            goal="Already done.",
            task_type="AFK",
            status="completed",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-child",
            plan_id="plan-active",
            title="Child task",
            goal="Run after completed parent.",
            task_type="AFK",
            status="ready",
            blocked_by=["task-parent"],
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )

    current = store.next_ready_afk_task()

    assert current is not None
    assert current.task_id == "task-child"


def test_next_ready_afk_task_resolves_completed_blocker_from_inactive_plan(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-completed",
            slug="completed",
            title="Completed Plan",
            goal="Hold historical blocker evidence.",
            status="completed",
            priority=1,
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-parent",
            plan_id="plan-completed",
            title="Parent task",
            goal="Already done in an earlier plan.",
            task_type="AFK",
            status="completed",
        )
    )
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-active",
            slug="active",
            title="Active Plan",
            goal="Continue after historical dependency.",
            status="active",
            priority=5,
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-child",
            plan_id="plan-active",
            title="Child task",
            goal="Run after completed parent.",
            task_type="AFK",
            status="ready",
            blocked_by=["task-parent"],
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )

    current = store.next_ready_afk_task()

    assert current is not None
    assert current.task_id == "task-child"


def test_next_ready_afk_task_ignores_underspecified_task_contracts(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-active",
            slug="active",
            title="Active",
            goal="Run executable work.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-underspecified",
            plan_id="plan-active",
            title="Underspecified task",
            goal="Looks ready but lacks a runnable contract.",
            task_type="AFK",
            status="ready",
        )
    )

    current = store.next_ready_afk_task()

    assert current is None


def test_next_ready_afk_task_rejects_blank_execution_contract_values(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-active",
            slug="active",
            title="Active",
            goal="Reject blank contract fields.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-blank-contract",
            plan_id="plan-active",
            title="Blank contract",
            goal="Looks ready but contains blank contract values.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            """
            UPDATE supervisor_tasks
            SET acceptance_criteria_json = ?,
                verification_commands_json = ?,
                allowed_paths_json = ?
            WHERE task_id = ?
            """,
            ('[" "]', '[""]', '["\\t"]', "task-blank-contract"),
        )

    with pytest.raises(ValueError, match="acceptance_criteria"):
        store.next_ready_afk_task()


def test_next_ready_afk_task_ignores_task_with_nonterminal_worker_run(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-active",
            slug="active",
            title="Active",
            goal="Avoid double-claiming work.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-claimed",
            plan_id="plan-active",
            title="Claimed task",
            goal="Already has a worker run.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-claimed",
            task_id="task-claimed",
            backend="codex_exec",
            status="queued",
        )
    )

    current = store.next_ready_afk_task()

    assert current is None


def test_next_ready_afk_task_ignores_task_with_completed_worker_run(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-active",
            slug="active",
            title="Active",
            goal="Avoid rerunning completed worker evidence.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-completed-run",
            plan_id="plan-active",
            title="Completed-run task",
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
            worker_run_id="run-completed",
            task_id="task-completed-run",
            backend="codex_exec",
            status="completed",
            result_path="runs/run-completed/result.json",
        )
    )

    current = store.next_ready_afk_task()

    assert current is None


def test_claim_next_ready_afk_task_is_atomic_state_transition(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-active",
            slug="active",
            title="Active",
            goal="Claim one task.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-ready",
            plan_id="plan-active",
            title="Ready task",
            goal="Claim this task once.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )

    claim = store.claim_next_ready_afk_task(
        worker_run_id="run-claim",
        backend="codex_exec",
        worktree_path="worktrees/run-claim",
        metadata={"source": "pytest"},
    )

    assert claim is not None
    assert claim.task.task_id == "task-ready"
    assert claim.task.status == "running"
    assert claim.worker_run.task_id == "task-ready"
    assert claim.worker_run.status == "running"
    assert claim.worker_run.worktree_path == "worktrees/run-claim"
    assert claim.worker_run.metadata == {"source": "pytest"}
    assert store.next_ready_afk_task() is None
    assert (
        store.claim_next_ready_afk_task(
            worker_run_id="run-second",
            backend="codex_exec",
        )
        is None
    )


def test_claim_next_ready_afk_task_respects_expected_current_task_id(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-active",
            slug="active",
            title="Active",
            goal="Claim one task.",
            status="active",
            priority=100,
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-current",
            plan_id="plan-active",
            title="Current task",
            goal="Claim this exact task.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )

    assert (
        store.claim_next_ready_afk_task(
            worker_run_id="run-stale",
            backend="codex_exec",
            task_id="task-stale",
        )
        is None
    )

    current = store.next_ready_afk_task()
    assert current is not None
    assert current.task_id == "task-current"

    claim = store.claim_next_ready_afk_task(
        worker_run_id="run-current",
        backend="codex_exec",
        task_id="task-current",
    )

    assert claim is not None
    assert claim.task.task_id == "task-current"
    assert claim.worker_run.task_id == "task-current"


def test_claim_next_ready_afk_task_rejects_terminal_or_review_status(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")

    with pytest.raises(ValueError, match="status must be one of"):
        store.claim_next_ready_afk_task(
            worker_run_id="run-blocked",
            backend="codex_exec",
            status="blocked",
        )


def test_cli_task_claim_returns_claim_or_null(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-active",
            slug="active",
            title="Active",
            goal="Claim through CLI.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-ready",
            plan_id="plan-active",
            title="Ready task",
            goal="Claim this task once.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )

    assert (
        main(
            [
                "task-claim",
                "--path",
                str(db_path),
                "--task-id",
                "task-ready",
                "--worker-run-id",
                "run-cli",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["task"]["task_id"] == "task-ready"
    assert payload["task"]["status"] == "running"
    assert payload["worker_run"]["worker_run_id"] == "run-cli"

    assert (
        main(
            [
                "task-claim",
                "--path",
                str(db_path),
                "--task-id",
                "task-ready",
                "--worker-run-id",
                "run-cli-empty",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) is None


def test_plan_progress_with_artifact_links_is_atomic(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-progress",
            slug="progress",
            title="Progress Plan",
            goal="Record atomic progress.",
            status="active",
        )
    )

    with pytest.raises(ValueError):
        store.add_plan_progress_with_artifact_links(
            PlanProgressRecord(
                progress_id="progress-atomic",
                plan_id="plan-progress",
                event_type="completed",
                summary="Should not commit.",
            ),
            (
                PlanArtifactLinkRecord(
                    plan_id="plan-other",
                    artifact_id="src/example.py",
                    relationship="evidence",
                ),
            ),
        )

    assert store.list_plan_progress(plan_id="plan-progress") == ()
    assert store.list_plan_artifact_links(plan_id="plan-progress") == ()


def test_plan_progress_linked_artifact_creates_artifact_link(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-progress",
            slug="progress",
            title="Progress",
            goal="Record linked artifacts.",
            status="active",
        )
    )

    store.add_plan_progress(
        PlanProgressRecord(
            progress_id="progress-linked",
            plan_id="plan-progress",
            event_type="recorded",
            summary="Recorded linked artifact.",
            linked_artifact_id="src/example.py",
        )
    )

    artifact_links = store.list_plan_artifact_links(plan_id="plan-progress")

    assert len(artifact_links) == 1
    assert artifact_links[0].artifact_id == "src/example.py"
    assert artifact_links[0].relationship == "progress-linked-artifact"


def test_planning_helper_surface_covers_queue_tables(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Exercise helper coverage.",
            status="active",
        )
    )
    store.upsert_plan_milestone(
        PlanMilestoneRecord(
            milestone_id="milestone-test",
            plan_id="plan-test",
            title="Milestone",
            status="pending",
            details={"why": "coverage"},
        )
    )
    store.upsert_plan_acceptance_criterion(
        PlanAcceptanceCriterionRecord(
            criterion_id="criterion-test",
            plan_id="plan-test",
            description="Criterion",
            status="pending",
            verification_command="python -B -m pytest -p no:cacheprovider",
        )
    )
    store.add_plan_artifact_link(
        PlanArtifactLinkRecord(
            plan_id="plan-test",
            artifact_id="artifact-test",
            relationship="evidence",
        )
    )
    store.add_plan_commit_link(
        PlanCommitLinkRecord(
            plan_id="plan-test",
            commit_sha=FULL_COMMIT_SHA,
            relationship="implementation",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-test",
            plan_id="plan-test",
            title="Task",
            goal="Do the task.",
            task_type="AFK",
            status="ready",
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-test",
            task_id="task-test",
            backend="codex_exec",
            status="completed",
            result_path="runs/run-test/result.json",
            metadata={"ok": True},
        )
    )

    assert store.list_plan_milestones(plan_id="plan-test")[0].details == {"why": "coverage"}
    assert store.list_plan_acceptance_criteria(plan_id="plan-test")[0].verification_command == (
        "python -B -m pytest -p no:cacheprovider"
    )
    assert store.list_plan_artifact_links(plan_id="plan-test")[0].artifact_id == "artifact-test"
    assert store.list_plan_commit_links(plan_id="plan-test")[0].commit_sha == FULL_COMMIT_SHA
    assert store.list_worker_runs(task_id="task-test")[0].metadata == {"ok": True}


def test_plan_acceptance_criterion_rejects_unsafe_verification_command(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Exercise criterion validation.",
            status="active",
        )
    )

    with pytest.raises(ValueError, match="verification_command contains unsafe"):
        store.upsert_plan_acceptance_criterion(
            PlanAcceptanceCriterionRecord(
                criterion_id="criterion-test",
                plan_id="plan-test",
                description="Criterion",
                status="pending",
                verification_command="uv run pytest",
            )
        )


def test_plan_artifact_links_reject_unsafe_repo_relative_paths(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Exercise artifact path validation.",
            status="active",
        )
    )

    with pytest.raises(ValueError, match="artifact_id contains unsafe"):
        store.add_plan_artifact_link(
            PlanArtifactLinkRecord(
                plan_id="plan-test",
                artifact_id="C:relative/path.md",
                relationship="evidence",
            )
        )


def test_plan_progress_rejects_unsafe_linked_artifact_paths(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Exercise progress artifact validation.",
            status="active",
        )
    )

    with pytest.raises(ValueError, match="linked_artifact_id contains unsafe"):
        store.add_plan_progress(
            PlanProgressRecord(
                progress_id="progress-test",
                plan_id="plan-test",
                event_type="noted",
                summary="Progress",
                linked_artifact_id="C:relative/path.md",
            )
        )


def test_plan_commit_links_require_full_commit_sha(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")

    with pytest.raises(ValueError, match="40-character lowercase hexadecimal"):
        store.add_plan_commit_link(
            PlanCommitLinkRecord(
                plan_id="plan-test",
                commit_sha="abc123",
                relationship="implementation",
            )
        )


def test_delete_plan_commit_link_removes_link_and_touches_parent(tmp_path, monkeypatch):
    moments = iter(
        [
            datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
            datetime(2026, 1, 1, 0, 0, 5, tzinfo=UTC),
            datetime(2026, 1, 1, 0, 0, 10, tzinfo=UTC),
            datetime(2026, 1, 1, 0, 0, 15, tzinfo=UTC),
        ]
    )
    monkeypatch.setattr(planning_module, "_utc_now", lambda: next(moments))
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Exercise commit link deletion.",
            status="active",
        )
    )
    record = PlanCommitLinkRecord(
        plan_id="plan-test",
        commit_sha=FULL_COMMIT_SHA,
        relationship="implementation",
    )
    store.add_plan_commit_link(record)

    assert store.delete_plan_commit_link(record) is True
    assert store.list_plan_commit_links(plan_id="plan-test") == ()
    with sqlite3.connect(store.path) as connection:
        updated_at = connection.execute(
            "SELECT updated_at FROM plans WHERE plan_id = ?",
            ("plan-test",),
        ).fetchone()[0]
    assert updated_at == "2026-01-01T00:00:15Z"
    assert store.delete_plan_commit_link(record) is False


def test_completed_worker_runs_require_result_path(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Exercise worker run validation.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-test",
            plan_id="plan-test",
            title="Task",
            goal="Do the task.",
            task_type="AFK",
            status="ready",
        )
    )

    with pytest.raises(ValueError, match="result_path"):
        store.upsert_worker_run(
            WorkerRunRecord(
                worker_run_id="run-test",
                task_id="task-test",
                backend="codex_exec",
                status="completed",
            )
        )

    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-test",
            task_id="task-test",
            backend="codex_exec",
            status="running",
        )
    )

    with pytest.raises(ValueError, match="result_path"):
        store.update_worker_run_status("run-test", "completed")


@pytest.mark.parametrize(
    "result_path",
    [
        "../runs/result.json",
        "..\\runs\\result.json",
        "C:\\runs\\result.json",
        "/tmp/runs/result.json",
        "https://example.test/result.json",
        "runs/result.txt",
        "runs/result.json#summary",
    ],
)
def test_completed_worker_runs_reject_unsafe_result_paths(tmp_path, result_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Exercise worker run validation.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-test",
            plan_id="plan-test",
            title="Task",
            goal="Do the task.",
            task_type="AFK",
            status="ready",
        )
    )

    with pytest.raises(ValueError, match="completed worker result_path is unsafe"):
        store.upsert_worker_run(
            WorkerRunRecord(
                worker_run_id="run-test",
                task_id="task-test",
                backend="codex_exec",
                status="completed",
                result_path=result_path,
            )
        )

    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-test",
            task_id="task-test",
            backend="codex_exec",
            status="running",
        )
    )
    with pytest.raises(ValueError, match="completed worker result_path is unsafe"):
        store.update_worker_run_status("run-test", "completed", result_path=result_path)


def test_worker_run_status_rejects_blank_result_path_without_erasing_existing_path(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Exercise worker result path validation.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-test",
            plan_id="plan-test",
            title="Task",
            goal="Complete the run.",
            task_type="AFK",
            status="ready",
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-test",
            task_id="task-test",
            backend="codex_exec",
            status="completed",
            result_path="runs/run-test/result.json",
        )
    )

    with pytest.raises(ValueError, match="result_path must be nonblank"):
        store.update_worker_run_status("run-test", "completed", result_path="")

    run = open_existing_planning_database(db_path).list_worker_runs(task_id="task-test")[0]
    assert run.result_path == "runs/run-test/result.json"


def test_task_status_cannot_hide_active_worker_run(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Reject misleading terminal state.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-test",
            plan_id="plan-test",
            title="Task",
            goal="Do the task.",
            task_type="AFK",
            status="ready",
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-test",
            task_id="task-test",
            backend="codex_exec",
            status="running",
        )
    )

    with pytest.raises(ValueError, match="cannot set task task-test to completed"):
        store.update_supervisor_task_status("task-test", "completed")


@pytest.mark.parametrize("status", ["ready", "running", "blocked", "reviewing"])
def test_task_status_rejects_open_afk_state_without_execution_contract(tmp_path, status):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Reject underspecified open AFK work.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-test",
            plan_id="plan-test",
            title="Task",
            goal="Missing its execution contract.",
            task_type="AFK",
            status="pending",
        )
    )

    with pytest.raises(ValueError, match="invalid execution contract"):
        store.update_supervisor_task_status("task-test", status)


def test_worker_run_upsert_rejects_reassigning_existing_run_to_another_task(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Reject ambiguous worker run ownership.",
            status="active",
        )
    )
    for task_id in ("task-one", "task-two"):
        store.upsert_supervisor_task(
            SupervisorTaskRecord(
                task_id=task_id,
                plan_id="plan-test",
                title=task_id,
                goal="Own a worker run.",
                task_type="AFK",
                status="ready",
            )
        )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-shared",
            task_id="task-one",
            backend="codex_exec",
            status="running",
        )
    )

    with pytest.raises(ValueError, match="already attached to task task-one"):
        store.upsert_worker_run(
            WorkerRunRecord(
                worker_run_id="run-shared",
                task_id="task-two",
                backend="codex_exec",
                status="running",
            )
        )


def test_worker_run_upsert_rejects_second_nonterminal_run_for_same_task(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Reject concurrent worker runs.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-test",
            plan_id="plan-test",
            title="Task",
            goal="Own one active worker run.",
            task_type="AFK",
            status="ready",
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-one",
            task_id="task-test",
            backend="codex_exec",
            status="running",
        )
    )

    with pytest.raises(ValueError, match="already has nonterminal worker run run-one"):
        store.upsert_worker_run(
            WorkerRunRecord(
                worker_run_id="run-two",
                task_id="task-test",
                backend="codex_exec",
                status="queued",
            )
        )

    store.update_worker_run_status("run-one", "completed", result_path="runs/run-one/result.json")
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-two",
            task_id="task-test",
            backend="codex_exec",
            status="queued",
        )
    )
    runs = open_existing_planning_database(
        tmp_path / "plans" / "planning.sqlite3"
    ).list_worker_runs(task_id="task-test")
    assert {run.worker_run_id for run in runs} == {"run-one", "run-two"}


def test_task_upsert_rejects_status_that_hides_nonterminal_worker_run(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Reject hidden running work.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-test",
            plan_id="plan-test",
            title="Task",
            goal="Own one active worker run.",
            task_type="AFK",
            status="ready",
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-one",
            task_id="task-test",
            backend="codex_exec",
            status="running",
        )
    )

    with pytest.raises(ValueError, match="cannot set task task-test to ready"):
        store.upsert_supervisor_task(
            SupervisorTaskRecord(
                task_id="task-test",
                plan_id="plan-test",
                title="Task",
                goal="Do not hide active work.",
                task_type="AFK",
                status="ready",
            )
        )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-test",
            plan_id="plan-test",
            title="Task",
            goal="Blocked is still visible as open work.",
            task_type="AFK",
            status="blocked",
        )
    )


@pytest.mark.parametrize("task_status", ["completed", "failed", "cancelled", "pending"])
def test_worker_run_upsert_rejects_nonterminal_run_on_nonstartable_task(tmp_path, task_status):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Reject hidden active worker runs.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-test",
            plan_id="plan-test",
            title="Task",
            goal="Do the task.",
            task_type="AFK",
            status=task_status,
        )
    )

    with pytest.raises(ValueError, match="reopen the task before starting a worker run"):
        store.upsert_worker_run(
            WorkerRunRecord(
                worker_run_id="run-test",
                task_id="task-test",
                backend="codex_exec",
                status="running",
            )
        )


def test_supervisor_task_cannot_move_plans_after_worker_history_exists(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    for plan_id in ("plan-one", "plan-two"):
        store.upsert_plan(
            PlanRecord(
                plan_id=plan_id,
                slug=plan_id,
                title=plan_id,
                goal="Own task history.",
                status="active",
            )
        )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-test",
            plan_id="plan-one",
            title="Task",
            goal="Do the task.",
            task_type="AFK",
            status="ready",
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-one",
            task_id="task-test",
            backend="codex_exec",
            status="completed",
            result_path="runs/run-one/result.json",
        )
    )

    with pytest.raises(ValueError, match="cannot move task task-test from plan plan-one"):
        store.upsert_supervisor_task(
            SupervisorTaskRecord(
                task_id="task-test",
                plan_id="plan-two",
                title="Task",
                goal="Do the task.",
                task_type="AFK",
                status="ready",
            )
        )


def test_worker_run_status_can_complete_with_result_path_without_full_upsert(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Exercise worker status result path.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-test",
            plan_id="plan-test",
            title="Task",
            goal="Complete the worker run.",
            task_type="AFK",
            status="ready",
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-test",
            task_id="task-test",
            backend="codex_exec",
            status="running",
            prompt_path="runs/run-test/prompt.md",
            metadata={"kept": True},
        )
    )

    assert (
        main(
            [
                "worker-run-status",
                "--path",
                str(db_path),
                "--worker-run-id",
                "run-test",
                "--status",
                "completed",
                "--result-path",
                "runs/run-test/result.json",
                "--completed-at",
                "2026-01-01T00:00:00Z",
            ]
        )
        == 0
    )
    capsys.readouterr()

    run = open_existing_planning_database(db_path).list_worker_runs(task_id="task-test")[0]
    assert run.status == "completed"
    assert run.result_path == "runs/run-test/result.json"
    assert run.prompt_path == "runs/run-test/prompt.md"
    assert run.metadata == {"kept": True}
    task = open_existing_planning_database(db_path).list_supervisor_tasks()[0]
    assert task.status == "reviewing"
    links = open_existing_planning_database(db_path).list_plan_artifact_links(plan_id="plan-test")
    assert any(
        link.artifact_id == "runs/run-test/result.json" and link.relationship == "worker-result"
        for link in links
    )


def test_worker_run_status_clears_stale_terminal_evidence_on_rerun(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Exercise worker rerun evidence cleanup.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-test",
            plan_id="plan-test",
            title="Task",
            goal="Rerun the worker.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["rerun completes"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-test",
            task_id="task-test",
            backend="codex_exec",
            status="failed",
            result_path="runs/run-test/result.json",
            completed_at="2026-01-01T00:00:00Z",
            failure_class="test-failure",
        )
    )

    with pytest.raises(ValueError, match="reopen the task before starting a worker run"):
        store.update_worker_run_status("run-test", "running")

    store.update_supervisor_task_status("task-test", "ready")
    store.update_worker_run_status("run-test", "running")

    run = open_existing_planning_database(db_path).list_worker_runs(task_id="task-test")[0]
    assert run.status == "running"
    assert run.result_path is None
    assert run.completed_at is None
    assert run.failure_class is None


def test_worker_run_upsert_clears_preserved_terminal_evidence_on_rerun(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Exercise worker rerun evidence cleanup.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-test",
            plan_id="plan-test",
            title="Task",
            goal="Rerun the worker.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["rerun completes"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-test",
            task_id="task-test",
            backend="codex_exec",
            status="failed",
            result_path="runs/run-test/result.json",
            completed_at="2026-01-01T00:00:00Z",
            failure_class="test-failure",
        )
    )
    with pytest.raises(ValueError, match="reopen the task before starting a worker run"):
        store.upsert_worker_run(
            WorkerRunRecord(
                worker_run_id="run-test",
                task_id="task-test",
                backend="codex_exec",
                status="running",
                result_path="runs/run-test/result.json",
                completed_at="2026-01-01T00:00:00Z",
                failure_class="test-failure",
            )
        )

    store.update_supervisor_task_status("task-test", "ready")
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-test",
            task_id="task-test",
            backend="codex_exec",
            status="running",
            result_path="runs/run-test/result.json",
            completed_at="2026-01-01T00:00:00Z",
            failure_class="test-failure",
        )
    )

    run = open_existing_planning_database(db_path).list_worker_runs(task_id="task-test")[0]
    assert run.status == "running"
    assert run.result_path is None
    assert run.completed_at is None
    assert run.failure_class is None


def test_worker_run_completion_can_complete_non_review_task(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Exercise worker completion.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-test",
            plan_id="plan-test",
            title="Task",
            goal="Complete the worker run.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["done"],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
            review_required=False,
        )
    )
    claim = store.claim_next_ready_afk_task(worker_run_id="run-test", backend="codex_exec")
    assert claim is not None

    store.update_worker_run_status(
        "run-test",
        "completed",
        result_path="runs/run-test/result.json",
    )

    read_store = open_existing_planning_database(db_path)
    task = read_store.list_supervisor_tasks()[0]
    run = read_store.list_worker_runs(task_id="task-test")[0]
    assert task.status == "completed"
    assert run.status == "completed"


def test_cli_reports_clean_error_when_planning_path_cannot_be_inferred(
    tmp_path,
    monkeypatch,
    capsys,
):
    monkeypatch.chdir(tmp_path)

    assert main(["plan-list"]) == 1

    captured = capsys.readouterr()
    assert "Could not locate planning database" in captured.err
    assert "Run from a codex-supervisor/supervised project root or pass --path" in captured.err
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out

    assert main(["plan-init"]) == 1

    captured = capsys.readouterr()
    assert "Could not locate planning database" in captured.err
    assert "Run from a codex-supervisor/supervised project root or pass --path" in captured.err
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out


def test_cli_does_not_infer_planning_path_from_generic_git_repo(tmp_path, monkeypatch, capsys):
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)

    assert main(["plan-init"]) == 1

    captured = capsys.readouterr()
    assert "Could not locate planning database" in captured.err
    assert "codex-supervisor/supervised project root" in captured.err
    assert not (tmp_path / "plans" / "planning.sqlite3").exists()


def test_repo_root_discovery_skips_nested_source_git_clone(tmp_path):
    repo_root = tmp_path / "codex-supervisor"
    nested_source = repo_root / "sources" / "openai-codex"
    nested_source.mkdir(parents=True)
    (repo_root / ".git").mkdir()
    (repo_root / "pyproject.toml").write_text("[project]\nname = 'codex-supervisor'\n")
    (repo_root / "src" / "codex_supervisor").mkdir(parents=True)
    (repo_root / "plans").mkdir()
    (repo_root / "plans" / "planning.sqlite3").write_bytes(b"")
    (nested_source / ".git").mkdir()

    assert find_repo_root(nested_source) == repo_root
    assert default_planning_database_path(repo_root) == repo_root / "plans" / "planning.sqlite3"


def test_cli_read_commands_report_validation_errors_without_traceback(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Exercise read error reporting.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-bad-json",
            plan_id="plan-test",
            title="Bad JSON task",
            goal="Break typed read validation.",
            task_type="AFK",
            status="ready",
        )
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE supervisor_tasks SET acceptance_criteria_json = ? WHERE task_id = ?",
            ('{"not":"array"}', "task-bad-json"),
        )

    assert main(["task-current", "--path", str(db_path)]) == 1

    captured = capsys.readouterr()
    assert "Could not read planning database" in captured.err
    assert "check_planning_integrity.py" in captured.err
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out


def test_cli_plan_summary_reports_child_read_errors_without_traceback(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Exercise summary error reporting.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-bad-json",
            plan_id="plan-test",
            title="Bad JSON task",
            goal="Break typed summary validation.",
            task_type="AFK",
            status="ready",
        )
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE supervisor_tasks SET acceptance_criteria_json = ? WHERE task_id = ?",
            ('{"not":"array"}', "task-bad-json"),
        )

    assert main(["plan-summary", "--path", str(db_path), "--json"]) == 1

    captured = capsys.readouterr()
    assert "Could not read planning database" in captured.err
    assert "check_planning_integrity.py" in captured.err
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out


def test_cli_task_upsert_reports_preserve_read_errors_without_traceback(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Exercise write error reporting.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-bad-json",
            plan_id="plan-test",
            title="Bad JSON task",
            goal="Break preservation read validation.",
            task_type="AFK",
            status="ready",
        )
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE supervisor_tasks SET acceptance_criteria_json = ? WHERE task_id = ?",
            ('{"not":"array"}', "task-bad-json"),
        )

    assert (
        main(
            [
                "task-upsert",
                "--path",
                str(db_path),
                "--task-id",
                "task-bad-json",
                "--plan-id",
                "plan-test",
                "--title",
                "Still bad",
                "--goal",
                "Should report cleanly.",
                "--task-type",
                "AFK",
                "--status",
                "ready",
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert "Could not update planning database" in captured.err
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out
