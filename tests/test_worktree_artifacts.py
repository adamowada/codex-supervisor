from __future__ import annotations

import pytest

from codex_supervisor.worktree_artifacts import (
    WorktreeArtifactError,
    build_worktree_run_layout,
    is_ignored_runtime_path,
    validate_changed_files,
    validate_cleanup_target,
)


def test_build_worktree_run_layout_separates_ignored_and_durable_paths():
    layout = build_worktree_run_layout(
        "task-stage7a-worktree-layout-guards",
        "worker-run-stage7a-worktree-layout-20260524",
    )

    assert layout.worktree_path == "worktrees/worker-run-stage7a-worktree-layout-20260524"
    assert layout.run_directory == "runs/worker-run-stage7a-worktree-layout-20260524"
    assert layout.artifact_directory == "artifacts/worker-run-stage7a-worktree-layout-20260524"
    assert layout.prompt_path == "runs/worker-run-stage7a-worktree-layout-20260524/prompt.md"
    assert layout.jsonl_path == "runs/worker-run-stage7a-worktree-layout-20260524/events.jsonl"
    assert layout.raw_result_path == (
        "artifacts/worker-run-stage7a-worktree-layout-20260524/worker-result.raw.json"
    )
    assert layout.durable_result_path == (
        "worker-results/worker-run-stage7a-worktree-layout-20260524-worker-result.json"
    )
    assert all(is_ignored_runtime_path(path) for path in layout.raw_evidence_paths().values())
    assert not is_ignored_runtime_path(layout.durable_result_path)


@pytest.mark.parametrize(
    "task_id, worker_run_id",
    (
        ("", "worker-run"),
        ("../task", "worker-run"),
        ("task/name", "worker-run"),
        ("task\\name", "worker-run"),
        ("task", "C:worker-run"),
        ("task", "worker/../run"),
    ),
)
def test_build_worktree_run_layout_rejects_unsafe_identifiers(task_id, worker_run_id):
    with pytest.raises(WorktreeArtifactError):
        build_worktree_run_layout(task_id, worker_run_id)


def test_validate_cleanup_target_accepts_child_path_without_requiring_target_exists(tmp_path):
    workspace_root = tmp_path / "worktrees"
    workspace_root.mkdir()

    target = validate_cleanup_target(workspace_root, workspace_root / "run-123")

    assert target == workspace_root.resolve() / "run-123"
    assert validate_cleanup_target(workspace_root, "relative-run") == (
        workspace_root.resolve() / "relative-run"
    )


def test_validate_cleanup_target_rejects_root_outside_and_missing_workspace(tmp_path):
    workspace_root = tmp_path / "worktrees"
    workspace_root.mkdir()

    with pytest.raises(WorktreeArtifactError, match="workspace root"):
        validate_cleanup_target(workspace_root, workspace_root)
    with pytest.raises(WorktreeArtifactError, match="outside workspace root"):
        validate_cleanup_target(workspace_root, tmp_path / "outside-run")
    with pytest.raises(WorktreeArtifactError, match="does not exist"):
        validate_cleanup_target(tmp_path / "missing-worktrees", tmp_path / "missing-worktrees/run")


def test_validate_changed_files_accepts_globs_and_directory_patterns():
    violations = validate_changed_files(
        (
            "src/codex_supervisor/worktree_artifacts.py",
            "tests/test_worktree_artifacts.py",
            "worker-results/stage7a-worktree-layout-worker-result.json",
        ),
        (
            "src/**",
            "tests/test_*.py",
            "worker-results/stage7a-worktree-layout-worker-result.json",
        ),
    )

    assert violations == ()


def test_validate_changed_files_reports_unsafe_and_out_of_scope_paths():
    violations = validate_changed_files(
        (
            "src/codex_supervisor/worktree_artifacts.py",
            "README.md",
            "../secret.txt",
            "C:relative.py",
            "/absolute.py",
        ),
        ("src/**",),
    )

    assert [(violation.path, violation.reason) for violation in violations] == [
        ("README.md", "outside_allowed_paths"),
        ("../secret.txt", "unsafe_changed_file:non_normalized_or_parent"),
        ("C:relative.py", "unsafe_changed_file:drive_path"),
        ("/absolute.py", "unsafe_changed_file:absolute"),
    ]


def test_validate_changed_files_reports_unsafe_allowed_paths():
    violations = validate_changed_files(("src/app.py",), ("../src/**", "src/**"))

    assert [(violation.path, violation.reason) for violation in violations] == [
        ("../src/**", "unsafe_allowed_path:non_normalized_or_parent"),
    ]
    violations = validate_changed_files(("src/app.py",), ("../src/**",))
    assert [(violation.path, violation.reason) for violation in violations] == [
        ("../src/**", "unsafe_allowed_path:non_normalized_or_parent"),
        ("src/app.py", "outside_allowed_paths"),
    ]
