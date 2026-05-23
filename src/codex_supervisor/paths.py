"""Path helpers for the supervisor."""

from __future__ import annotations

from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    """Return the nearest ancestor containing a `.git` directory."""

    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    msg = f"Could not find repository root from {current}"
    raise RuntimeError(msg)


def default_planning_database_path(repo_root: Path | None = None) -> Path:
    """Return the default tracked planning database path."""

    root = repo_root or find_repo_root()
    return root / "plans" / "planning.sqlite3"
