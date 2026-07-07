#!/usr/bin/env python3
"""Check whether a target workspace is safe to ACP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_supervisor.acp_gate import check_target_workspace_acp_gate  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--path", type=Path, default=None, help="Planning SQLite path")
    parser.add_argument("--json", action="store_true", default=False)
    args = parser.parse_args(argv)

    result = check_target_workspace_acp_gate(args.workspace, database_path=args.path)
    payload = {
        "ok": result.ok,
        "failures": list(result.failures),
        "warnings": list(result.warnings),
        "changed_product_paths": list(result.changed_product_paths),
        "worker_backed_paths": list(result.worker_backed_paths),
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif result.ok:
        print("Target workspace ACP gate passed.")
        for warning in result.warnings:
            print(f"warning: {warning}")
    else:
        print("Target workspace ACP gate failed.", file=sys.stderr)
        for failure in result.failures:
            print(f"- {failure}", file=sys.stderr)
        for warning in result.warnings:
            print(f"warning: {warning}", file=sys.stderr)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
