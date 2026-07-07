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
    "README.md": "bee74f588489db64a026ed3c69d20d7f8dbce2c6896df66d6f15ae8af9cd77ae",
    "AGENTS.md": "826033261b06d875f0fc264a92af3c5fe089d3cb81b6c85052e2c4bc673b57be",
    "SUBSTRATE_PLAN.md": "ca7e59258fe8879a90d614d46089d3541e8cdf025be6824cb0d1b9b5251b1f94",
    "PLANS.md": "776d64e44b2fbce5b010d455eacaa0c08c3e162a06d3f730bb8b93061493284e",
    "ARCHITECTURE.md": "bd03e1bd2477fd39214a2c770c4102adc651e20d06e85a499323e2429aa54378",
    "CONTRACTS.md": "c4cd19d972dda9b016ad3cedde833b90155a505d96aeab35444b02773feaf50f",
    "ROADMAP.md": "a5acdf4114f5fc9a5176797803143e62f18a4492acee9b4c47739139e42c01dd",
    "SOP.md": "ff5a50b4fc89ebd463018abbb8afbdf1a021dd7a55082922b656ce4dd70cc85f",
    "TESTING.md": "faf8f7f83033d1272f3756316854b7f838cd5bc2c940d814266f2b877fba6579",
    "DECISIONS.md": "83d41f7d139d86f37402d6640dd257345ee32b5420ca9689f6eb0f0ab126d39f",
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
