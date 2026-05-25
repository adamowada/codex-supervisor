import json
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from codex_supervisor.cli import main
from codex_supervisor.planning import PlanRecord, initialize_planning_database
from codex_supervisor.projects import (
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
