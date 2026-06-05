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
    "README.md": "57c77e9bac2d09c6a4f05c4860df771a52540ed8f644afa1cfcc821cba750556",
    "AGENTS.md": "ad63a9041c09c01f02a3f784f8e59d0e7d1456d81075dca8fb6db4d1a3fff741",
    "PLANS.md": "39bbdeccf039d410f116916e63991ea1b160858c60ce934f1cdc58f24c4ae823",
    "ARCHITECTURE.md": "1fe1db51640dde85532076a0e9057a492ad3dcf88a8a216e1d111267962ad631",
    "CONTRACTS.md": "d9fd290aaf5434ecc1f8a4d4d30cab4aac1d1d94ed361b4223b8d52f9f1e3bf0",
    "ROADMAP.md": "b5d089a24695daa957eb2b8c2eabe8ce81aab098adfe3ce5eb6c8f64d4b913aa",
    "SOP.md": "7415a0623e105a8db7377a27ae8e1f166b61ed7690b9e18df27946a8ff05711c",
    "TESTING.md": "a4bdc5d4977ab40936fcf8a8be65c6eddc0c592d02b1a98c780145bd27597215",
    "DECISIONS.md": "e6b3dd9c9f118db061e238e94f271177a1c88c2251c7bc5d6a21e70b60f41b62",
    "LICENSE": "17399c1f99877b3e7b981b714cda5954cfac88075d7243b846b101608b86fbba",
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
