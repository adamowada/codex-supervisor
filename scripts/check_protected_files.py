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
    "README.md": "c38dd77d043e83b53647a8456d14b6b8e4b78f41f4b2dbb274c79f85985f4001",
    "AGENTS.md": "ad63a9041c09c01f02a3f784f8e59d0e7d1456d81075dca8fb6db4d1a3fff741",
    "PLANS.md": "12b401107306020f56d54870ad788fd3cc552eed1e38c5cde605f184b89c9c7f",
    "ARCHITECTURE.md": "bbb87e9d365307fc942dac97e50612249dd9f81c1edc96a8bd0e01611bd45619",
    "CONTRACTS.md": "80c9f54ff672cf670be1b873affa0a8d55d087b6a668cd5f2d69ada6ab6251f9",
    "ROADMAP.md": "d6ead98ae914a2cf658e54fd58ffa1f71101dd4e1b182e6080f49f2eed53fff0",
    "SOP.md": "a2e14e8d5f5e6b8813b2fb9875e05b8c7c02b5ddfca26daeb8b93e1397bd53ec",
    "TESTING.md": "96efcd7e54c36318409953ead572f687da8a044d9316e2bcd13d7a209b4d8a19",
    "DECISIONS.md": "fae093b38ddd114a0c0ddce4d4d31fdb95305639d3e7a10a7e1de26ea76ed800",
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
