"""ACP guardrails for target workspaces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codex_supervisor.target_workspace import (
    SUPERVISOR_DIR,
    changed_product_paths,
    git_check_ignore,
    is_git_worktree,
    linked_worktree_changes,
    tracked_supervisor_paths,
    worker_backed_product_paths,
)


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

    if not is_git_worktree(workspace):
        failures.append("workspace is not a git worktree")
        return AcpGateResult(
            ok=False,
            failures=tuple(failures),
            changed_product_paths=(),
            worker_backed_paths=(),
        )

    ignored = git_check_ignore(workspace, workspace / SUPERVISOR_DIR / "planning.sqlite3")
    if not ignored:
        failures.append(".codex-supervisor/planning.sqlite3 is not ignored by git")

    tracked_supervisor = tracked_supervisor_paths(workspace)
    if tracked_supervisor:
        failures.append(".codex-supervisor has tracked paths: " + "\n".join(tracked_supervisor))

    product_paths = changed_product_paths(workspace)
    worker_backed_paths = worker_backed_product_paths(
        workspace,
        database_path=database_path,
    )
    missing_evidence = tuple(
        path for path in product_paths if path not in set(worker_backed_paths)
    )
    if missing_evidence:
        failures.append(
            "product paths lack attempt-run worker evidence: " + ", ".join(missing_evidence)
        )
    for linked in linked_worktree_changes(workspace):
        failures.append(
            f"linked worktree has unintegrated product changes: "
            f"{linked.worktree}: {', '.join(linked.product_paths)}"
        )

    return AcpGateResult(
        ok=not failures,
        failures=tuple(failures),
        changed_product_paths=product_paths,
        worker_backed_paths=worker_backed_paths,
    )
