from __future__ import annotations

from codex_supervisor.planning import (
    CURRENT_PLANNING_SCHEMA_VERSION,
    PlanDecisionRecord,
    PlanProgressRecord,
    PlanRecord,
    initialize_planning_database,
)


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
