import json

import pytest

from codex_supervisor.cli import main
from codex_supervisor.spawned_projects import (
    SpawnedProjectBrief,
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
    assert actions_by_path["sources/README.md"].tier == "source-study"
    assert any("Initialize plans/planning.sqlite3" in item for item in proposal.planning_actions)
    assert any("protected source-of-truth docs" in item for item in proposal.source_lock_actions)
    assert any("insights/" in item for item in proposal.insight_actions)
    assert any("project-specific skills" in item for item in proposal.skill_actions)
    assert any("sources/README.md" in item for item in proposal.source_study_actions)
    assert proposal.first_task.title == "Bootstrap spawned project scaffold"
    assert proposal.first_task.review_required is True
    assert proposal.first_task.allowed_paths == tuple(
        action.path for action in proposal.file_actions
    )


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
    assert payload["first_task"]["review_required"] is True
    assert payload["first_task"]["allowed_paths"] == action_paths
