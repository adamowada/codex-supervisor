from __future__ import annotations

from pathlib import Path

import pytest

from codex_supervisor.worker_backends import CommandExecutionResult
from codex_supervisor.worktree_artifacts import WorktreeArtifactError
from codex_supervisor.worktree_state import inspect_worktree_state


def test_inspect_worktree_state_captures_clean_branch_and_diff_summary(tmp_path: Path) -> None:
    calls: list[tuple[tuple[str, ...], Path, dict[str, str]]] = []
    responses = {
        ("git", "rev-parse", "--abbrev-ref", "HEAD"): CommandExecutionResult(
            exit_code=0,
            stdout="feature/stage7d\n",
        ),
        ("git", "rev-parse", "main"): CommandExecutionResult(
            exit_code=0,
            stdout="abc123\n",
        ),
        ("git", "rev-parse", "HEAD"): CommandExecutionResult(
            exit_code=0,
            stdout="def456\n",
        ),
        ("git", "status", "--porcelain=v1"): CommandExecutionResult(exit_code=0),
        ("git", "diff", "--name-only", "abc123...def456"): CommandExecutionResult(
            exit_code=0,
            stdout="src/codex_supervisor/worktree_state.py\n",
        ),
    }

    def runner(
        argv: tuple[str, ...],
        cwd: Path,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        calls.append((argv, cwd, environment))
        return responses[argv]

    snapshot = inspect_worktree_state(
        workspace_root=tmp_path,
        worktree_path="worktrees/run-stage7d",
        allowed_paths=("src/codex_supervisor/worktree_state.py",),
        command_runner=runner,
        base_ref="main",
        environment={"GIT_OPTIONAL_LOCKS": "0"},
    )

    assert snapshot.status == "completed"
    assert snapshot.worktree_path == "worktrees/run-stage7d"
    assert snapshot.branch == "feature/stage7d"
    assert snapshot.base_commit == "abc123"
    assert snapshot.head_commit == "def456"
    assert snapshot.dirty is False
    assert snapshot.changed_files == ("src/codex_supervisor/worktree_state.py",)
    assert snapshot.diff_summary == "src/codex_supervisor/worktree_state.py\n"
    assert snapshot.changed_path_violations == ()
    assert [command.name for command in snapshot.commands] == [
        "branch",
        "base_commit",
        "head_commit",
        "status",
        "diff_summary",
    ]
    assert calls[0] == (
        ("git", "rev-parse", "--abbrev-ref", "HEAD"),
        tmp_path / "worktrees" / "run-stage7d",
        {"GIT_OPTIONAL_LOCKS": "0"},
    )
    assert not (tmp_path / "worktrees").exists()
    assert all("worktree" not in argv for argv, _, _ in calls)


def test_inspect_worktree_state_reports_dirty_out_of_scope_changes(tmp_path: Path) -> None:
    responses = {
        ("git", "rev-parse", "--abbrev-ref", "HEAD"): CommandExecutionResult(
            exit_code=0,
            stdout="feature/stage7d\n",
        ),
        ("git", "rev-parse", "origin/main"): CommandExecutionResult(
            exit_code=0,
            stdout="abc123\n",
        ),
        ("git", "rev-parse", "HEAD"): CommandExecutionResult(
            exit_code=0,
            stdout="def456\n",
        ),
        ("git", "status", "--porcelain=v1"): CommandExecutionResult(
            exit_code=0,
            stdout=" M README.md\n?? src/codex_supervisor/worktree_state.py\n",
        ),
        ("git", "diff", "--name-only", "abc123...def456"): CommandExecutionResult(
            exit_code=0,
            stdout="tests/test_worktree_state.py\n",
        ),
    }

    def runner(
        argv: tuple[str, ...],
        cwd: Path,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        return responses[argv]

    snapshot = inspect_worktree_state(
        workspace_root=tmp_path,
        worktree_path="worktrees/run-stage7d",
        allowed_paths=(
            "src/codex_supervisor/worktree_state.py",
            "tests/test_worktree_state.py",
        ),
        command_runner=runner,
        base_ref="origin/main",
    )

    assert snapshot.status == "completed"
    assert snapshot.dirty is True
    assert snapshot.changed_files == (
        "README.md",
        "src/codex_supervisor/worktree_state.py",
        "tests/test_worktree_state.py",
    )
    assert snapshot.changed_path_violations[0].path == "README.md"
    assert snapshot.changed_path_violations[0].reason == "outside_allowed_paths"


def test_inspect_worktree_state_classifies_git_command_failure(tmp_path: Path) -> None:
    def runner(
        argv: tuple[str, ...],
        cwd: Path,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        assert argv == ("git", "rev-parse", "--abbrev-ref", "HEAD")
        return CommandExecutionResult(exit_code=128, stderr="not a git repository\n")

    snapshot = inspect_worktree_state(
        workspace_root=tmp_path,
        worktree_path="worktrees/run-stage7d",
        allowed_paths=("src/**",),
        command_runner=runner,
    )

    assert snapshot.status == "failed"
    assert snapshot.failure_class == "worktree_state_failed"
    assert snapshot.failure_reason == "branch exited 128: not a git repository"
    assert snapshot.commands[0].name == "branch"
    assert snapshot.commands[0].stderr == "not a git repository\n"
    assert snapshot.changed_files == ()
    assert snapshot.changed_path_violations == ()


def test_inspect_worktree_state_rejects_outside_workspace_before_running_git(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, ...]] = []

    def runner(
        argv: tuple[str, ...],
        cwd: Path,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        calls.append(argv)
        return CommandExecutionResult(exit_code=0)

    with pytest.raises(WorktreeArtifactError):
        inspect_worktree_state(
            workspace_root=tmp_path,
            worktree_path=tmp_path.parent / "outside",
            allowed_paths=("src/**",),
            command_runner=runner,
        )

    assert calls == []
