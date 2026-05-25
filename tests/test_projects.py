import json
import sqlite3
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from codex_supervisor.cli import main
from codex_supervisor.planning import PlanRecord, initialize_planning_database
from codex_supervisor.projects import (
    MAX_HARNESS_CONFIG_BYTES,
    MAX_HARNESS_PROMPT_BYTES,
    MAX_MARKDOWN_PLAN_BYTES,
    MAX_TASKS_JSON_BYTES,
    build_project_task_seeds,
    discover_projects,
    stable_project_id_from_path,
)


def test_project_registry_discovers_generic_repo_with_stable_id(tmp_path: Path) -> None:
    repo = _write_generic_repo(tmp_path / "demo-supervised")

    first = discover_projects((repo,))
    second = discover_projects((repo,))

    assert len(first) == 1
    entry = first[0]
    assert entry == second[0]
    assert entry.project_id.startswith("demo-supervised-")
    assert entry.root_path == str(repo.resolve())
    assert entry.adapter_type == "generic_repo"
    assert entry.trust_policy == "local_trusted"
    assert entry.status == "ready"
    assert entry.facts is not None
    assert entry.facts.has_planning_database is True
    assert entry.facts.has_tasks_json is True
    assert entry.facts.source_documents == (
        "AGENTS.md",
        "PLANS.md",
        "TESTING.md",
        "README.md",
    )
    assert entry.facts.verification_commands == (
        "uv run --no-sync python -B scripts/verify.py",
        "uv run --no-sync python -B scripts/check_protected_files.py",
    )


def test_generic_repo_adapter_reports_bounded_facts_only(tmp_path: Path) -> None:
    repo = _write_generic_repo(tmp_path / "bounded")
    (repo / "deep").mkdir()
    (repo / "deep" / "private-notes.md").write_text("not an authority file", encoding="utf-8")
    (repo / "random.py").write_text("print('not a verification surface')\n", encoding="utf-8")

    entry = discover_projects((repo,))[0]

    assert entry.facts is not None
    facts = entry.facts
    assert "deep/private-notes.md" not in facts.source_documents
    assert "random.py" not in facts.verification_commands
    assert facts.authority_markers == (
        "AGENTS.md",
        "PLANS.md",
        "plans/planning.sqlite3",
        "TASKS.json",
    )


def test_generic_repo_adapter_extracts_bounded_task_candidates(tmp_path: Path) -> None:
    repo = _write_generic_repo(
        tmp_path / "task-candidates",
        tasks=[
            {
                "id": "ship-search",
                "title": "Ship search",
                "goal": "Add search to the product list.",
                "task_type": "AFK",
                "acceptance_criteria": ["Search results filter by query."],
                "verification_commands": ["uv run --no-sync python -B scripts/verify.py"],
                "allowed_paths": ["src/search.py", "tests/test_search.py"],
                "blocked_by": ["task-design-review"],
            },
            {
                "title": "Approve launch copy",
                "goal": "Get human approval for launch copy.",
                "task_type": "hitl",
                "acceptance_criteria": ["Human approval is recorded."],
                "allowed_paths": ["README.md"],
            },
        ],
    )

    facts = discover_projects((repo,))[0].facts

    assert facts is not None
    assert facts.adapter_findings == ()
    assert len(facts.candidate_tasks) == 2
    first = facts.candidate_tasks[0]
    assert first.source_id == "tasks-json-ship-search"
    assert first.source_path == "TASKS.json"
    assert first.title == "Ship search"
    assert first.goal == "Add search to the product list."
    assert first.task_type == "AFK"
    assert first.acceptance_criteria == ("Search results filter by query.",)
    assert first.verification_commands == ("uv run --no-sync python -B scripts/verify.py",)
    assert first.allowed_paths == ("src/search.py", "tests/test_search.py")
    assert first.blocked_by == ("task-design-review",)
    assert first.source_authority == ("TASKS.json",)
    second = facts.candidate_tasks[1]
    assert second.task_type == "HITL"
    assert second.verification_commands == (
        "uv run --no-sync python -B scripts/verify.py",
        "uv run --no-sync python -B scripts/check_protected_files.py",
    )


