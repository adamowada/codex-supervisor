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
    "README.md": "9476f7dbf4f329831acf06177f008e99ada94553b8ac7eb4e67c20cdb938ff94",
    "AGENTS.md": "0d5d5c0b956a6355e32bea9c2ba53bae2bc7459ba5df94729849739bd2e644ef",
    "PLANS.md": "54c20c9d48ba6ac4557cdaef4c7968f6f8d5e4252bb268c2a28f2d4e46563eb6",
    "ARCHITECTURE.md": "6c7da679486f0cd8153fbaa2def4a42395ac9f55f9d62fff6c7f9737f771ef35",
    "CONTRACTS.md": "8844e7311a69cba842ef2358cee8ede8e77830584fd64229746a8f397330ea39",
    "ROADMAP.md": "4f0087a590a1f9207a0d15d6628b76827b9a322e23f679275bb8103e93810b7a",
    "SOP.md": "8ab599fff8ab0544c4c86b9161df43dbd7b2d4ed2c3691f0b4dcbe241720b087",
    "TESTING.md": "169e8fd1df3edcd94ce2b4dba10daeaff4f43bcdc36952d280511436da71184e",
    "DECISIONS.md": "5b97be1a273f7ed0b66c251b0b5fa18b13f100205942cd5d8d06f3d6bd998896",
    "LICENSE": "17399c1f99877b3e7b981b714cda5954cfac88075d7243b846b101608b86fbba",
    "ATTRIBUTIONS.md": "d8b621138a595675048bdece0d0baa8aaa1dac288f1e74536595aea680261bf1",
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
