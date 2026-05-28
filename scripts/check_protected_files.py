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
    ".gitignore": "e67254cca067cb65c4b691c33416e23f9ab245c25e8528593df7459993c70abb",
    ".gitattributes": "287b668a5753e463f837a21c0cd062f3722e45a4ad89cc9075041bfd12d3f0ae",
    "README.md": "69ad5e26b1af077f4d98c6162c8b3c26da87e25931500e367c9227ba523aad86",
    "AGENTS.md": "a1ebda12ce70523ab56c15e20872d77eea52459cc3f72a8df3f1b74191a4fe3d",
    "PLANS.md": "7b72c0fb47a19dc3f2b73556e7361b8150baee4d180865934b5c3359c7b09062",
    "ARCHITECTURE.md": "1fc50f17f21f120ef76bf656c7082d536d3b8da4fdac7b6ab21d241c856ccdf6",
    "CONTRACTS.md": "e23276c657a54a4f15ea20a99db6c24493de352549ef19c01cf00870deef4159",
    "ROADMAP.md": "1ad3aadcda464e1fa6ef833b155c82a01a982911ec8f1567b6d8f0e55143c14c",
    "SOP.md": "2bb4870e29b183e2dd3ed80fbcaf3795588da5c0c116081b4e4d6c2e8204ab84",
    "TESTING.md": "c21a30c5e10e611529308c20834f427a8d516749d93e21e69c13ce6d076edd01",
    "DECISIONS.md": "e0e45f2a14d19653115eecb6fe13996a08b8e4b8244486b014283c75d83cd243",
    "LICENSE": "17399c1f99877b3e7b981b714cda5954cfac88075d7243b846b101608b86fbba",
    "ATTRIBUTIONS.md": "bbc5a6138252f34a35221eb90b22a9c915f8f3a909d9cad48657ceaafc7f01dc",
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
