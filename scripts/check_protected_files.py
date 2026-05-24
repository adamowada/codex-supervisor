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
    "README.md": "fd646abc5470430dd3a558516c51a31916689d7f4409b16607200cce5825372f",
    "AGENTS.md": "05bef6c4197ea65c33f65cb65e235d07fc760bf00b9a2d00d8736c4dc0c29793",
    "PLANS.md": "9cc998a43371a2b1fa949a1c28ab5527513981d01d41cef6fbddff95f73b2f5d",
    "ARCHITECTURE.md": "ed26ed324351f4e5a9268ef69e78fe9947b1a5f227b45c73f3c0e87ce517a049",
    "CONTRACTS.md": "c60168f62ed47847c594a49684af60405bc9b2845753bf89cb187d63cd41c054",
    "ROADMAP.md": "0feb6a9ba6312cc6c37cf519cc75891679ece071becbcc35dccbb180fe28d9d2",
    "SOP.md": "6f91c59c9bc30e6b71bdc72ed36d5fe7c19ade91751ddff3862617e21336f23a",
    "TESTING.md": "1ef3b50238284369572054d501206540cd9a454b0c98742d23710cba9feacf31",
    "DECISIONS.md": "384c96f3fc103ae3829f986f91fe812ee9dab0fc69ee4f860dca9efd9f5228bc",
    "LICENSE": "17399c1f99877b3e7b981b714cda5954cfac88075d7243b846b101608b86fbba",
    "ATTRIBUTIONS.md": "afe221115e5a794725cf9dd7be7c0f13d795f21a60ef2d0744074a50a0218312",
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
