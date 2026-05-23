#!/usr/bin/env python3
"""Print the current protected-file hash mapping."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_supervisor.locks import sha256_file  # noqa: E402

PROTECTED_FILES = [
    "README.md",
    "AGENTS.md",
    "PLANS.md",
    "ARCHITECTURE.md",
    "CONTRACTS.md",
    "ROADMAP.md",
    "SOP.md",
    "TESTING.md",
    "DECISIONS.md",
    "LICENSE",
    "ATTRIBUTIONS.md",
]


def main() -> int:
    print("PROTECTED_FILE_HASHES = {")
    for relative_path in PROTECTED_FILES:
        digest = sha256_file(REPO_ROOT / relative_path)
        print(f'    "{relative_path}": "{digest}",')
    print("}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
