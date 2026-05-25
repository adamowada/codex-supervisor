from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_supervisor.cli import main
from codex_supervisor.factory_demo import (
    DEMO_PROJECT_NAME,
    DEMO_STAGE_NAMES,
    run_factory_loop_demo,
)


def test_factory_loop_demo_runs_all_stages_and_cleans_workspace(tmp_path: Path) -> None:
    report = run_factory_loop_demo(workspace_root=tmp_path)

    assert report.success is True
    assert report.release_evidence is False
    assert report.cleanup_performed is True
    assert report.workspace_retained is False
    assert tuple(stage.name for stage in report.stages) == DEMO_STAGE_NAMES
    assert {stage.status for stage in report.stages} == {"pass"}
    assert any(
        "not v1 release readiness evidence" in evidence
        for stage in report.stages
        for evidence in stage.evidence
    )
    assert not (tmp_path / DEMO_PROJECT_NAME).exists()


def test_factory_loop_demo_can_keep_workspace_for_inspection(tmp_path: Path) -> None:
    report = run_factory_loop_demo(workspace_root=tmp_path, keep_workspace=True)
    project_root = tmp_path / DEMO_PROJECT_NAME

    assert report.success is True
    assert report.cleanup_performed is False
    assert report.workspace_retained is True
    assert (
        (project_root / "README.md")
        .read_text(encoding="utf-8")
        .endswith("Deterministic local backend completed.\n")
    )
    assert (project_root / "plans" / "planning.sqlite3").exists()
    assert (project_root / "artifacts").exists()
    assert (project_root / "runs").exists()


def test_factory_loop_demo_requires_workspace_when_retaining() -> None:
    with pytest.raises(ValueError, match="requires workspace_root"):
        run_factory_loop_demo(keep_workspace=True)


def test_cli_factory_loop_demo_emits_json_and_cleans_workspace(
    capsys,
    tmp_path: Path,
) -> None:
    assert main(["factory-loop-demo", "--workspace", str(tmp_path), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)

    assert payload["success"] is True
    assert payload["release_evidence"] is False
    assert payload["project_name"] == DEMO_PROJECT_NAME
    assert payload["cleanup_performed"] is True
    assert [stage["name"] for stage in payload["stages"]] == list(DEMO_STAGE_NAMES)
    assert not (tmp_path / DEMO_PROJECT_NAME).exists()


def test_cli_factory_loop_demo_requires_workspace_when_retaining(capsys) -> None:
    assert main(["factory-loop-demo", "--keep-workspace"]) == 1

    assert "--keep-workspace requires --workspace" in capsys.readouterr().err


def test_cli_factory_loop_demo_emits_human_report(capsys, tmp_path: Path) -> None:
    assert main(["factory-loop-demo", "--workspace", str(tmp_path)]) == 0

    output = capsys.readouterr().out

    assert "success: True" in output
    assert "factory_loop_progress_recording" in output
    assert not (tmp_path / DEMO_PROJECT_NAME).exists()