def test_planning_sqlite_adapter_extracts_candidates_without_mutating_target(
    tmp_path: Path,
) -> None:
    repo = _write_planning_sqlite_project(tmp_path / "planning-style")
    before_bytes = (repo / "plans" / "planning.sqlite3").read_bytes()

    entry = discover_projects((repo,))[0]

    assert entry.adapter_type == "nlp_stock_prediction_planning_sqlite"
    assert entry.status == "ready"
    assert entry.facts is not None
    facts = entry.facts
    assert facts.authority_markers == ("plans/planning.sqlite3",)
    assert facts.has_planning_database is True
    assert facts.adapter_findings == ()
    assert facts.verification_commands == ("uv run --no-sync python -B scripts/verify.py",)
    assert len(facts.candidate_tasks) == 1
    candidate = facts.candidate_tasks[0]
    assert candidate.source_id == "planning-sqlite-task-add-signals"
    assert candidate.source_path == "plans/planning.sqlite3:tasks/task-add-signals"
    assert candidate.title == "Add signal feature"
    assert candidate.goal == "Add a bounded signal feature."
    assert candidate.task_type == "AFK"
    assert candidate.acceptance_criteria == ("Signal feature is implemented.",)
    assert candidate.verification_commands == ("uv run --no-sync python -B scripts/verify.py",)
    assert candidate.allowed_paths == ("src/signals.py",)
    assert candidate.blocked_by == ("task-data-contract",)
    assert candidate.source_authority == ("plans/planning.sqlite3", "tasks")
    assert (repo / "plans" / "planning.sqlite3").read_bytes() == before_bytes


