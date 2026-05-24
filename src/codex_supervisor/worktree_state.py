"""Read-only worktree state snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codex_supervisor.worker_backends import CommandExecutionResult, CommandRunner
from codex_supervisor.worktree_artifacts import (
    ChangedPathViolation,
    validate_changed_files,
    validate_cleanup_target,
)


@dataclass(frozen=True)
class GitCommandEvidence:
    """One read-only git command result captured during worktree inspection."""

    name: str
    argv: tuple[str, ...]
    cwd: str
    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class WorktreeStateSnapshot:
    """Read-only snapshot of a worker worktree's git state."""

    status: str
    worktree_path: str
    branch: str | None
    base_commit: str | None
    head_commit: str | None
    dirty: bool
    changed_files: tuple[str, ...]
    diff_summary: str
    changed_path_violations: tuple[ChangedPathViolation, ...]
    commands: tuple[GitCommandEvidence, ...]
    failure_class: str | None = None
    failure_reason: str | None = None


def inspect_worktree_state(
    *,
    workspace_root: Path,
    worktree_path: Path | str,
    allowed_paths: tuple[str, ...],
    command_runner: CommandRunner,
    base_ref: str = "HEAD~1",
    git_executable: str = "git",
    environment: dict[str, str] | None = None,
) -> WorktreeStateSnapshot:
    """Inspect a worktree with read-only git commands and injected process execution."""

    target = validate_cleanup_target(workspace_root, worktree_path)
    worktree_label = _workspace_relative_path(workspace_root, target)
    environment = environment or {}
    commands: list[GitCommandEvidence] = []

    branch = _run_git(
        commands,
        command_runner,
        target,
        environment,
        git_executable,
        "branch",
        ("rev-parse", "--abbrev-ref", "HEAD"),
    )
    if branch.exit_code != 0:
        return _failed_snapshot(worktree_label, commands, branch, "branch")

    base = _run_git(
        commands,
        command_runner,
        target,
        environment,
        git_executable,
        "base_commit",
        ("rev-parse", base_ref),
    )
    if base.exit_code != 0:
        return _failed_snapshot(worktree_label, commands, base, "base_commit")

    head = _run_git(
        commands,
        command_runner,
        target,
        environment,
        git_executable,
        "head_commit",
        ("rev-parse", "HEAD"),
    )
    if head.exit_code != 0:
        return _failed_snapshot(worktree_label, commands, head, "head_commit")

    status = _run_git(
        commands,
        command_runner,
        target,
        environment,
        git_executable,
        "status",
        ("status", "--porcelain=v1"),
    )
    if status.exit_code != 0:
        return _failed_snapshot(worktree_label, commands, status, "status")

    diff = _run_git(
        commands,
        command_runner,
        target,
        environment,
        git_executable,
        "diff_summary",
        ("diff", "--name-only", f"{_single_line(base.stdout)}...{_single_line(head.stdout)}"),
    )
    if diff.exit_code != 0:
        return _failed_snapshot(worktree_label, commands, diff, "diff_summary")

    status_files = _parse_porcelain_status(status.stdout)
    diff_files = _parse_name_only(diff.stdout)
    changed_files = _ordered_unique((*status_files, *diff_files))
    violations = validate_changed_files(changed_files, allowed_paths)
    return WorktreeStateSnapshot(
        status="completed",
        worktree_path=worktree_label,
        branch=_single_line(branch.stdout),
        base_commit=_single_line(base.stdout),
        head_commit=_single_line(head.stdout),
        dirty=bool(status_files),
        changed_files=changed_files,
        diff_summary=diff.stdout,
        changed_path_violations=violations,
        commands=tuple(commands),
    )


def _run_git(
    commands: list[GitCommandEvidence],
    command_runner: CommandRunner,
    cwd: Path,
    environment: dict[str, str],
    git_executable: str,
    name: str,
    args: tuple[str, ...],
) -> CommandExecutionResult:
    argv = (git_executable, *args)
    try:
        result = command_runner(argv, cwd, environment)
    except OSError as exc:
        result = CommandExecutionResult(exit_code=1, stderr=str(exc))
    commands.append(
        GitCommandEvidence(
            name=name,
            argv=argv,
            cwd=str(cwd),
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    )
    return result


def _failed_snapshot(
    worktree_path: str,
    commands: list[GitCommandEvidence],
    result: CommandExecutionResult,
    command_name: str,
) -> WorktreeStateSnapshot:
    stderr = result.stderr.strip()
    failure_reason = f"{command_name} exited {result.exit_code}"
    if stderr:
        failure_reason = f"{failure_reason}: {stderr}"
    return WorktreeStateSnapshot(
        status="failed",
        worktree_path=worktree_path,
        branch=None,
        base_commit=None,
        head_commit=None,
        dirty=False,
        changed_files=(),
        diff_summary="",
        changed_path_violations=(),
        commands=tuple(commands),
        failure_class="worktree_state_failed",
        failure_reason=failure_reason,
    )


def _workspace_relative_path(workspace_root: Path, target: Path) -> str:
    root = workspace_root.resolve()
    return target.resolve(strict=False).relative_to(root).as_posix()


def _single_line(value: str) -> str:
    return value.strip().splitlines()[0].strip() if value.strip() else ""


def _parse_name_only(value: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in value.splitlines() if line.strip())


def _parse_porcelain_status(value: str) -> tuple[str, ...]:
    paths: list[str] = []
    for line in value.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[1].strip()
        if path:
            paths.append(path.strip('"'))
    return tuple(paths)


def _ordered_unique(paths: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        ordered.append(path)
    return tuple(ordered)
