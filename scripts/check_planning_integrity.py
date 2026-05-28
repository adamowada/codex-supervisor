#!/usr/bin/env python3
"""CLI adapter for the package-owned planning integrity checker."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from codex_supervisor.planning_integrity import (  # noqa: E402
    PlanningIntegrityFailure,
    check_planning_integrity,
    main,
)

__all__ = ["PlanningIntegrityFailure", "check_planning_integrity", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
