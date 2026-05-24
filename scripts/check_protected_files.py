#!/usr/bin/env python3
"""Fail if locked source-of-truth documents changed unexpectedly."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_supervisor.locks import check_protected_files  # noqa: E402

PROTECTED_FILE_HASHES = {
    "README.md": "0c36b6b2b1e899bfde8d52510fbad22614634400cd78e063b8cbf8f011b0a8b8",
    "AGENTS.md": "2c2802983acfdc3d39f22e36599dc54d2ee3c582395db55c0ab0b0ab6ee28dc8",
    "PLANS.md": "e6f80da9df510bb70d2fa075ee1d2b73e988cf332caf190d14e5df8769c43588",
    "ARCHITECTURE.md": "9ef689a77a54c7d925c69f32e0cfbb5febe3e6587be85e4508419d0f2d9da0b1",
    "CONTRACTS.md": "707dc320ee17e574cfd532f9e9593805cf4e8eceee5873d6ac5ff2cdf4b6e174",
    "ROADMAP.md": "11193f0e277821a6122fb1d5adaa675ac480a37dfd3ae42616638b726712b527",
    "SOP.md": "769ce18d4a22930199e7ece63d7987bbc96dbd38402e05ea9eca959dd9322886",
    "TESTING.md": "169e8fd1df3edcd94ce2b4dba10daeaff4f43bcdc36952d280511436da71184e",
    "DECISIONS.md": "96ca4bc8f3b40fd848f5c51fdef203cd48dea698b5199c11ccedc729b5aa4d45",
    "LICENSE": "17399c1f99877b3e7b981b714cda5954cfac88075d7243b846b101608b86fbba",
    "ATTRIBUTIONS.md": "7a425e7a9bd4e479f9e387a1a07a8088b4d83d545a39df53a512f5209196f7e9",
}


def main() -> int:
    failures = check_protected_files(REPO_ROOT, PROTECTED_FILE_HASHES)
    if failures:
        print("Protected source-of-truth files changed unexpectedly.", file=sys.stderr)
        print("", file=sys.stderr)
        for failure in failures:
            print(f"{failure.relative_path}: {failure.reason}", file=sys.stderr)
            print(f"  expected: {failure.expected_hash}", file=sys.stderr)
            print(f"  actual:   {failure.actual_hash or 'missing'}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Only update locked documents, and then this guard, intentionally.", file=sys.stderr)
        return 1
    print("Protected source-of-truth files are unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
