"""Launch the codex-supervisor CLI from a plugin install."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from mcp_launcher import SOURCE_ENV_VAR, find_repo_root


def main(argv: list[str] | None = None) -> int:
    """Resolve the source repo and forward arguments to the compact CLI."""

    plugin_root = Path(__file__).resolve().parents[1]
    repo_root = find_repo_root(plugin_root, os.environ)
    if repo_root is None:
        print(
            "Could not locate codex-supervisor source repo. "
            f"Set {SOURCE_ENV_VAR} to the repo root before running the plugin CLI launcher.",
            file=sys.stderr,
        )
        return 1

    command = (
        "uv",
        "run",
        "--no-sync",
        "python",
        "-B",
        "-m",
        "codex_supervisor.cli",
        *(argv if argv is not None else sys.argv[1:]),
    )
    try:
        completed = subprocess.run(command, cwd=repo_root, check=False)
    except FileNotFoundError:
        print("Could not start codex-supervisor CLI: uv is not on PATH.", file=sys.stderr)
        return 1
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
