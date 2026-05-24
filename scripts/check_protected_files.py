#!/usr/bin/env python3
"""Fail if locked source-of-truth documents changed unexpectedly."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_supervisor.locks import (  # noqa: E402
    PROTECTED_FILES,
    check_protected_files,
    untracked_protected_files,
)

PROTECTED_FILE_HASHES = {
    ".gitignore": "818040f7cd8f5bc2504d3cb8a7fbdf3c826e5c37eea6310de2c7a5abf87531ce",
    ".gitattributes": "287b668a5753e463f837a21c0cd062f3722e45a4ad89cc9075041bfd12d3f0ae",
    "README.md": "8efb2302edf45db386b0b8cc8b8a7eac7296f80fa97388a7b9c1e9bde05e4e3f",
    "AGENTS.md": "87d437a7b24a55b7d6f2dc64b032e690e859388b2b38be2229f061e387d67b25",
    "PLANS.md": "650c682502750ac578786a663ff2077e5515303ae0d52f6fa4fec7bcd6a2a97f",
    "ARCHITECTURE.md": "8818388df79f8013c19640e6eb01a4b133a9fcd715d09ce4673185f4f7d97768",
    "CONTRACTS.md": "84b0999996624824dba5a6781cf7714c6969ef1bc6a79123b28a25ea4cf78c3e",
    "ROADMAP.md": "89cfbddfb67de3966b6f051547af42302fe16244c702560963771f680de07b11",
    "SOP.md": "ac64d00b5382d416c0c9208dbded5fd6dc49fff63483eaf92fa1ce210dc70097",
    "TESTING.md": "5979ed310f71c3d6516b1f3d5284d1818a5c50cb6e1f90e0a5357a7a98d4187f",
    "DECISIONS.md": "d9b13e33ba882e1dd6618fcde56f355a333fa9f84c178a086f3d6e3c1959bad9",
    "LICENSE": "17399c1f99877b3e7b981b714cda5954cfac88075d7243b846b101608b86fbba",
    "ATTRIBUTIONS.md": "866f246b07307cbf0661c342e0d70a652821772a09297e1367fe84bc311aeceb",
}


def main() -> int:
    if tuple(PROTECTED_FILE_HASHES) != PROTECTED_FILES:
        print(
            "Protected file manifest drifted from codex_supervisor.locks.PROTECTED_FILES.",
            file=sys.stderr,
        )
        return 1
    untracked = untracked_protected_files(REPO_ROOT)
    failures = check_protected_files(REPO_ROOT, PROTECTED_FILE_HASHES)
    if untracked or failures:
        if untracked:
            print("Protected source-of-truth files are not tracked.", file=sys.stderr)
            print("", file=sys.stderr)
            for relative_path in untracked:
                print(f"{relative_path}: not tracked by git", file=sys.stderr)
            print("", file=sys.stderr)
        if failures:
            print("Protected source-of-truth files changed unexpectedly.", file=sys.stderr)
            print("", file=sys.stderr)
            for failure in failures:
                print(f"{failure.relative_path}: {failure.reason}", file=sys.stderr)
                print(f"  expected: {failure.expected_hash}", file=sys.stderr)
                print(f"  actual:   {failure.actual_hash or 'missing'}", file=sys.stderr)
            print("", file=sys.stderr)
        if untracked:
            print(
                "Add intended protected files before treating the lock check as reproducible.",
                file=sys.stderr,
            )
        if failures:
            print(
                "Only update locked documents, and then this guard, intentionally.",
                file=sys.stderr,
            )
        return 1
    print("Protected source-of-truth files are unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
