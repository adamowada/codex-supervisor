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
    "AGENTS.md": "71e822366a524b920af9f71b6e379afa1c709d0b70c220631d97044670ecd68a",
    "PLANS.md": "9ff75bf7c214e18c887999c7f48f11474a12a5349a5a8ba18626415bdecb09f5",
    "ARCHITECTURE.md": "6b867c71e832cb1f08f02da7435b83c3e8bf41f9f60dc0c411b388f56301514e",
    "CONTRACTS.md": "6b22605fd8077b5d793a1438d7964633db0fc9a983f8e64ac2557ed17d5e073b",
    "ROADMAP.md": "754597dffbbb0aa51bb8bfa45a6112b55f1dd0ebacdbc6aadfd75d3da54cfbee",
    "SOP.md": "3919666ed5d43c99e088e672aef4c9fbd8953f684913ea1ab49dab27ee4df921",
    "TESTING.md": "169e8fd1df3edcd94ce2b4dba10daeaff4f43bcdc36952d280511436da71184e",
    "DECISIONS.md": "8959fc81fee4efe7e10d3c5f951b908e300e7675dc9d823f3455670c726d8771",
    "LICENSE": "17399c1f99877b3e7b981b714cda5954cfac88075d7243b846b101608b86fbba",
    "ATTRIBUTIONS.md": "324d90f3b9bdbd6531609f63c5439090173b9fa8678e9ea76869ef7341a6e28e",
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
