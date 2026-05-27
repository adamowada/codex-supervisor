import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from codex_supervisor.cli import main
from codex_supervisor.spawned_projects import (
    SpawnedProjectBrief,
    apply_spawned_project_scaffold,
    build_spawned_project_scaffold_proposal,
    recommend_spawned_project_scaffold,
)


def test_spawned_project_classifier_keeps_throwaway_prototype_light() -> None:
    recommendation = recommend_spawned_project_scaffold(
        SpawnedProjectBrief(name="paint spike", complexity="prototype")
    )

    assert recommendation.tiers == ("prototype-light",)
    assert recommendation.required_files == (
        "README.md",
        "AGENTS.md",
        "HANDOFF.md",
        ".gitignore",
        "scripts/verify.py",
    )
    assert "plans/planning.sqlite3" not in recommendation.required_files
    assert "multiple AFK slices" in recommendation.planning_guidance


def test_spawned_project_classifier_recommends_full_production_public_scaffold() -> None:
    recommendation = recommend_spawned_project_scaffold(
        SpawnedProjectBrief(
            name="ops platform",
            complexity="production",
            production_intended=True,
            public_or_shared=True,
            unattended_workers=True,
            durable_learning=True,
            repo_local_skills=True,
            source_study=True,
            trust_policy="controlled_runner",
        )
    )

    assert recommendation.tiers == (
        "base",
        "supervisor-managed",
        "publication-ready",
        "durable-learning",
        "skills-source-study",
    )
    assert "CONTRACTS.md" in recommendation.required_files
    assert "plans/planning.sqlite3" in recommendation.required_files
    assert "LICENSE" in recommendation.required_files
    assert "insights/graph.md" in recommendation.required_files
    assert ".agents/skills/" in recommendation.required_files
    assert "uv run --no-sync python -B scripts/check_public_repo_hygiene.py" in (
        recommendation.verification_commands
    )
    assert recommendation.warnings == ()


def test_spawned_project_classifier_keeps_durable_learning_separate_from_sources() -> None:
    recommendation = recommend_spawned_project_scaffold(
        SpawnedProjectBrief(
            name="research notebook",
            complexity="small",
            durable_learning=True,
        )
    )

    assert recommendation.tiers == ("base", "durable-learning")
    assert "insights/graph.md" in recommendation.required_files
    assert "insights/open-questions.md" not in recommendation.required_files
    assert ".agents/skills/" not in recommendation.required_files
    assert "sources/README.md" not in recommendation.required_files
    assert "uv run --no-sync python -B scripts/check_skill_inventory.py" not in (
        recommendation.verification_commands
    )
    assert "uv run --no-sync python -B scripts/check_source_inventory.py" not in (
        recommendation.verification_commands
    )


def test_spawned_project_classifier_warns_for_untrusted_full_auto() -> None:
    recommendation = recommend_spawned_project_scaffold(
        SpawnedProjectBrief(
            name="vendor audit",
            complexity="small",
            unattended_workers=True,
            trust_policy="untrusted",
        )
    )

    assert "supervisor-managed" in recommendation.tiers
    assert recommendation.warnings == (
        "Untrusted projects need isolated worktrees or controlled runners before full-auto work.",
    )


def test_spawned_project_classifier_forces_supervisor_managed_for_plugin_full_afk() -> None:
    recommendation = recommend_spawned_project_scaffold(
        SpawnedProjectBrief(
            name="plugin todo smoke",
            complexity="prototype",
            plugin_full_afk=True,
        )
    )

    assert recommendation.tiers == ("base", "supervisor-managed")
    assert "plans/planning.sqlite3" in recommendation.required_files
    assert "plugin_full_afk" in recommendation.classification_reason
    assert "Initialize planning SQLite" in recommendation.planning_guidance


def test_spawned_project_proposal_for_prototype_avoids_optional_ceremony() -> None:
    proposal = build_spawned_project_scaffold_proposal(
        SpawnedProjectBrief(name="paint spike", complexity="prototype")
    )

    assert proposal.writes_files is False
    assert [action.path for action in proposal.file_actions] == [
        "README.md",
        "AGENTS.md",
        "HANDOFF.md",
        ".gitignore",
        "scripts/verify.py",
    ]
    assert {action.tier for action in proposal.file_actions} == {"prototype-light"}
    assert proposal.planning_actions == (
        "Defer planning SQLite until the work spans multiple AFK slices.",
    )
    assert proposal.source_lock_actions == ("Skip source locks until stable protected docs exist.",)
    assert proposal.insight_actions == (
        "Keep lessons in the handoff until durable learning is needed.",
    )
    assert proposal.skill_actions == (
        "Skip repo-local skills until a repeated project workflow appears.",
    )
    assert proposal.source_study_actions == (
        "Skip source-study surfaces unless OSS/source inspiration is actually used.",
    )
    assert proposal.first_task.title == "Build first prototype slice"
    assert proposal.first_task.allowed_paths == ("README.md", "scripts/verify.py")
    assert proposal.first_task.review_required is False


