"""ACP guardrails for target workspaces."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path

from codex_supervisor.workspace_hygiene import SUPERVISOR_DIR


@dataclass(frozen=True)
class AcpGateResult:
    """Result of checking whether a target workspace is ready for ACP."""

    ok: bool
    failures: tuple[str, ...]
    changed_product_paths: tuple[str, ...]
    worker_backed_paths: tuple[str, ...]


def check_target_workspace_acp_gate(
    workspace: Path,
    *,
    database_path: Path | None = None,
) -> AcpGateResult:
    """Check target-workspace ACP rules without mutating the workspace."""

    workspace = workspace.resolve()
    database_path = (database_path or workspace / SUPERVISOR_DIR / "planning.sqlite3").resolve()
    failures: list[str] = []

    if not _is_git_worktree(workspace):
        failures.append("workspace is not a git worktree")
        return AcpGateResult(
            ok=False,
            failures=tuple(failures),
            changed_product_paths=(),
            worker_backed_paths=(),
        )

    ignored = _git_check_ignore(workspace, workspace / SUPERVISOR_DIR / "planning.sqlite3")
    if not ignored:
        failures.append(".codex-supervisor/planning.sqlite3 is not ignored by git")

    tracked_supervisor = _git_output(workspace, "ls-files", "--", SUPERVISOR_DIR)
    if tracked_supervisor.strip():
        failures.append(".codex-supervisor has tracked paths: " + tracked_supervisor.strip())

    changed_product_paths = _changed_product_paths(workspace)
    worker_backed_paths = _worker_backed_product_artifacts(
        workspace,
        database_path=database_path,
    )
    missing_evidence = tuple(
        path for path in changed_product_paths if path not in set(worker_backed_paths)
    )
    if missing_evidence:
        failures.append(
            "product paths lack attempt-run worker evidence: " + ", ".join(missing_evidence)
        )

    return AcpGateResult(
        ok=not failures,
        failures=tuple(failures),
        changed_product_paths=changed_product_paths,
        worker_backed_paths=worker_backed_paths,
    )


def _changed_product_paths(workspace: Path) -> tuple[str, ...]:
    output = _git_output(workspace, "status", "--porcelain=v1", "-z")
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
        normalized = _normalize_relative_path(raw_path)
        if _is_product_path(normalized):
            paths.append(normalized)
    return tuple(sorted(set(paths)))


def _worker_backed_product_artifacts(
    workspace: Path,
    *,
    database_path: Path,
) -> tuple[str, ...]:
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
        artifacts = _json_string_array(artifacts_json)
        if not _has_attempt_run_metadata(workspace, attempt_id=str(attempt_id), artifacts=artifacts):
            continue
        for artifact in artifacts:
            normalized = _artifact_to_workspace_relative(workspace, artifact)
            if normalized is not None and _is_product_path(normalized):
                paths.add(normalized)
    return tuple(sorted(paths))


def _has_attempt_run_metadata(
    workspace: Path,
    *,
    attempt_id: str,
    artifacts: tuple[str, ...],
) -> bool:
    required = {
        f"{SUPERVISOR_DIR}/evidence/{attempt_id}-assignment.json",
        f"{SUPERVISOR_DIR}/evidence/{attempt_id}-command.json",
    }
    normalized_artifacts = {
        normalized
        for artifact in artifacts
        if (normalized := _artifact_to_workspace_relative(workspace, artifact)) is not None
    }
    return required.issubset(normalized_artifacts)


def _artifact_to_workspace_relative(workspace: Path, artifact: str) -> str | None:
    artifact_path = Path(artifact)
    if artifact_path.is_absolute():
        try:
            relative = artifact_path.resolve().relative_to(workspace)
        except ValueError:
            return None
        return relative.as_posix()
    return _normalize_relative_path(artifact)


def _json_string_array(raw_json: str) -> tuple[str, ...]:
    try:
        values = json.loads(raw_json)
    except json.JSONDecodeError:
        return ()
    if not isinstance(values, list):
        return ()
    return tuple(value for value in values if isinstance(value, str))


def _is_product_path(relative_path: str) -> bool:
    return bool(relative_path) and relative_path != ".gitignore" and not (
        relative_path == SUPERVISOR_DIR or relative_path.startswith(f"{SUPERVISOR_DIR}/")
    )


def _normalize_relative_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _is_git_worktree(workspace: Path) -> bool:
    completed = _run_git(workspace, "rev-parse", "--is-inside-work-tree")
    return completed.returncode == 0


def _git_check_ignore(workspace: Path, path: Path) -> bool:
    try:
        candidate = path.relative_to(workspace).as_posix()
    except ValueError:
        candidate = str(path)
    return _run_git(workspace, "check-ignore", "-q", "--", candidate).returncode == 0


def _git_output(workspace: Path, *args: str) -> str:
    return _run_git(workspace, *args).stdout


def _run_git(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", str(workspace), *args),
        check=False,
        text=True,
        capture_output=True,
    )
