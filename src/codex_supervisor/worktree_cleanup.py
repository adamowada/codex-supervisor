"""Non-destructive cleanup planning for worker runtime paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codex_supervisor.worktree_artifacts import (
    IGNORED_RUNTIME_ROOTS,
    validate_cleanup_target,
)


@dataclass(frozen=True)
class CleanupPlanEntry:
    """One validated cleanup candidate and its non-destructive plan decision."""

    requested_path: str
    repo_relative_path: str
    resolved_path: str
    runtime_kind: str | None
    worker_run_id: str | None
    reason: str
    operation: str | None
    selected: bool
    skip_reason: str | None = None


@dataclass(frozen=True)
class CleanupPlan:
    """A non-destructive cleanup plan for ignored worker runtime outputs."""

    workspace_root: str
    entries: tuple[CleanupPlanEntry, ...]

    @property
    def selected_entries(self) -> tuple[CleanupPlanEntry, ...]:
        """Return cleanup entries that a future deletion command may consume."""

        return tuple(entry for entry in self.entries if entry.selected)

    @property
    def skipped_entries(self) -> tuple[CleanupPlanEntry, ...]:
        """Return cleanup entries skipped by runtime or active-run guards."""

        return tuple(entry for entry in self.entries if not entry.selected)


def plan_cleanup_targets(
    *,
    workspace_root: Path,
    candidate_paths: tuple[Path | str, ...],
    active_worker_run_ids: tuple[str, ...] = (),
    reason: str = "orphaned_runtime_path",
) -> CleanupPlan:
    """Build a structured cleanup plan without deleting files or running git."""

    root = workspace_root.resolve()
    active_ids = frozenset(active_worker_run_ids)
    entries = tuple(
        _cleanup_entry(
            workspace_root=root,
            candidate_path=candidate_path,
            active_worker_run_ids=active_ids,
            reason=reason,
        )
        for candidate_path in candidate_paths
    )
    return CleanupPlan(
        workspace_root=str(root),
        entries=entries,
    )


def _cleanup_entry(
    *,
    workspace_root: Path,
    candidate_path: Path | str,
    active_worker_run_ids: frozenset[str],
    reason: str,
) -> CleanupPlanEntry:
    target = validate_cleanup_target(workspace_root, candidate_path)
    relative_path = target.relative_to(workspace_root).as_posix()
    runtime_kind, worker_run_id, skip_reason = _classify_runtime_path(relative_path)
    if worker_run_id in active_worker_run_ids:
        skip_reason = "active_worker_run"
    selected = skip_reason is None
    return CleanupPlanEntry(
        requested_path=str(candidate_path),
        repo_relative_path=relative_path,
        resolved_path=str(target),
        runtime_kind=runtime_kind,
        worker_run_id=worker_run_id,
        reason=reason,
        operation="delete_tree" if selected else None,
        selected=selected,
        skip_reason=skip_reason,
    )


def _classify_runtime_path(relative_path: str) -> tuple[str | None, str | None, str | None]:
    parts = relative_path.replace("\\", "/").split("/")
    runtime_kind = parts[0] if parts else ""
    if runtime_kind not in IGNORED_RUNTIME_ROOTS:
        return None, None, "unsupported_runtime_path"
    if len(parts) < 2 or not parts[1].strip():
        return runtime_kind, None, "missing_worker_run_id"
    return runtime_kind, parts[1], None