def test_project_seed_tasks_cli_applies_planning_sqlite_candidates_only_to_supervisor_db(
    tmp_path: Path,
    capsys,
) -> None:
    supervisor_db = tmp_path / "supervisor" / "planning.sqlite3"
    store = initialize_planning_database(supervisor_db)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-seeded-project",
            slug="seeded-project",
            title="Seeded Project",
            goal="Receive seeded tasks.",
            status="active",
        )
    )
    repo = _write_planning_sqlite_project(tmp_path / "target-planning")
    target_before = (repo / "plans" / "planning.sqlite3").read_bytes()

    assert (
        main(
            [
                "project-seed-tasks",
                "--path",
                str(supervisor_db),
                "--root",
                str(repo),
                "--plan-id",
                "plan-seeded-project",
                "--apply",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    tasks = store.list_supervisor_tasks()
    assert payload["project"]["adapter_type"] == "nlp_stock_prediction_planning_sqlite"
    assert payload["task_ids"] == [tasks[0].task_id]
    assert tasks[0].scope["source_project"]["adapter_type"] == (
        "nlp_stock_prediction_planning_sqlite"
    )
    assert tasks[0].scope["source_candidate"]["source_authority"] == [
        "plans/planning.sqlite3",
        "tasks",
    ]
    assert (repo / "plans" / "planning.sqlite3").read_bytes() == target_before


def test_planning_sqlite_adapter_reports_corrupt_database_without_generic_fallback(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "corrupt-planning"
    (repo / "plans").mkdir(parents=True)
    (repo / "plans" / "planning.sqlite3").write_bytes(b"not sqlite")

    entry = discover_projects((repo,))[0]

    assert entry.adapter_type == "nlp_stock_prediction_planning_sqlite"
    assert entry.status == "unsupported"
    assert entry.failure_class == "unsupported_planning_sqlite"
    assert entry.facts is not None
    assert entry.facts.adapter_findings
    assert "planning SQLite database could not be read" in entry.facts.adapter_findings[0]


def test_planning_sqlite_adapter_filters_open_tasks_before_candidate_limit(
    tmp_path: Path,
) -> None:
    terminal_rows = [
        (
            f"task-{index:02d}-completed",
            f"Completed {index}",
            "Already completed.",
            "completed",
            "AFK",
            json.dumps(["Done."]),
            json.dumps([]),
            json.dumps([]),
            json.dumps([]),
        )
        for index in range(25)
    ]
    repo = _write_planning_sqlite_project(
        tmp_path / "terminal-heavy-planning",
        task_rows=[
            *terminal_rows,
            (
                "task-99-ready",
                "Ready work",
                "Surface the ready work after terminal rows.",
                "ready",
                "AFK",
                json.dumps(["Ready task is surfaced."]),
                json.dumps([]),
                json.dumps(["src/ready.py"]),
                json.dumps([]),
            ),
        ],
    )

    entry = discover_projects((repo,))[0]

    assert entry.status == "ready"
    assert entry.facts is not None
    assert [candidate.source_id for candidate in entry.facts.candidate_tasks] == [
        "planning-sqlite-task-99-ready"
    ]


def test_markdown_plan_adapter_extracts_candidates_without_mutating_target(
    tmp_path: Path,
) -> None:
    repo = _write_markdown_plan_project(tmp_path / "observe-style")
    plan_path = repo / "plans" / "active" / "safety-plan.md"
    before_text = plan_path.read_text(encoding="utf-8")

    entry = discover_projects((repo,))[0]

    assert entry.adapter_type == "observe_safety_markdown_plan"
    assert entry.status == "ready"
    assert entry.facts is not None
    facts = entry.facts
    assert facts.authority_markers == ("plans/active/safety-plan.md",)
    assert facts.adapter_findings == ()
    assert facts.verification_commands == ("uv run --no-sync python -B scripts/validate_plan.py",)
    assert len(facts.candidate_tasks) == 1
    candidate = facts.candidate_tasks[0]
    assert candidate.source_id == "markdown-plan-plans-active-safety-plan-md-add-guardrails"
    assert candidate.source_path == "plans/active/safety-plan.md#task-add-guardrails"
    assert candidate.title == "Add guardrails"
    assert candidate.goal == "Add bounded guardrails."
    assert candidate.task_type == "AFK"
    assert candidate.acceptance_criteria == ("Guardrails are implemented.",)
    assert candidate.verification_commands == (
        "uv run --no-sync python -B scripts/validate_plan.py",
    )
    assert candidate.allowed_paths == ("src/guardrails.py",)
    assert candidate.blocked_by == ("task-data-contract",)
    assert candidate.source_authority == (
        "plans/active/safety-plan.md",
        "Task: Add guardrails",
    )
    assert plan_path.read_text(encoding="utf-8") == before_text


def test_project_seed_tasks_cli_applies_markdown_plan_candidates_only_to_supervisor_db(
    tmp_path: Path,
    capsys,
) -> None:
    supervisor_db = tmp_path / "supervisor" / "planning.sqlite3"
    store = initialize_planning_database(supervisor_db)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-markdown-seeded-project",
            slug="markdown-seeded-project",
            title="Markdown Seeded Project",
            goal="Receive markdown seeded tasks.",
            status="active",
        )
    )
    repo = _write_markdown_plan_project(tmp_path / "target-markdown")
    plan_path = repo / "plans" / "active" / "safety-plan.md"
    target_before = plan_path.read_text(encoding="utf-8")

    assert (
        main(
            [
                "project-seed-tasks",
                "--path",
                str(supervisor_db),
                "--root",
                str(repo),
                "--plan-id",
                "plan-markdown-seeded-project",
                "--apply",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    tasks = store.list_supervisor_tasks()
    assert payload["project"]["adapter_type"] == "observe_safety_markdown_plan"
    assert payload["task_ids"] == [tasks[0].task_id]
    assert tasks[0].scope["source_project"]["adapter_type"] == "observe_safety_markdown_plan"
    assert tasks[0].scope["source_candidate"]["source_authority"] == [
        "plans/active/safety-plan.md",
        "Task: Add guardrails",
    ]
    assert plan_path.read_text(encoding="utf-8") == target_before


def test_markdown_plan_adapter_reports_malformed_plan_without_generic_fallback(
    tmp_path: Path,
) -> None:
    repo = _write_markdown_plan_project(
        tmp_path / "malformed-markdown",
        plan_text="""<!-- observe-safety-plan -->
Plan Status: active

## Task: Missing goal
Status: ready
""",
    )

    entry = discover_projects((repo,))[0]

    assert entry.adapter_type == "observe_safety_markdown_plan"
    assert entry.status == "unsupported"
    assert entry.failure_class == "unsupported_markdown_plan"
    assert entry.facts is not None
    assert "must include nonblank title and Goal" in entry.facts.adapter_findings[0]


def test_markdown_plan_adapter_reports_oversized_plan_without_generic_fallback(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "oversized-markdown"
    (repo / "plans" / "active").mkdir(parents=True)
    plan_path = repo / "plans" / "active" / "huge-plan.md"
    plan_path.write_text("x" * (MAX_MARKDOWN_PLAN_BYTES + 1), encoding="utf-8")

    entry = discover_projects((repo,))[0]

    assert entry.adapter_type == "observe_safety_markdown_plan"
    assert entry.status == "unsupported"
    assert entry.failure_class == "unsupported_markdown_plan"
    assert entry.facts is not None
    assert "is larger than" in entry.facts.adapter_findings[0]


def test_markdown_plan_without_marker_falls_back_to_generic_repo(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "generic-with-plan-notes"
    (repo / "plans" / "active").mkdir(parents=True)
    (repo / "AGENTS.md").write_text("# Agent notes\n", encoding="utf-8")
    (repo / "plans" / "active" / "notes.md").write_text("# Notes\n", encoding="utf-8")

    entry = discover_projects((repo,))[0]

    assert entry.adapter_type == "generic_repo"
    assert entry.status == "ready"


def test_harness_config_adapter_extracts_candidates_without_mutating_target(
    tmp_path: Path,
) -> None:
    repo = _write_harness_config_project(tmp_path / "harness-style")
    config_path = repo / "harness" / "config.json"
    prompt_path = repo / "prompts" / "browser-smoke.md"
    before_config = config_path.read_text(encoding="utf-8")
    before_prompt = prompt_path.read_text(encoding="utf-8")

    entry = discover_projects((repo,))[0]

    assert entry.adapter_type == "codex_subagent_testing_harness_config"
    assert entry.status == "ready"
    assert entry.facts is not None
    facts = entry.facts
    assert facts.authority_markers == ("harness/config.json",)
    assert facts.adapter_findings == ()
    assert facts.verification_commands == ("uv run --no-sync python -B scripts/run_harness.py",)
    assert len(facts.candidate_tasks) == 1
    candidate = facts.candidate_tasks[0]
    assert candidate.source_id == "harness-config-browser-smoke"
    assert candidate.source_path == "harness/config.json:runs/browser-smoke"
    assert candidate.title == "Run browser smoke"
    assert candidate.goal == "Exercise the browser harness prompt."
    assert candidate.task_type == "AFK"
    assert candidate.acceptance_criteria == ("Harness smoke completes.",)
    assert candidate.verification_commands == ("uv run --no-sync python -B scripts/run_harness.py",)
    assert candidate.allowed_paths == ("harness/browser.py",)
    assert candidate.blocked_by == ("task-fixture-data",)
    assert candidate.source_authority == ("harness/config.json", "prompts/browser-smoke.md")
    assert config_path.read_text(encoding="utf-8") == before_config
    assert prompt_path.read_text(encoding="utf-8") == before_prompt


def test_project_seed_tasks_cli_applies_harness_config_candidates_only_to_supervisor_db(
    tmp_path: Path,
    capsys,
) -> None:
    supervisor_db = tmp_path / "supervisor" / "planning.sqlite3"
    store = initialize_planning_database(supervisor_db)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-harness-seeded-project",
            slug="harness-seeded-project",
            title="Harness Seeded Project",
            goal="Receive harness seeded tasks.",
            status="active",
        )
    )
    repo = _write_harness_config_project(tmp_path / "target-harness")
    config_path = repo / "harness" / "config.json"
    target_before = config_path.read_text(encoding="utf-8")

    assert (
        main(
            [
                "project-seed-tasks",
                "--path",
                str(supervisor_db),
                "--root",
                str(repo),
                "--plan-id",
                "plan-harness-seeded-project",
                "--apply",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    tasks = store.list_supervisor_tasks()
    assert payload["project"]["adapter_type"] == "codex_subagent_testing_harness_config"
    assert payload["task_ids"] == [tasks[0].task_id]
    assert tasks[0].scope["source_project"]["adapter_type"] == (
        "codex_subagent_testing_harness_config"
    )
    assert tasks[0].scope["source_candidate"]["source_authority"] == [
        "harness/config.json",
        "prompts/browser-smoke.md",
    ]
    assert config_path.read_text(encoding="utf-8") == target_before


def test_harness_config_adapter_reports_malformed_config_without_generic_fallback(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "malformed-harness"
    (repo / "harness").mkdir(parents=True)
    (repo / "harness" / "config.json").write_text("{not json", encoding="utf-8")

    entry = discover_projects((repo,))[0]

    assert entry.adapter_type == "codex_subagent_testing_harness_config"
    assert entry.status == "unsupported"
    assert entry.failure_class == "unsupported_harness_config"
    assert entry.facts is not None
    assert "could not be parsed" in entry.facts.adapter_findings[0]


def test_harness_config_adapter_reports_oversized_config_without_generic_fallback(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "oversized-harness"
    (repo / "harness").mkdir(parents=True)
    (repo / "harness" / "config.json").write_text(
        "x" * (MAX_HARNESS_CONFIG_BYTES + 1),
        encoding="utf-8",
    )

    entry = discover_projects((repo,))[0]

    assert entry.adapter_type == "codex_subagent_testing_harness_config"
    assert entry.status == "unsupported"
    assert entry.failure_class == "unsupported_harness_config"
    assert entry.facts is not None
    assert "is larger than" in entry.facts.adapter_findings[0]


def test_harness_config_adapter_reports_oversized_prompt_without_generic_fallback(
    tmp_path: Path,
) -> None:
    repo = _write_harness_config_project(
        tmp_path / "oversized-prompt",
        prompt_text="x" * (MAX_HARNESS_PROMPT_BYTES + 1),
    )

    entry = discover_projects((repo,))[0]

    assert entry.adapter_type == "codex_subagent_testing_harness_config"
    assert entry.status == "unsupported"
    assert entry.failure_class == "unsupported_harness_config"
    assert entry.facts is not None
    assert "prompts/browser-smoke.md is larger than" in entry.facts.adapter_findings[0]


@pytest.mark.parametrize(
    "prompt_path",
    ("../secret.md", "C:\\secret.md", "C:secret.md", "/secret.md", "\\secret.md"),
)
def test_harness_config_adapter_rejects_unsafe_prompt_paths(
    tmp_path: Path,
    prompt_path: str,
) -> None:
    repo = _write_harness_config_project(
        tmp_path / "unsafe-prompt-path",
        config_payload={
            "schema": "codex-subagent-testing",
            "runs": [
                {
                    "id": "unsafe",
                    "title": "Unsafe prompt",
                    "goal": "Should not resolve outside or through drive syntax.",
                    "prompt_path": prompt_path,
                }
            ],
        },
    )

    entry = discover_projects((repo,))[0]

    assert entry.adapter_type == "codex_subagent_testing_harness_config"
    assert entry.status == "unsupported"
    assert entry.failure_class == "unsupported_harness_config"
    assert entry.facts is not None
    assert "must include a safe prompt_path" in entry.facts.adapter_findings[0]


def test_harness_config_adapter_normalizes_windows_prompt_separators(
    tmp_path: Path,
) -> None:
    repo = _write_harness_config_project(
        tmp_path / "windows-prompt-path",
        config_payload={
            "schema": "codex-subagent-testing",
            "runs": [
                {
                    "id": "windows-path",
                    "title": "Windows prompt",
                    "goal": "Normalize Windows relative prompt separators.",
                    "prompt_path": "prompts\\browser-smoke.md",
                }
            ],
        },
    )

    entry = discover_projects((repo,))[0]

    assert entry.status == "ready"
    assert entry.facts is not None
    assert entry.facts.candidate_tasks[0].source_authority == (
        "harness/config.json",
        "prompts/browser-smoke.md",
    )


def test_harness_config_adapter_preserves_tasks_collection_in_source_path(
    tmp_path: Path,
) -> None:
    repo = _write_harness_config_project(
        tmp_path / "tasks-array-harness",
        config_payload={
            "schema": "codex-subagent-testing",
            "tasks": [
                {
                    "id": "prompt-task",
                    "title": "Prompt task",
                    "goal": "Seed from a tasks array.",
                    "prompt_path": "prompts/browser-smoke.md",
                }
            ],
        },
    )

    entry = discover_projects((repo,))[0]

    assert entry.status == "ready"
    assert entry.facts is not None
    assert entry.facts.candidate_tasks[0].source_path == ("harness/config.json:tasks/prompt-task")


def test_harness_config_without_marker_falls_back_to_generic_repo(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "generic-with-harness-notes"
    (repo / "harness").mkdir(parents=True)
    (repo / "AGENTS.md").write_text("# Agent notes\n", encoding="utf-8")
    (repo / "harness" / "config.json").write_text(
        json.dumps({"runs": []}),
        encoding="utf-8",
    )

    entry = discover_projects((repo,))[0]

    assert entry.adapter_type == "generic_repo"
    assert entry.status == "ready"


def test_project_task_seeds_map_candidate_fields(tmp_path: Path) -> None:
    repo = _write_generic_repo(
        tmp_path / "seed-source",
        tasks=[
            {
                "id": "ship-search",
                "title": "Ship search",
                "goal": "Add search to the product list.",
                "acceptance_criteria": ["Search results filter by query."],
                "verification_commands": ["uv run --no-sync python -B scripts/verify.py"],
                "allowed_paths": ["src/search.py"],
                "blocked_by": ["task-design-review"],
            }
        ],
    )
    entry = discover_projects((repo,))[0]

    seeds = build_project_task_seeds(entry, plan_id="plan-seeded-project")

    assert len(seeds) == 1
    seed = seeds[0]
    assert seed.task_id.startswith("task-seed-source-")
    assert seed.task_id.endswith("-tasks-json-ship-search")
    assert seed.plan_id == "plan-seeded-project"
    assert seed.title == "Ship search"
    assert seed.goal == "Add search to the product list."
    assert seed.task_type == "AFK"
    assert seed.status == "pending"
    assert seed.acceptance_criteria == ("Search results filter by query.",)
    assert seed.verification_commands == ("uv run --no-sync python -B scripts/verify.py",)
    assert seed.allowed_paths == ("src/search.py",)
    assert seed.blocked_by == ("task-design-review",)
    assert seed.worker_backend == "codex_exec"
    assert seed.review_required is True
    assert seed.scope["source_project"]["project_id"] == entry.project_id
    assert seed.scope["source_candidate"]["source_id"] == "tasks-json-ship-search"


def test_generic_repo_adapter_reports_invalid_and_oversized_tasks_json(
    tmp_path: Path,
) -> None:
    invalid_repo = _write_generic_repo(tmp_path / "invalid-tasks")
    (invalid_repo / "TASKS.json").write_text("{not json", encoding="utf-8")
    oversized_repo = _write_generic_repo(tmp_path / "oversized-tasks")
    (oversized_repo / "TASKS.json").write_text(
        " " * (MAX_TASKS_JSON_BYTES + 1),
        encoding="utf-8",
    )

    invalid_facts = discover_projects((invalid_repo,))[0].facts
    oversized_facts = discover_projects((oversized_repo,))[0].facts

    assert invalid_facts is not None
    assert invalid_facts.candidate_tasks == ()
    assert invalid_facts.adapter_findings
    assert "TASKS.json could not be parsed" in invalid_facts.adapter_findings[0]
    assert oversized_facts is not None
    assert oversized_facts.candidate_tasks == ()
    assert oversized_facts.adapter_findings == (
        f"TASKS.json is larger than {MAX_TASKS_JSON_BYTES} bytes.",
    )


def test_project_list_cli_prints_json_for_current_repo(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    repo = _write_generic_repo(tmp_path / "current")
    monkeypatch.chdir(repo)

    assert main(["project-list", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["project_id"].startswith("current-")
    assert payload[0]["adapter_type"] == "generic_repo"
    assert payload[0]["status"] == "ready"
    assert payload[0]["facts"]["has_planning_database"] is True
    assert payload[0]["facts"]["candidate_tasks"] == []


def test_project_seed_tasks_cli_prints_dry_run_json_without_planning_db(
    tmp_path: Path,
    capsys,
) -> None:
    repo = _write_generic_repo(
        tmp_path / "dry-run-seed",
        tasks=[
            {
                "title": "Add queue docs",
                "goal": "Document queue operations.",
                "acceptance_criteria": ["Queue docs exist."],
                "allowed_paths": ["docs/queue.md"],
            }
        ],
    )

    assert (
        main(
            [
                "project-seed-tasks",
                "--root",
                str(repo),
                "--plan-id",
                "plan-seeded-project",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["applied"] is False
    assert payload["project"]["adapter_type"] == "generic_repo"
    assert len(payload["task_seeds"]) == 1
    assert payload["task_seeds"][0]["status"] == "pending"
    assert payload["task_seeds"][0]["allowed_paths"] == ["docs/queue.md"]


def test_project_seed_tasks_cli_apply_is_idempotent_and_mutates_only_planning_db(
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-seeded-project",
            slug="seeded-project",
            title="Seeded Project",
            goal="Receive seeded tasks.",
            status="active",
        )
    )
    repo = _write_generic_repo(
        tmp_path / "apply-seed",
        tasks=[
            {
                "id": "task-one",
                "title": "Task one",
                "goal": "Do one bounded thing.",
                "acceptance_criteria": ["One thing is done."],
                "verification_commands": ["uv run --no-sync python -B scripts/verify.py"],
                "allowed_paths": ["src/one.py"],
            }
        ],
    )
    original_tasks_json = (repo / "TASKS.json").read_text(encoding="utf-8")
    command = [
        "project-seed-tasks",
        "--path",
        str(db_path),
        "--root",
        str(repo),
        "--plan-id",
        "plan-seeded-project",
        "--apply",
        "--json",
    ]

    assert main(command) == 0
    first_payload = json.loads(capsys.readouterr().out)
    assert main(command) == 0
    second_payload = json.loads(capsys.readouterr().out)

    tasks = store.list_supervisor_tasks()
    assert len(tasks) == 1
    seeded = tasks[0]
    assert seeded.task_id == first_payload["task_ids"][0] == second_payload["task_ids"][0]
    assert seeded.status == "pending"
    assert seeded.title == "Task one"
    assert seeded.allowed_paths == ["src/one.py"]
    assert seeded.scope["source_project"]["adapter_type"] == "generic_repo"
    assert (repo / "TASKS.json").read_text(encoding="utf-8") == original_tasks_json


def test_project_seed_tasks_cli_reports_missing_and_candidate_free_roots(
    tmp_path: Path,
    capsys,
) -> None:
    missing = tmp_path / "missing-seed"
    empty_repo = _write_generic_repo(tmp_path / "empty-seed")

    assert (
        main(
            [
                "project-seed-tasks",
                "--root",
                str(missing),
                "--plan-id",
                "plan-seeded-project",
            ]
        )
        == 1
    )
    assert "Project root does not exist" in capsys.readouterr().err

    assert (
        main(
            [
                "project-seed-tasks",
                "--root",
                str(empty_repo),
                "--plan-id",
                "plan-seeded-project",
            ]
        )
        == 1
    )
    assert "No project task candidates were found" in capsys.readouterr().out


def test_project_seed_tasks_cli_rejects_worker_lifecycle_statuses(
    tmp_path: Path,
    capsys,
) -> None:
    repo = _write_generic_repo(
        tmp_path / "unsafe-status-seed",
        tasks=[
            {
                "title": "Unsafe status task",
                "goal": "Demonstrate status validation.",
                "acceptance_criteria": ["Validation rejects worker lifecycle statuses."],
                "allowed_paths": ["src/status.py"],
            }
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "project-seed-tasks",
                "--root",
                str(repo),
                "--plan-id",
                "plan-seeded-project",
                "--status",
                "running",
            ]
        )
    assert exc_info.value.code == 2

    assert "invalid choice" in capsys.readouterr().err


def test_project_list_cli_prints_human_summary_with_candidate_count(
    tmp_path: Path,
    capsys,
) -> None:
    repo = _write_generic_repo(
        tmp_path / "human-summary",
        tasks=[
            {
                "title": "Document setup",
                "goal": "Document setup commands.",
                "acceptance_criteria": ["Setup docs exist."],
            }
        ],
    )

    assert main(["project-list", "--root", str(repo)]) == 0

    output = capsys.readouterr().out
    assert "human-summary-" in output
    assert "generic_repo" in output
    assert "local_trusted" in output
    assert "source_documents: AGENTS.md, PLANS.md, TESTING.md, README.md" in output
    assert "candidate_tasks: 1" in output


def test_project_list_cli_json_includes_candidate_task_output(
    tmp_path: Path,
    capsys,
) -> None:
    repo = _write_generic_repo(
        tmp_path / "json-candidates",
        tasks=[
            {
                "title": "Add docs",
                "goal": "Add docs for the queue.",
                "acceptance_criteria": ["Queue docs exist."],
                "allowed_paths": ["docs/queue.md"],
            }
        ],
    )

    assert main(["project-list", "--root", str(repo), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    candidate = payload[0]["facts"]["candidate_tasks"][0]
    assert candidate["source_id"].startswith("tasks-json-add-docs-")
    assert candidate["source_path"] == "TASKS.json"
    assert candidate["title"] == "Add docs"
    assert candidate["goal"] == "Add docs for the queue."
    assert candidate["task_type"] == "AFK"
    assert candidate["acceptance_criteria"] == ["Queue docs exist."]
    assert candidate["allowed_paths"] == ["docs/queue.md"]


def test_project_list_cli_reports_missing_roots_without_creating_files(
    tmp_path: Path,
    capsys,
) -> None:
    missing = tmp_path / "missing-project"

    assert main(["project-list", "--root", str(missing)]) == 1

    captured = capsys.readouterr()
    assert "Project root does not exist" in captured.err
    assert str(missing) in captured.err
    assert not missing.exists()


def test_stable_project_id_normalizes_windows_and_posix_paths() -> None:
    windows_a = PureWindowsPath(r"D:\Workspace\Example\Repo Name")
    windows_b = PureWindowsPath("D:/Workspace/Example/Repo Name")
    posix = PurePosixPath("/srv/example/Repo Name")

    assert stable_project_id_from_path(windows_a) == stable_project_id_from_path(windows_b)
    assert stable_project_id_from_path(windows_a).startswith("repo-name-")
    assert stable_project_id_from_path(posix).startswith("repo-name-")
    assert stable_project_id_from_path(posix) != stable_project_id_from_path(windows_a)


def _write_generic_repo(root: Path, *, tasks: list[dict[str, object]] | None = None) -> Path:
    root.mkdir()
    (root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (root / "PLANS.md").write_text("# Plans\n", encoding="utf-8")
    (root / "TESTING.md").write_text("# Testing\n", encoding="utf-8")
    (root / "README.md").write_text("# Demo\n", encoding="utf-8")
    (root / "TASKS.json").write_text(json.dumps(tasks or []) + "\n", encoding="utf-8")
    (root / "plans").mkdir()
    (root / "plans" / "planning.sqlite3").write_bytes(b"not inspected by registry")
    (root / "scripts").mkdir()
    (root / "scripts" / "verify.py").write_text("print('verify')\n", encoding="utf-8")
    (root / "scripts" / "check_protected_files.py").write_text(
        "print('locks')\n",
        encoding="utf-8",
    )
    return root


def _write_planning_sqlite_project(
    root: Path,
    *,
    task_rows: list[tuple[str, str, str, str, str, str, str, str, str]] | None = None,
) -> Path:
    (root / "plans").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "scripts" / "verify.py").write_text("print('verify')\n", encoding="utf-8")
    database_path = root / "plans" / "planning.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE tasks (
                task_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                goal TEXT NOT NULL,
                status TEXT NOT NULL,
                task_type TEXT NOT NULL,
                acceptance_criteria_json TEXT NOT NULL,
                verification_commands_json TEXT NOT NULL,
                allowed_paths_json TEXT NOT NULL,
                blocked_by_json TEXT NOT NULL
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO tasks (
                task_id, title, goal, status, task_type, acceptance_criteria_json,
                verification_commands_json, allowed_paths_json, blocked_by_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            task_rows
            or [
                (
                    "task-add-signals",
                    "Add signal feature",
                    "Add a bounded signal feature.",
                    "ready",
                    "AFK",
                    json.dumps(["Signal feature is implemented."]),
                    json.dumps(["uv run --no-sync python -B scripts/verify.py"]),
                    json.dumps(["src/signals.py"]),
                    json.dumps(["task-data-contract"]),
                ),
                (
                    "task-already-done",
                    "Already done",
                    "This terminal task should not become a candidate.",
                    "completed",
                    "AFK",
                    json.dumps(["Done."]),
                    json.dumps(["uv run --no-sync python -B scripts/verify.py"]),
                    json.dumps(["src/done.py"]),
                    json.dumps([]),
                ),
            ],
        )
    return root


def _write_markdown_plan_project(root: Path, *, plan_text: str | None = None) -> Path:
    (root / "plans" / "active").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "scripts" / "validate_plan.py").write_text("print('validate')\n", encoding="utf-8")
    (root / "plans" / "active" / "safety-plan.md").write_text(
        plan_text
        or """<!-- observe-safety-plan -->
Plan Status: active

# Safety Plan

## Task: Add guardrails
ID: add-guardrails
Status: ready
Type: AFK
Goal: Add bounded guardrails.

### Acceptance Criteria
- Guardrails are implemented.

### Verification Commands
- uv run --no-sync python -B scripts/validate_plan.py

### Allowed Paths
- src/guardrails.py

### Blocked By
- task-data-contract
""",
        encoding="utf-8",
    )
    return root


def _write_harness_config_project(
    root: Path,
    *,
    config_payload: dict[str, object] | None = None,
    prompt_text: str | None = None,
) -> Path:
    (root / "harness").mkdir(parents=True)
    (root / "prompts").mkdir()
    (root / "scripts").mkdir()
    (root / "scripts" / "run_harness.py").write_text("print('run harness')\n", encoding="utf-8")
    (root / "prompts" / "browser-smoke.md").write_text(
        prompt_text or "Run the browser smoke harness.\n",
        encoding="utf-8",
    )
    (root / "harness" / "config.json").write_text(
        json.dumps(
            config_payload
            or {
                "schema": "codex-subagent-testing",
                "runs": [
                    {
                        "id": "browser-smoke",
                        "title": "Run browser smoke",
                        "goal": "Exercise the browser harness prompt.",
                        "status": "ready",
                        "task_type": "AFK",
                        "prompt_path": "prompts/browser-smoke.md",
                        "acceptance_criteria": ["Harness smoke completes."],
                        "verification_commands": [
                            "uv run --no-sync python -B scripts/run_harness.py"
                        ],
                        "allowed_paths": ["harness/browser.py"],
                        "blocked_by": ["task-fixture-data"],
                    },
                    {
                        "id": "completed-run",
                        "title": "Completed harness run",
                        "goal": "This terminal run should not become a candidate.",
                        "status": "completed",
                        "task_type": "AFK",
                        "prompt_path": "prompts/browser-smoke.md",
                        "acceptance_criteria": ["Done."],
                        "verification_commands": [
                            "uv run --no-sync python -B scripts/run_harness.py"
                        ],
                        "allowed_paths": ["harness/done.py"],
                        "blocked_by": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return root
