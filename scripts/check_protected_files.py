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
    "README.md": "cdc47d2d2ac1346eab855d2fa1ea7cf98b462d3b284d739919c5ac584f47b7c6",
    "AGENTS.md": "826033261b06d875f0fc264a92af3c5fe089d3cb81b6c85052e2c4bc673b57be",
    "SUBSTRATE_PLAN.md": "09e32baef0c2b2046ca04791cba5a80fddc9721dc5b728c02f2244973eee79f1",
    "PLANS.md": "f8aca9705447a703c32926a7e8be8ae66184b51209009e858867e39f187d30be",
    "ARCHITECTURE.md": "16f3e486b21f7bf6c75587eba779b25691afd73cf775778031f27cf63a18da37",
    "CONTRACTS.md": "70542552a81a5f434fdf532cd2f2536e67fcddfe7113eacd1afa318990c090e5",
    "ROADMAP.md": "3b7575e13115fd11eef43378a9868ff2f8d5e4dc67a32a81b39703f6ddfc38cf",
    "SOP.md": "ff5a50b4fc89ebd463018abbb8afbdf1a021dd7a55082922b656ce4dd70cc85f",
    "TESTING.md": "543cfd75f32682327bc568bfd059c590b2ef8ad47f17a93f5cc8846db27ce866",
    "DECISIONS.md": "25e58011416ed7a1919d976d31f9a876d3bedd94522238cec084471ebbb747fa",
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