def test_spawned_project_proposal_for_full_scaffold_includes_guidance() -> None:
    proposal = build_spawned_project_scaffold_proposal(
        SpawnedProjectBrief(
            name="ops platform",
            complexity="production",
            production_intended=True,
            public_or_shared=True,
            unattended_workers=True,
            durable_learning=True,
            repo_local_skills=True,
            source_study=True,
            trust_policy="controlled_runner",
        )
    )

    actions_by_path = {action.path: action for action in proposal.file_actions}

    assert proposal.writes_files is False
    assert actions_by_path["plans/planning.sqlite3"].tier == "supervisor-managed"
    assert actions_by_path["LICENSE"].tier == "publication-ready"
    assert actions_by_path["insights/graph.md"].tier == "durable-learning"
    assert actions_by_path[".agents/skills/"].tier == "repo-local-skills"
    assert actions_by_path[".agents/skills/project-bootstrap/SKILL.md"].tier == (
        "repo-local-skills"
    )
    assert actions_by_path["sources/README.md"].tier == "source-study"
    assert any("Initialize plans/planning.sqlite3" in item for item in proposal.planning_actions)
    assert any("protected source-of-truth docs" in item for item in proposal.source_lock_actions)
    assert any("insights/" in item for item in proposal.insight_actions)
    assert any("project-specific skills" in item for item in proposal.skill_actions)
    assert any("sources/README.md" in item for item in proposal.source_study_actions)
    assert proposal.first_task.title == "Bootstrap spawned project scaffold"
    assert proposal.first_task.review_required is False
    assert proposal.first_task.verification_commands == ("python -B scripts/verify.py",)
    assert ".agents/skills/**" in proposal.first_task.allowed_paths
    assert ".agents/skills/" not in proposal.first_task.allowed_paths


