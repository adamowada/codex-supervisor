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
    "README.md": "4d9af14626014be9ce07bb76d923fb5b96b0a26b62aed0efd5e3cfd4897b66ac",
    "AGENTS.md": "438ba97ca9c9961a3dacbe05c105f2d966e9c2fd830da7ecbd86a0f7f822a5e5",
    "PLANS.md": "114693cce008f70c49408cdd7f31520bd333d945d89a92e8ef0c759b594175ce",
    "ARCHITECTURE.md": "7448f24d01327073acbe4c002372e96dcfca2de770ba709af2ab4e690b0a99bb",
    "CONTRACTS.md": "631080b73c7d3b29a47b4a2a3142bc14285387e807a6ec3c181fcf9d7f3ebf43",
    "ROADMAP.md": "10a3e8015d4daa341e30dc029a00750caab15e25ecc7d44ae83b5ebfeebaacba",
    "SOP.md": "6f100a82b105bb4d020fe1c2e160801e7d46d612d14a9468b2a6b931930b15de",
    "TESTING.md": "f5813f5f34c302551a98bbe479071bb34a07d2fb0812dee3d5faa5e2a004b692",
    "DECISIONS.md": "58b9720bcbb9b83a92e992fdf49cb4f720fdb34c1f6b19cad52cef93c1abd213",
    "LICENSE": "17399c1f99877b3e7b981b714cda5954cfac88075d7243b846b101608b86fbba",
    "ATTRIBUTIONS.md": "866f246b07307cbf0661c342e0d70a652821772a09297e1367fe84bc311aeceb",
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
