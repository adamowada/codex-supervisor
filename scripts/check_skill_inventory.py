#!/usr/bin/env python3
"""Validate the repo-local skill surface."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPO_ROOT / ".agents" / "skills"
EXPECTED_SKILLS = {
    "codex-supervisor",
    "improve-codebase-architecture",
    "reduce-codebase-complexity",
}


def main() -> int:
    failures = check_skill_inventory()
    if failures:
        print("Skill inventory checks failed.", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Skill inventory checks passed.")
    return 0


def check_skill_inventory() -> tuple[str, ...]:
    failures: list[str] = []
    if not SKILLS_ROOT.exists():
        return (".agents/skills is missing",)

    skill_files = sorted(SKILLS_ROOT.glob("*/SKILL.md"))
    skill_names = {path.parent.name for path in skill_files}
    if skill_names != EXPECTED_SKILLS:
        failures.append(f"skills are {sorted(skill_names)}, expected {sorted(EXPECTED_SKILLS)}")

    for path in skill_files:
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(REPO_ROOT).as_posix()
        if not text.startswith("---\n"):
            failures.append(f"{relative} is missing frontmatter")
        if f"name: {path.parent.name}" not in text:
            failures.append(f"{relative} frontmatter name does not match directory")
        if "[TODO" in text:
            failures.append(f"{relative} still contains template TODO text")
        if (
            path.parent.name == "codex-supervisor"
            and "TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision" not in text
        ):
            failures.append(f"{relative} does not name the simplified work model")
        if path.parent.name == "reduce-codebase-complexity":
            for required in (
                "State Space",
                "Reduction Candidate",
                "REDUCTION-MOVES.md",
                "Calibrate Ruthlessness",
                "Ruthless",
                "Focused",
                "Cautious",
                "Sacred constraints",
            ):
                if required not in text:
                    failures.append(f"{relative} does not include {required!r}")

    return tuple(failures)


if __name__ == "__main__":
    raise SystemExit(main())