def test_spawned_project_apply_writes_full_supervisor_scaffold(tmp_path: Path) -> None:
    target = tmp_path / "ops-platform"

    result = apply_spawned_project_scaffold(
        SpawnedProjectBrief(
            name="ops platform",
            complexity="production",
            production_intended=True,
            public_or_shared=True,
            unattended_workers=True,
            durable_learning=True,
            trust_policy="controlled_runner",
        ),
        target_root=target,
    )

    assert result.writes_files is True
    assert result.project_root == str(target)
    assert result.created_files
    assert result.git_initialized is True
    assert result.baseline_commit_created is True
    assert result.baseline_commit_sha is not None
    for relative_path in (
        "README.md",
        "AGENTS.md",
        "PLANS.md",
        "ARCHITECTURE.md",
        "CONTRACTS.md",
        "ROADMAP.md",
        "SOP.md",
        "TESTING.md",
        "DECISIONS.md",
        "HANDOFF.md",
        "LICENSE",
        "ATTRIBUTIONS.md",
        ".gitignore",
        ".gitattributes",
        "scripts/verify.py",
        "scripts/check_protected_files.py",
        "scripts/check_planning_integrity.py",
        "scripts/check_file_justification.py",
        "scripts/check_public_repo_hygiene.py",
        "insights/README.md",
        "insights/graph.md",
        "plans/planning.sqlite3",
    ):
        assert (target / relative_path).exists(), relative_path

    readme = (target / "README.md").read_text(encoding="utf-8")
    assert "ops platform" in readme
    assert "spawned project" in readme
    assert "TODO" not in readme
    agents = (target / "AGENTS.md").read_text(encoding="utf-8")
    assert "client/**" in agents
    assert "separate review task" in agents
    assert "Post-worker browser smoke" in agents
    assert "browser_smoke_passed" in agents
    assert "JSON-heavy queue mutations" in agents
    assert "final_commit_required" in agents
    plans_text = (target / "PLANS.md").read_text(encoding="utf-8")
    assert "worker evidence manifest" in plans_text
    assert "commit link" in plans_text
    assert "promotion_completed" in plans_text
    gitignore_text = (target / ".gitignore").read_text(encoding="utf-8")
    assert "*.tsbuildinfo" in gitignore_text
    integrity_text = (target / "scripts" / "check_planning_integrity.py").read_text(
        encoding="utf-8"
    )
    assert "completed_worker_run_changed_file_outside_allowed_paths" in integrity_text
    assert "planning database requires at least one plan and one task" not in integrity_text
    license_text = (target / "LICENSE").read_text(encoding="utf-8")
    assert "Permission is hereby granted, free of charge" in license_text
    assert "THE SOFTWARE IS PROVIDED" in license_text
    public_result = {
        "created_files": result.created_files,
        "existing_files": result.existing_files,
    }
    assert "C:\\Users" not in json.dumps(public_result, sort_keys=True)

    with sqlite3.connect(target / "plans" / "planning.sqlite3") as connection:
        plan_count = connection.execute("SELECT COUNT(*) FROM plans").fetchone()[0]
        plan_status = connection.execute(
            "SELECT status FROM plans WHERE plan_id = ?",
            ("plan-ops-platform-bootstrap",),
        ).fetchone()[0]
        task_count = connection.execute("SELECT COUNT(*) FROM supervisor_tasks").fetchone()[0]
        task_status = connection.execute(
            "SELECT status FROM supervisor_tasks WHERE task_id = ?",
            ("task-ops-platform-bootstrap-scaffold",),
        ).fetchone()[0]
        worker_run = connection.execute(
            "SELECT backend, status, result_id FROM worker_runs WHERE worker_run_id = ?",
            ("run-ops-platform-scaffold-apply",),
        ).fetchone()
        result_count = connection.execute("SELECT COUNT(*) FROM worker_result_records").fetchone()[
            0
        ]
        database_text = "\n".join(connection.iterdump())
    assert plan_count == 1
    assert plan_status == "completed"
    assert task_count == 1
    assert task_status == "completed"
    assert tuple(worker_run[:2]) == ("scaffold_apply", "completed")
    assert worker_run[2]
    assert result_count == 1
    assert "C:\\Users" not in database_text
    assert str(target) not in database_text

    protected = subprocess.run(
        (sys.executable, "scripts/check_protected_files.py"),
        cwd=target,
        text=True,
        capture_output=True,
        check=False,
    )
    assert protected.returncode == 0, protected.stderr + protected.stdout
    integrity = subprocess.run(
        (sys.executable, "scripts/check_planning_integrity.py"),
        cwd=target,
        text=True,
        capture_output=True,
        check=False,
    )
    assert integrity.returncode == 0, integrity.stderr + integrity.stdout
    verify = subprocess.run(
        (sys.executable, "scripts/verify.py"),
        cwd=target,
        text=True,
        capture_output=True,
        check=False,
    )
    assert verify.returncode == 0, verify.stderr + verify.stdout
    (target / ".env").write_text("LOCAL_ONLY=true\n", encoding="utf-8")
    (target / "client").mkdir()
    (target / "client" / "tsconfig.tsbuildinfo").write_text("{}", encoding="utf-8")
    justification = subprocess.run(
        (sys.executable, "scripts/check_file_justification.py"),
        cwd=target,
        text=True,
        capture_output=True,
        check=False,
    )
    assert justification.returncode == 0, justification.stderr + justification.stdout
    git_log = subprocess.run(
        ("git", "log", "--oneline", "-1"),
        cwd=target,
        text=True,
        capture_output=True,
        check=False,
    )
    assert git_log.returncode == 0, git_log.stderr + git_log.stdout
    assert "Bootstrap supervisor-managed scaffold" in git_log.stdout


def test_spawned_project_apply_writes_usable_prototype_verify_script(tmp_path: Path) -> None:
    target = tmp_path / "prototype"

    result = apply_spawned_project_scaffold(
        SpawnedProjectBrief(name="rough draft", complexity="prototype"),
        target_root=target,
    )

    assert "scripts/check_planning_integrity.py" not in result.created_files
    verify = subprocess.run(
        (sys.executable, "scripts/verify.py"),
        cwd=target,
        text=True,
        capture_output=True,
        check=False,
    )
    assert verify.returncode == 0, verify.stderr + verify.stdout


