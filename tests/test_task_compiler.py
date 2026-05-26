from __future__ import annotations

from codex_supervisor.planning import (
    PlanAcceptanceCriterionRecord,
    PlanMilestoneRecord,
    PlanRecord,
    initialize_planning_database,
    open_existing_planning_database,
)
from codex_supervisor.task_compiler import apply_compiled_tasks, compile_tasks_from_plan


def test_task_compiler_prefers_open_criteria_over_milestones(tmp_path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-compile",
            slug="compile",
            title="Compile Tasks",
            goal="Turn broad plan state into vertical slices.",
            status="active",
        )
    )
    store.upsert_plan_milestone(
        PlanMilestoneRecord(
            milestone_id="milestone-a",
            plan_id="plan-compile",
            title="Ship milestone",
            status="pending",
        )
    )
    store.upsert_plan_acceptance_criterion(
        PlanAcceptanceCriterionRecord(
            criterion_id="criterion-a",
            plan_id="plan-compile",
            description="Criterion A passes.",
            status="pending",
            verification_command="uv run --no-sync python -B scripts/verify.py",
        )
    )

    report = compile_tasks_from_plan(
        store,
        plan_id="plan-compile",
        allowed_paths=("src/**", "tests/**"),
        status="ready",
    )

    assert report.status == "compiled"
    assert len(report.tasks) == 1
    task = report.tasks[0]
    assert task.task_id.startswith("task-criterion-criterion-a-")
    assert task.status == "ready"
    assert task.scope == {
        "compiled_from": "plan_acceptance_criterion",
        "criterion_id": "criterion-a",
    }
    assert task.acceptance_criteria == ["Criterion A passes."]
    assert task.verification_commands == ["uv run --no-sync python -B scripts/verify.py"]

    applied = apply_compiled_tasks(store, report)
    assert applied.status == "applied"
    read_store = open_existing_planning_database(db_path)
    assert read_store.list_supervisor_tasks()[0].task_id == task.task_id


def test_task_compiler_falls_back_to_milestones(tmp_path):
    store = initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-compile",
            slug="compile",
            title="Compile Tasks",
            goal="Turn milestones into tasks.",
            status="active",
        )
    )
    store.upsert_plan_milestone(
        PlanMilestoneRecord(
            milestone_id="milestone-a",
            plan_id="plan-compile",
            title="Ship milestone",
            status="pending",
        )
    )

    report = compile_tasks_from_plan(
        store,
        plan_id="plan-compile",
        allowed_paths=("src/**",),
        verification_commands=("uv run --no-sync python -B scripts/verify.py",),
    )

    assert len(report.tasks) == 1
    assert report.tasks[0].task_id.startswith("task-milestone-milestone-a-")
    assert report.tasks[0].scope == {
        "compiled_from": "plan_milestone",
        "milestone_id": "milestone-a",
    }
