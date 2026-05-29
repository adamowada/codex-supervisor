"""Launch the codex-supervisor CLI from a plugin install."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from mcp_launcher import SOURCE_ENV_VAR, find_repo_root

WORKSPACE_DATABASE_COMMANDS = {
    "plan-init",
    "task-create",
    "queue-next",
    "attempt-transition",
    "attempt-run",
}


def main(argv: list[str] | None = None) -> int:
    """Resolve the source repo and forward arguments to the compact CLI."""

    invocation_cwd = Path.cwd().resolve()
    plugin_root = Path(__file__).resolve().parents[1]
    repo_root = find_repo_root(plugin_root, os.environ)
    if repo_root is None:
        print(
            "Could not locate codex-supervisor source repo. "
            f"Set {SOURCE_ENV_VAR} to the repo root before running the plugin CLI launcher.",
            file=sys.stderr,
        )
        return 1

    cli_args = _with_workspace_database_default(
        argv if argv is not None else sys.argv[1:],
        invocation_cwd=invocation_cwd,
    )
    command = (
        "uv",
        "run",
        "--no-sync",
        "python",
        "-B",
        "-m",
        "codex_supervisor.cli",
        *cli_args,
    )
    try:
        completed = subprocess.run(command, cwd=repo_root, check=False)
    except FileNotFoundError:
        print("Could not start codex-supervisor CLI: uv is not on PATH.", file=sys.stderr)
        return 1
    return completed.returncode


def _with_workspace_database_default(
    argv: list[str],
    *,
    invocation_cwd: Path,
) -> tuple[str, ...]:
    """Add the workspace planning DB path when a compact command omits --path."""

    if not argv:
        return ()
    command = argv[0]
    if (
        command not in WORKSPACE_DATABASE_COMMANDS
        or "--path" in argv
        or "-h" in argv
        or "--help" in argv
    ):
        return tuple(argv)
    database_path = invocation_cwd / ".codex-supervisor" / "planning.sqlite3"
    return (command, "--path", str(database_path), *argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