def test_spawned_project_apply_with_repo_local_skills_writes_initial_skill(
    tmp_path: Path,
) -> None:
    target = tmp_path / "ops-platform"

    result = apply_spawned_project_scaffold(
        SpawnedProjectBrief(
            name="ops platform",
            complexity="production",
            production_intended=True,
            unattended_workers=True,
            durable_queue=True,
            repo_local_skills=True,
        ),
        target_root=target,
    )

    skill_path = target / ".agents" / "skills" / "project-bootstrap" / "SKILL.md"
    assert ".agents/skills/project-bootstrap/SKILL.md" in result.created_files
    assert skill_path.exists()
    skill_text = skill_path.read_text(encoding="utf-8")
    assert "plans/planning.sqlite3" in skill_text
    assert "browser-smoke pass/fail" in skill_text
    assert "OS-neutral promotion" in skill_text
    assert "JSON-heavy queue mutations" in skill_text
    verify = subprocess.run(
        (sys.executable, "scripts/verify.py"),
        cwd=target,
        text=True,
        capture_output=True,
        check=False,
    )
    assert verify.returncode == 0, verify.stderr + verify.stdout


def test_cli_spawned_project_apply_emits_json_and_writes_files(
    tmp_path: Path,
    capsys,
) -> None:
    target = tmp_path / "ops-platform"

    assert (
        main(
            [
                "spawned-project-apply",
                "--name",
                "ops platform",
                "--complexity",
                "production",
                "--production-intended",
                "--public-or-shared",
                "--unattended-workers",
                "--durable-learning",
                "--target-root",
                str(target),
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["writes_files"] is True
    assert payload["project_root"] == str(target)
    assert "plans/planning.sqlite3" in payload["created_files"]
    assert payload["git_initialized"] is True
    assert payload["baseline_commit_created"] is True
    assert (target / "plans" / "planning.sqlite3").exists()


def test_spawned_project_classifier_rejects_invalid_complexity() -> None:
    with pytest.raises(ValueError, match="complexity must be one of"):
        recommend_spawned_project_scaffold(
            SpawnedProjectBrief(name="demo", complexity="enterprise")
        )


def test_cli_spawned_project_classify_emits_json_for_prototype(capsys) -> None:
    assert (
        main(
            [
                "spawned-project-classify",
                "--name",
                "paint spike",
                "--complexity",
                "prototype",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)

    assert payload["project_name"] == "paint spike"
    assert payload["tiers"] == ["prototype-light"]
    assert "plans/planning.sqlite3" not in payload["required_files"]


def test_cli_spawned_project_classify_emits_supervisor_scaffold_for_plugin_full_afk(capsys) -> None:
    assert (
        main(
            [
                "spawned-project-classify",
                "--name",
                "plugin todo smoke",
                "--complexity",
                "prototype",
                "--plugin-full-afk",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)

    assert payload["tiers"] == ["base", "supervisor-managed"]
    assert "plans/planning.sqlite3" in payload["required_files"]


def test_cli_spawned_project_classify_emits_full_public_recommendation(capsys) -> None:
    assert (
        main(
            [
                "spawned-project-classify",
                "--name",
                "ops platform",
                "--complexity",
                "production",
                "--production-intended",
                "--public-or-shared",
                "--unattended-workers",
                "--durable-learning",
                "--repo-local-skills",
                "--source-study",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)

    assert payload["tiers"] == [
        "base",
        "supervisor-managed",
        "publication-ready",
        "durable-learning",
        "skills-source-study",
    ]
    assert "plans/planning.sqlite3" in payload["required_files"]
    assert "ATTRIBUTIONS.md" in payload["required_files"]


def test_cli_spawned_project_propose_emits_json(capsys) -> None:
    assert (
        main(
            [
                "spawned-project-propose",
                "--name",
                "ops platform",
                "--complexity",
                "production",
                "--production-intended",
                "--public-or-shared",
                "--unattended-workers",
                "--durable-learning",
                "--repo-local-skills",
                "--source-study",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    action_paths = [action["path"] for action in payload["file_actions"]]

    assert payload["project_name"] == "ops platform"
    assert payload["writes_files"] is False
    assert "plans/planning.sqlite3" in action_paths
    assert "sources/README.md" in action_paths
    assert any("planning.sqlite3" in item for item in payload["planning_actions"])
    assert any("protected source-of-truth docs" in item for item in payload["source_lock_actions"])
    assert any("insights/" in item for item in payload["insight_actions"])
    assert any("project-specific skills" in item for item in payload["skill_actions"])
    assert any("sources/README.md" in item for item in payload["source_study_actions"])
    assert payload["first_task"]["review_required"] is False
    assert payload["first_task"]["verification_commands"] == ["python -B scripts/verify.py"]
    assert ".agents/skills/**" in payload["first_task"]["allowed_paths"]
    assert payload["first_task"]["allowed_paths"] != action_paths
