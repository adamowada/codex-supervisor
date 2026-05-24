from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_supervisor.cli import main
from codex_supervisor.worktree_artifacts import WorktreeArtifactError
from codex_supervisor.worktree_cleanup import plan_cleanup_targets


def test_plan_cleanup_targets_selects_safe_orphan_runtime_directories(tmp_path: Path) -> None:
    candidates = (
        tmp_path / "worktrees" / "run-old",
        tmp_path / "runs" / "run-old",
        tmp_path / "artifacts" / "run-old",
        tmp_path / "logs" / "run-old",
    )
    for candidate in candidates:
        candidate.mkdir(parents=True)

    plan = plan_cleanup_targets(
        workspace_root=tmp_path,
        candidate_paths=candidates,
        active_worker_run_ids=("run-active",),
        reason="orphaned_worker_run",
    )

    assert plan.workspace_root == str(tmp_path.resolve())
    assert len(plan.selected_entries) == 4
    assert plan.skipped_entries == ()
    assert [entry.runtime_kind for entry in plan.selected_entries] == [
        "worktrees",
        "runs",
        "artifacts",
        "logs",
    ]
    assert {entry.worker_run_id for entry in plan.selected_entries} == {"run-old"}
    assert {entry.operation for entry in plan.selected_entries} == {"delete_tree"}
    assert {entry.reason for entry in plan.selected_entries} == {"orphaned_worker_run"}
    assert all(candidate.exists() for candidate in candidates)


@pytest.mark.parametrize(
    "candidate",
    [
        ".",
        "../outside",
    ],
)
def test_plan_cleanup_targets_rejects_root_or_outside_paths(
    tmp_path: Path,
    candidate: str,
) -> None:
    with pytest.raises(WorktreeArtifactError):
        plan_cleanup_targets(
            workspace_root=tmp_path,
            candidate_paths=(candidate,),
        )


def test_plan_cleanup_targets_preserves_active_worker_runs(tmp_path: Path) -> None:
    active_worktree = tmp_path / "worktrees" / "run-active"
    active_run = tmp_path / "runs" / "run-active"
    active_worktree.mkdir(parents=True)
    active_run.mkdir(parents=True)

    plan = plan_cleanup_targets(
        workspace_root=tmp_path,
        candidate_paths=(active_worktree, active_run),
        active_worker_run_ids=("run-active",),
    )

    assert plan.selected_entries == ()
    assert len(plan.skipped_entries) == 2
    assert {entry.skip_reason for entry in plan.skipped_entries} == {"active_worker_run"}
    assert {entry.operation for entry in plan.skipped_entries} == {None}
    assert active_worktree.exists()
    assert active_run.exists()


def test_plan_cleanup_targets_skips_unsupported_runtime_paths(tmp_path: Path) -> None:
    unsupported = tmp_path / "tmp" / "run-old"
    missing_worker_run_id = tmp_path / "runs"
    unsupported.mkdir(parents=True)
    missing_worker_run_id.mkdir()

    plan = plan_cleanup_targets(
        workspace_root=tmp_path,
        candidate_paths=(unsupported, missing_worker_run_id),
    )

    assert plan.selected_entries == ()
    assert [(entry.repo_relative_path, entry.skip_reason) for entry in plan.skipped_entries] == [
        ("tmp/run-old", "unsupported_runtime_path"),
        ("runs", "missing_worker_run_id"),
    ]
    assert unsupported.exists()
    assert missing_worker_run_id.exists()


def test_cleanup_plan_cli_outputs_json_and_preserves_candidate_directories(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    orphan = tmp_path / "worktrees" / "run-old"
    active = tmp_path / "runs" / "run-active"
    orphan.mkdir(parents=True)
    active.mkdir(parents=True)

    exit_code = main(
        [
            "cleanup-plan",
            "--workspace-root",
            str(tmp_path),
            "--candidate",
            str(orphan),
            "--candidate",
            str(active),
            "--active-worker-run-id",
            "run-active",
            "--reason",
            "orphaned_worker_run",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert payload["entries"][0]["selected"] is True
    assert payload["entries"][0]["repo_relative_path"] == "worktrees/run-old"
    assert payload["entries"][0]["operation"] == "delete_tree"
    assert payload["entries"][1]["selected"] is False
    assert payload["entries"][1]["skip_reason"] == "active_worker_run"
    assert orphan.exists()
    assert active.exists()


def test_cleanup_plan_cli_human_output_has_no_executable_delete_command(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    orphan = tmp_path / "artifacts" / "run-old"
    skipped = tmp_path / "tmp" / "run-old"
    orphan.mkdir(parents=True)
    skipped.mkdir(parents=True)

    exit_code = main(
        [
            "cleanup-plan",
            "--workspace-root",
            str(tmp_path),
            "--candidate",
            str(orphan),
            "--candidate",
            str(skipped),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "selected:" in captured.out
    assert "skipped:" in captured.out
    assert "artifacts/run-old" in captured.out
    assert "tmp/run-old" in captured.out
    assert "Remove-Item" not in captured.out
    assert "rm " not in captured.out
    assert orphan.exists()
    assert skipped.exists()


def test_cleanup_plan_cli_rejects_invalid_candidate(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    outside = tmp_path.parent / "outside"

    exit_code = main(
        [
            "cleanup-plan",
            "--workspace-root",
            str(tmp_path),
            "--candidate",
            str(outside),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "cleanup-plan failed:" in captured.err
