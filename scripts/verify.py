#!/usr/bin/env python3
"""Run the local verification suite."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
Command = tuple[str, ...]

BASE_COMMANDS: tuple[Command, ...] = (
    (sys.executable, "-m", "pytest", "-p", "no:cacheprovider"),
    (sys.executable, "-m", "ruff", "check", ".", "--no-cache"),
    (sys.executable, "-m", "ruff", "format", "--check", ".", "--no-cache"),
    (sys.executable, "-m", "mypy", "--no-incremental", "src", "scripts"),
    (sys.executable, "-m", "codex_supervisor.cli", "--help"),
    ("uv", "run", "--no-sync", "codex-supervisor", "--help"),
    (sys.executable, "scripts/check_file_justification.py"),
    (sys.executable, "scripts/check_planning_integrity.py"),
    (sys.executable, "scripts/check_skill_inventory.py"),
    (sys.executable, "scripts/check_source_inventory.py"),
    (sys.executable, "scripts/check_protected_files.py"),
    ("uv", "lock", "--check"),
)


def build_commands(*, publication_ready: bool = False) -> tuple[Command, ...]:
    hygiene_command: Command = (sys.executable, "scripts/check_public_repo_hygiene.py")
    if publication_ready:
        hygiene_command = (*hygiene_command, "--publication-ready")
    return (*BASE_COMMANDS[:7], hygiene_command, *BASE_COMMANDS[7:])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--publication-ready",
        action="store_true",
        help="Require git-index publication readiness in addition to the default local checks.",
    )
    args = parser.parse_args(argv)

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for command in build_commands(publication_ready=args.publication_ready):
        print(f"+ {' '.join(command)}")
        completed = subprocess.run(command, check=False, cwd=REPO_ROOT, env=env)
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
