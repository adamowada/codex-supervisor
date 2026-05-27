from __future__ import annotations

import json

from codex_supervisor.cli import main
from codex_supervisor.goal_contracts import (
    render_goal_contract,
    render_goal_contract_markdown,
)
from codex_supervisor.planning import (
    PlanRecord,
    SupervisorTaskRecord,
    SupervisorTaskSummaryRecord,
    initialize_planning_database,
)


def test_goal_contract_renderer_produces_required_sections():
    task = SupervisorTaskSummaryRecord(
        task_id="task-contract",
        plan_id="plan-contract",
        plan_title="Contract Plan",
        plan_status="active",
        plan_priority=50,
        title="Render contract",
        goal="Render a worker-ready contract.",
        task_type="AFK",
        status="ready",
        scope={"area": "planning"},
        out_of_scope={"edits": ["backend launch"]},
        acceptance_criteria=["Objective is present.", "Stop condition is present."],
        verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
        allowed_paths=["src/**", "tests/**"],
        blocked_by=[],
        worker_backend="codex_exec",
        review_required=True,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:01Z",
    )

    contract = render_goal_contract(task)
    markdown = render_goal_contract_markdown(contract)

    assert contract.objective == "Render a worker-ready contract."
    assert contract.context_to_read_first[0] == "README.md"
    assert contract.in_scope["plan"]["plan_id"] == "plan-contract"
    assert contract.in_scope["scope"] == {"area": "planning"}
    assert contract.constraints["allowed_paths"] == ["src/**", "tests/**"]
    assert contract.out_of_scope == {"edits": ["backend launch"]}
    assert contract.acceptance_criteria == (
        "Objective is present.",
        "Stop condition is present.",
    )
    assert contract.verification_surface == (
        "uv run --no-sync python -B -m pytest -p no:cacheprovider",
    )
    assert "native_goal_mode" in contract.execution_surface
    assert contract.execution_surface["source_authority"]["execution_order"] == (
        "plans/planning.sqlite3"
    )
    assert contract.execution_surface["worker_backend"] == {
        "name": "codex_exec",
        "backend_status": "available",
        "execution_mode": "codex_exec_worker_backend",
        "native_goal_support": "prompt_rendered_fallback_only",
        "official_noninteractive_native_goal_path": False,
    }
    goal_mode_preflight = contract.execution_surface["native_goal_mode"]["preflight"]
    assert "[features] goals = true" in goal_mode_preflight[1]
    assert "only when Goal Mode setup is in scope" in goal_mode_preflight[1]
    assert "In read-only mode" in goal_mode_preflight[1]
    assert (
        "only if the running process does not pick up an allowed config change"
        in goal_mode_preflight[1]
    )
    assert "then restart Codex" not in goal_mode_preflight[1]
    assert (
        "planning SQLite remains canonical"
        in contract.execution_surface["native_goal_mode"]["authority"]
    )
    assert "planning SQLite records the task progress/completion" in contract.stop_condition
    assert "Proceed unless" in contract.blocked_condition
    for heading in (
        "## Objective",
        "## Context To Read First",
        "## In Scope",
        "## Out Of Scope",
        "## Constraints",
        "## Acceptance Criteria",
        "## Verification Surface",
        "## Stop Condition",
        "## Blocked Condition",
        "## Iteration Policy",
        "## Budget Or Status Limits",
        "## Record Updates",
        "## Execution Surface",
    ):
        assert heading in markdown


def test_goal_contract_renderer_surfaces_blocked_state():
    task = SupervisorTaskSummaryRecord(
        task_id="task-blocked",
        plan_id="plan-contract",
        plan_title="Contract Plan",
        plan_status="blocked",
        plan_priority=50,
        title="Render blocked contract",
        goal="Render a blocked contract.",
        task_type="HITL",
        status="blocked",
        scope={},
        out_of_scope={},
        acceptance_criteria=[],
        verification_commands=[],
        allowed_paths=[],
        blocked_by=["task-parent"],
        worker_backend="codex_exec",
        review_required=False,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:01Z",
    )

    contract = render_goal_contract(task)

    assert "Do not start autonomous implementation" in contract.blocked_condition
    assert "plan status is `blocked`" in contract.blocked_condition
    assert "blocked dependencies remain: `task-parent`" in contract.blocked_condition
    assert "acceptance criteria are missing" in contract.blocked_condition
    assert "verification commands are missing" in contract.blocked_condition
    assert "allowed paths are missing" in contract.blocked_condition


def test_cli_goal_contract_render_defaults_to_current_ready_afk_task(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-contract",
            slug="contract",
            title="Contract Plan",
            goal="Exercise contract rendering.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-contract",
            plan_id="plan-contract",
            title="Render contract",
            goal="Render the next Goal Contract.",
            task_type="AFK",
            status="ready",
            scope={"area": "planning"},
            acceptance_criteria=["Contract is rendered."],
            verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )

    assert main(["goal-contract-render", "--path", str(db_path)]) == 0

    markdown = capsys.readouterr().out
    assert "# Goal Contract" in markdown
    assert "Render the next Goal Contract." in markdown
    assert '"allowed_paths": [' in markdown

    assert main(["goal-contract-render", "--path", str(db_path), "--json"]) == 0

    contract_json = json.loads(capsys.readouterr().out)
    assert contract_json["task_id"] == "task-contract"
    assert contract_json["objective"] == "Render the next Goal Contract."
    assert contract_json["verification_surface"] == [
        "uv run --no-sync python -B -m pytest -p no:cacheprovider"
    ]
    assert "README.md" in contract_json["context_to_read_first"]


def test_cli_goal_contract_render_omits_resolved_dependency_blockers(tmp_path, capsys):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-contract",
            slug="contract",
            title="Contract Plan",
            goal="Exercise resolved dependency rendering.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-parent",
            plan_id="plan-contract",
            title="Completed parent",
            goal="Already completed.",
            task_type="AFK",
            status="completed",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-child",
            plan_id="plan-contract",
            title="Child",
            goal="Render without stale blockers.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["Contract is rendered."],
            verification_commands=["uv run --no-sync python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
            blocked_by=["task-parent"],
        )
    )

    assert main(["goal-contract-render", "--path", str(db_path), "--json"]) == 0

    contract_json = json.loads(capsys.readouterr().out)
    assert contract_json["task_id"] == "task-child"
    assert "Proceed unless" in contract_json["blocked_condition"]
    assert "task-parent" not in contract_json["blocked_condition"]
