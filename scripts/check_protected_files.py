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
    "README.md": "7dee93ac43db0df921464c8d3ee55719f3ce782b1b3f1f1bc908f257fae49d77",
    "AGENTS.md": "bf871a3105da2bd7cb17524a765537ebcd5a84c950f2504dd88e88efcbdab52b",
    "PLANS.md": "73df420899905cf0ec6a862a49a45389cba63a9c6258d597aa8651902845f882",
    "ARCHITECTURE.md": "408e738163db90158e76b16d648ab1fe199214221e2f832e0b9b59a733268caa",
    "CONTRACTS.md": "890e80348d483f7c30dd6d994278ec623fe8dbd777f057dadddf94f6b3724e70",
    "ROADMAP.md": "98c7e726e51e3614f3853baf087b5be7b28997cf9cefbcb70d4e414546920aa9",
    "SOP.md": "6f91c59c9bc30e6b71bdc72ed36d5fe7c19ade91751ddff3862617e21336f23a",
    "TESTING.md": "1bd64a88f613a169febb9ed9f454126cb31320e1c32c09998c038250a8a55081",
    "DECISIONS.md": "384c96f3fc103ae3829f986f91fe812ee9dab0fc69ee4f860dca9efd9f5228bc",
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
