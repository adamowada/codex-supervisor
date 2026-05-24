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
    "README.md": "3a7fcdbf72941cfd904d7ccaa2f511e81d0537a2da27f2b2ef8ac26a70236972",
    "AGENTS.md": "adf1813264b30e36df1170174f13094662ea7bd81b3ee72f254b0f5b2d68e90c",
    "PLANS.md": "73df420899905cf0ec6a862a49a45389cba63a9c6258d597aa8651902845f882",
    "ARCHITECTURE.md": "408e738163db90158e76b16d648ab1fe199214221e2f832e0b9b59a733268caa",
    "CONTRACTS.md": "a8251b1cd6db3945cac6c1670950e2e745db895ccd42d21d8acab861262ec647",
    "ROADMAP.md": "fcb7151dfd5e1d65ee9736b76ec3c59e2aa2cbb90996bdea67499b94f6703ef3",
    "SOP.md": "5bfdf7e552e30a90917028167562479453c141b74a760cd3f88d8d28e0c0991e",
    "TESTING.md": "5ee5f0ee65370288b4f6a6989f43b026b0be22733cf3780998591624729ccf8f",
    "DECISIONS.md": "c47fc1614d5a008a96e4e6d5ab4809b2c99bcf61360ffd070d0dbeb0adc3c57f",
    "LICENSE": "17399c1f99877b3e7b981b714cda5954cfac88075d7243b846b101608b86fbba",
    "ATTRIBUTIONS.md": "de47b55f86f3d6b3484f7ffabcd04cb2bb65bd5eea0d924339e28b96b22585f9",
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
