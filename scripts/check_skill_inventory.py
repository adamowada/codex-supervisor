#!/usr/bin/env python3
"""Fail when repo-local skills drift from bootstrap routing expectations."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = Path(".agents/skills")
ROUTE_MAP_FILES = (Path(".agents/skills/skill-router/SKILL.md"),)
ROUTE_MAP_EXEMPTIONS = frozenset({"codex-supervisor", "skill-router"})
PROHIBITED_SKILL_TEXT = (
    "Claude",
    "Claude Code",
)


@dataclass(frozen=True)
class SkillInventoryFailure:
    relative_path: str
    reason: str


def main() -> int:
    failures = check_skill_inventory(REPO_ROOT)
    if failures:
        print("Skill inventory checks failed.", file=sys.stderr)
        for failure in failures:
            print(f"- {failure.relative_path}: {failure.reason}", file=sys.stderr)
        return 1
    print("Skill inventory checks passed.")
    return 0


def check_skill_inventory(repo_root: Path) -> tuple[SkillInventoryFailure, ...]:
    failures: list[SkillInventoryFailure] = []
    skills_root = repo_root / SKILLS_ROOT
    if not skills_root.exists():
        return (SkillInventoryFailure(SKILLS_ROOT.as_posix(), "skills root is missing"),)

    routed_skills, route_failures = _routed_skill_names(repo_root)
    failures.extend(route_failures)
    for skill_file in sorted(skills_root.glob("*/SKILL.md")):
        relative_path = skill_file.relative_to(repo_root).as_posix()
        text = skill_file.read_text(encoding="utf-8")
        frontmatter = _frontmatter(text)
        skill_name = frontmatter.get("name")
        description = frontmatter.get("description")
        folder_name = skill_file.parent.name

        if skill_name is None:
            failures.append(SkillInventoryFailure(relative_path, "frontmatter is missing name"))
        elif skill_name != folder_name:
            failures.append(
                SkillInventoryFailure(
                    relative_path,
                    f"frontmatter name {skill_name!r} does not match folder {folder_name!r}",
                )
            )

        if description is None or len(description.strip()) < 20:
            failures.append(
                SkillInventoryFailure(
                    relative_path, "frontmatter description is missing or too thin"
                )
            )

        prohibited = _first_prohibited_text(text)
        if prohibited is not None:
            failures.append(
                SkillInventoryFailure(
                    relative_path, f"contains prohibited reference {prohibited!r}"
                )
            )

        if (
            skill_name is not None
            and skill_name not in ROUTE_MAP_EXEMPTIONS
            and skill_name not in routed_skills
        ):
            failures.append(
                SkillInventoryFailure(
                    relative_path,
                    "skill is not explicitly routed by skill-router",
                )
            )

    for support_file in sorted(path for path in skills_root.rglob("*") if path.is_file()):
        if support_file.name == "SKILL.md":
            continue
        relative_path = support_file.relative_to(repo_root).as_posix()
        try:
            text = support_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        prohibited = _first_prohibited_text(text)
        if prohibited is not None:
            failures.append(
                SkillInventoryFailure(
                    relative_path, f"contains prohibited reference {prohibited!r}"
                )
            )

    return tuple(failures)


def _routed_skill_names(
    repo_root: Path,
) -> tuple[frozenset[str], tuple[SkillInventoryFailure, ...]]:
    routed: set[str] = set()
    failures: list[SkillInventoryFailure] = []
    for relative_path in ROUTE_MAP_FILES:
        path = repo_root / relative_path
        if not path.exists():
            failures.append(
                SkillInventoryFailure(
                    relative_path.as_posix(),
                    "route map file is missing",
                )
            )
            continue
        in_route_section = False
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                in_route_section = stripped == "## Route By Intent"
                continue
            if not in_route_section:
                continue
            if not stripped.startswith("-"):
                continue
            match = re.fullmatch(r"- [^:]+: `([a-z0-9-]+)`\.", stripped)
            if match is None:
                continue
            routed.add(match.group(1))
    return frozenset(routed), tuple(failures)


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    try:
        _, raw_frontmatter, _ = text.split("---", maxsplit=2)
    except ValueError:
        return {}
    values: dict[str, str] = {}
    for line in raw_frontmatter.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", maxsplit=1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _first_prohibited_text(text: str) -> str | None:
    for phrase in PROHIBITED_SKILL_TEXT:
        if re.search(rf"\b{re.escape(phrase)}\b", text, flags=re.IGNORECASE):
            return phrase
    return None


if __name__ == "__main__":
    raise SystemExit(main())
