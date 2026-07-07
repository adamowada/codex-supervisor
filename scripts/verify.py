#!/usr/bin/env python3
"""Run the simplified verification gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

COMMANDS: tuple[tuple[str, ...], ...] = (
    (sys.executable, "scripts/check_planning_integrity.py"),
    (sys.executable, "scripts/check_skill_inventory.py"),
    (sys.executable, "scripts/check_protected_files.py"),
    (sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"),
)


def main() -> int:
    for command in COMMANDS:
        print(f"+ {' '.join(command)}")
        completed = subprocess.run(command, cwd=REPO_ROOT, check=False)
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
