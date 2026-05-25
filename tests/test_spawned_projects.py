import json

import pytest

from codex_supervisor.cli import main
from codex_supervisor.spawned_projects import (
    SpawnedProjectBrief,
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
    assert "insights/open-questions.md" in recommendation.required_files
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
