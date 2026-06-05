"""Workspace hygiene helpers for supervisor ledger bootstrap."""

from __future__ import annotations

from pathlib import Path

from codex_supervisor.target_workspace import (
    SUPERVISOR_DIR,
    SUPERVISOR_IGNORE_ENTRY,
    git_check_ignore,
    is_git_worktree,
    tracked_supervisor_paths,
)


def ensure_workspace_supervisor_ignored(database_path: Path) -> None:
    """Ensure a workspace-local supervisor ledger cannot be accidentally tracked."""

    supervisor_dir = database_path.resolve().parent
    if supervisor_dir.name != SUPERVISOR_DIR:
        return

    workspace = supervisor_dir.parent
    workspace.mkdir(parents=True, exist_ok=True)
    _ensure_gitignore_entry(workspace)

    if not is_git_worktree(workspace):
        return

    tracked = tracked_supervisor_paths(workspace)
    if tracked:
        raise ValueError(
            ".codex-supervisor is already tracked by git; remove these paths from "
            f"the index before ACP: {', '.join(tracked[:10])}"
        )

    ledger_path = supervisor_dir / "planning.sqlite3"
    if not git_check_ignore(workspace, ledger_path):
        raise ValueError(
            ".codex-supervisor/planning.sqlite3 is not ignored by git; "
            "ensure .gitignore contains .codex-supervisor/"
        )


def _ensure_gitignore_entry(workspace: Path) -> None:
    gitignore = workspace / ".gitignore"
    text = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if _already_ignores_supervisor(text):
        return

    separator = "" if not text or text.endswith(("\n", "\r")) else "\n"
    gitignore.write_text(
        f"{text}{separator}{SUPERVISOR_IGNORE_ENTRY}\n",
        encoding="utf-8",
    )


def _already_ignores_supervisor(text: str) -> bool:
    accepted = {
        ".codex-supervisor",
        ".codex-supervisor/",
        "/.codex-supervisor",
        "/.codex-supervisor/",
    }
    for raw_line in text.splitlines():
        line = raw_line.strip().replace("\\", "/")
        if not line or line.startswith("#"):
            continue
        if line in accepted:
            return True
        if line.startswith(".codex-supervisor/") or line.startswith("/.codex-supervisor/"):
            return True
    return False
