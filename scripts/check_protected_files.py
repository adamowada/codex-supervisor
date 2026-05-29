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
    "README.md": "32ca58ba90eaddaecc76f5626c1932d9cfa842ebc81743c68b2a311685d2caee",
    "AGENTS.md": "ec890327d3a44a8e0d7ea1ffa1b2e5fd27a3fdb7173fb661ee22995842df7ff1",
    "PLANS.md": "9ddc7ea6458f501aee6df51b6aae52e1ccabca1e223f1ff1e4958d10c8967924",
    "ARCHITECTURE.md": "9707e4c01c459ee69ac63df8cf9af5c87f2b889ed03f50a0e5550ea84e662bd7",
    "CONTRACTS.md": "a6b06acec316d85e6906da0c7f050a3c6c39a05bc674956379a4b87d424b6ff3",
    "ROADMAP.md": "cb92dba52dc940034ca2df58a56654156acd47c46cbd794c9bd6cb3c063a67c2",
    "SOP.md": "88be150b80b4b0e6f439cfdb5be0ddc8180bceff907cf6eab4f494d1c67206ac",
    "TESTING.md": "8603c023c0416a87cbf58e75a0e33e3c300815f177af5a8b07b4dbcfd6c089e3",
    "DECISIONS.md": "3ae5f2363f939449f2995894a40fc062715fab808dee1b5760a48eeef99a1cb1",
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
