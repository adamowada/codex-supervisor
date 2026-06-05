"""Target workspace inspection and product provenance helpers."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path

SUPERVISOR_DIR = ".codex-supervisor"
SUPERVISOR_IGNORE_ENTRY = ".codex-supervisor/"


@dataclass(frozen=True)
class LinkedWorktreeChanges:
    """Product changes found in one linked git worktree."""

    worktree: Path
    product_paths: tuple[str, ...]


def is_git_worktree(workspace: Path) -> bool:
    """Return whether the workspace is inside a git worktree."""

    completed = run_git(workspace, "rev-parse", "--is-inside-work-tree")
    return completed is not None and completed.returncode == 0


def tracked_supervisor_paths(workspace: Path) -> tuple[str, ...]:
    """Return tracked `.codex-supervisor` paths for a git workspace."""

    completed = run_git(workspace, "ls-files", "-z", "--", SUPERVISOR_DIR)
    if completed is None or completed.returncode != 0:
        return ()
    return tuple(
        item.replace("\\", "/")
        for item in completed.stdout.split("\0")
        if item
    )


def git_check_ignore(workspace: Path, path: Path) -> bool:
    """Return whether git ignores a path relative to the workspace."""

    try:
        candidate = path.relative_to(workspace).as_posix()
    except ValueError:
        candidate = str(path)
    completed = run_git(workspace, "check-ignore", "-q", "--", candidate)
    return completed is not None and completed.returncode == 0


def changed_product_paths(workspace: Path) -> tuple[str, ...]:
    """Return changed product paths from git status, excluding supervisor state."""

    completed = run_git(
        workspace,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    if completed is None or completed.returncode != 0:
        return ()
    return product_paths_from_porcelain_z(completed.stdout)


def product_paths_from_porcelain_z(output: str) -> tuple[str, ...]:
    """Parse `git status --porcelain=v1 -z` output into product paths."""

    paths: list[str] = []
    entries = [entry for entry in output.split("\0") if entry]
    index = 0
    while index < len(entries):
        entry = entries[index]
        status = entry[:2]
        raw_path = entry[3:] if len(entry) > 3 else ""
        if "R" in status or "C" in status:
            index += 1
            if index < len(entries):
                raw_path = entries[index]
        index += 1
        normalized = normalize_relative_path(raw_path)
        if is_product_path(normalized):
            paths.append(normalized)
    return tuple(sorted(set(paths)))


def worker_backed_product_paths(
    workspace: Path,
    *,
    database_path: Path,
) -> tuple[str, ...]:
    """Return product paths backed by succeeded `attempt-run` metadata."""

    if not database_path.exists():
        return ()
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """select evidence_bundles.artifacts_json, attempts.attempt_id
               from evidence_bundles
               join attempts on attempts.attempt_id = evidence_bundles.attempt_id
               where attempts.status = 'succeeded'"""
        ).fetchall()

    paths: set[str] = set()
    for artifacts_json, attempt_id in rows:
        artifacts = json_string_array_or_empty(artifacts_json)
        if not has_attempt_run_metadata(
            workspace,
            attempt_id=str(attempt_id),
            artifacts=artifacts,
        ):
            continue
        for artifact in artifacts:
            normalized = artifact_to_workspace_relative(workspace, artifact)
            if normalized is not None and is_product_path(normalized):
                paths.add(normalized)
    return tuple(sorted(paths))


def linked_worktree_changes(workspace: Path) -> tuple[LinkedWorktreeChanges, ...]:
    """Return product changes from linked worktrees outside the root workspace."""

    changes: list[LinkedWorktreeChanges] = []
    for worktree in linked_worktrees(workspace):
        product_paths = changed_product_paths(worktree)
        if product_paths:
            changes.append(
                LinkedWorktreeChanges(
                    worktree=worktree,
                    product_paths=product_paths,
                )
            )
    return tuple(changes)


def linked_worktrees(workspace: Path) -> tuple[Path, ...]:
    """Return linked git worktrees for the same repository, excluding the root."""

    completed = run_git(workspace, "worktree", "list", "--porcelain")
    if completed is None or completed.returncode != 0:
        return ()
    root = workspace.resolve()
    paths: list[Path] = []
    for line in completed.stdout.splitlines():
        if not line.startswith("worktree "):
            continue
        path = Path(line.removeprefix("worktree ")).resolve()
        if path != root:
            paths.append(path)
    return tuple(paths)


def has_attempt_run_metadata(
    workspace: Path,
    *,
    attempt_id: str,
    artifacts: tuple[str, ...],
) -> bool:
    """Return whether artifacts include the metadata emitted by `attempt-run`."""

    required = {
        f"{SUPERVISOR_DIR}/evidence/{attempt_id}-assignment.json",
        f"{SUPERVISOR_DIR}/evidence/{attempt_id}-command.json",
    }
    normalized_artifacts = {
        normalized
        for artifact in artifacts
        if (normalized := artifact_to_workspace_relative(workspace, artifact)) is not None
    }
    return required.issubset(normalized_artifacts)


def artifact_to_workspace_relative(workspace: Path, artifact: str) -> str | None:
    """Return an artifact path relative to the workspace when possible."""

    artifact_path = Path(artifact)
    if artifact_path.is_absolute():
        try:
            relative = artifact_path.resolve().relative_to(workspace)
        except ValueError:
            return None
        return relative.as_posix()
    return normalize_relative_path(artifact)


def is_product_path(relative_path: str) -> bool:
    """Return whether a relative path is product state, not supervisor state."""

    return bool(relative_path) and relative_path != ".gitignore" and not (
        relative_path == SUPERVISOR_DIR or relative_path.startswith(f"{SUPERVISOR_DIR}/")
    )


def normalize_relative_path(path: str) -> str:
    """Normalize a git/workspace path for product-provenance comparison."""

    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def json_string_array_or_empty(raw_json: str) -> tuple[str, ...]:
    """Parse a JSON string array, returning empty for malformed evidence."""

    try:
        values = json.loads(raw_json)
    except json.JSONDecodeError:
        return ()
    if not isinstance(values, list):
        return ()
    return tuple(value for value in values if isinstance(value, str))


def run_git(workspace: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    """Run git in a workspace and return text output."""

    try:
        return subprocess.run(
            ("git", "-C", str(workspace), *args),
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
    except FileNotFoundError:
        return None
