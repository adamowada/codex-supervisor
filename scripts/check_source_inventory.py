#!/usr/bin/env python3
"""Verify ignored local source clones match documented inventory when present."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = REPO_ROOT / "sources"
ATTRIBUTIONS = REPO_ROOT / "ATTRIBUTIONS.md"
SOURCES_README = SOURCES_ROOT / "README.md"

EXPECTED_SOURCES = {
    "harnesslab-claw-code-agent": {
        "url": "https://github.com/HarnessLab/claw-code-agent",
        "commit": "816bc3a2591910f4dd569e3b1fe24c35280abc5e",
        "license_posture": "No license file or package license found in the bootstrap clone",
        "license_evidence": "none found",
        "use_posture": "Reference-only unless the upstream license is clarified.",
    },
    "mattpocock-agent-browser": {
        "url": "https://github.com/mattpocock/agent-browser",
        "commit": "ea17db856473e2b1f89f35b485ad1cb250678a6b",
        "license_posture": "Apache-2.0",
        "license_evidence": (
            "LICENSE sha256:014bb31e83d5c2e76aea1cc6e82217346ab41362f32cb355ad0f5c10aa0aeaff"
        ),
        "use_posture": "Study browser automation APIs designed for coding agents.",
    },
    "mattpocock-agent-rules-books": {
        "url": "https://github.com/mattpocock/agent-rules-books",
        "commit": "a7d7649044505b9c377c8dca28d2d6a543bc7f8c",
        "license_posture": "MIT; local license copyright Maciej Ciemborowicz",
        "license_evidence": (
            "LICENSE sha256:c21def7bbce1900717a361a06af67399903d31bd3a695757fff534d6698d1bdb"
        ),
        "use_posture": "Study concise rule-pack and skill-pack design.",
    },
    "mattpocock-evalite": {
        "url": "https://github.com/mattpocock/evalite",
        "commit": "e18a793789400b9292f92465d1084344340aef9b",
        "license_posture": "MIT",
        "license_evidence": (
            "LICENSE sha256:d771b938c81101a190dcae20b14f19af77062361e8c4a57af97df26bc61025d7"
        ),
        "use_posture": "Study eval harness patterns for prompts, skills, and workers.",
    },
    "mattpocock-node-DeepResearch": {
        "url": "https://github.com/mattpocock/node-DeepResearch",
        "commit": "69f345ef8ef28f725aaa778177f6be181801411e",
        "license_posture": "Apache-2.0; local license copyright Jina AI",
        "license_evidence": (
            "LICENSE sha256:4e0e989fafce6b20008458b60c238699994547ab5dd9cba6c4d0bf5472a2fd25"
        ),
        "use_posture": "Study bounded research, search, read, and synthesis loops.",
    },
    "mattpocock-sandcastle": {
        "url": "https://github.com/mattpocock/sandcastle",
        "commit": "65063f6c8ea2fccde22d7d415be4d03212668678",
        "license_posture": "MIT",
        "license_evidence": (
            "LICENSE sha256:0e7ac423bf2c6e223b7c5b156f8cf72da49d748e56a1641402c31f22ad07dbb5"
        ),
        "use_posture": (
            "Study sandboxed orchestration, worktrees, branch flow, implementation, "
            "and review loops."
        ),
    },
    "mattpocock-skills": {
        "url": "https://github.com/mattpocock/skills",
        "commit": "b8be62ffacb0118fa3eaa29a0923c87c8c11985c",
        "license_posture": "MIT",
        "license_evidence": (
            "LICENSE sha256:0e7ac423bf2c6e223b7c5b156f8cf72da49d748e56a1641402c31f22ad07dbb5"
        ),
        "use_posture": (
            "Integrated selected engineering skills and supporting references as repo-local skills."
        ),
    },
    "openai-codex": {
        "url": "https://github.com/openai/codex",
        "commit": "7d47056ea42636271ac020b86347fbbef49490aa",
        "license_posture": "Apache-2.0; upstream NOTICE present",
        "license_evidence": (
            "LICENSE sha256:d17f227e4df5da1600391338865ce0f3055211760a36688f816941d58232d8dc; "
            "NOTICE sha256:9d71575ecfd9a843fc1677b0efb08053c6ba9fd686a0de1a6f5382fd3c220915"
        ),
        "use_posture": "Study Codex CLI, codex exec, MCP, configuration, and automation behavior.",
    },
    "openclaw-openclaw": {
        "url": "https://github.com/openclaw/openclaw",
        "commit": "d485464dbc4b6a2f2302b24f42b42364fe90fa8e",
        "license_posture": "MIT",
        "license_evidence": (
            "LICENSE sha256:9efd316ecf1c4c60f6fd5d26433142fff2b6794d7d328e9bc6179b29bf9c82a4"
        ),
        "use_posture": (
            "Study local-first control plane, sessions, tools, skills, cron, and sandboxing."
        ),
    },
    "snarktank-ralph": {
        "url": "https://github.com/snarktank/ralph",
        "commit": "6c53cb0b831ebe8739c6a003e22af14902d8b0b5",
        "license_posture": "MIT",
        "license_evidence": (
            "LICENSE sha256:102b6470e861e782d90a42d9086f48b8a2f38cbc4c0229216bcf0364f79ea5a3"
        ),
        "use_posture": (
            "Study fresh-context autonomous coding loops, PRD-to-story execution, "
            "progress logs, checks, and stop conditions."
        ),
    },
}


@dataclass(frozen=True)
class SourceInventoryFailure:
    source: str
    reason: str


def main() -> int:
    failures = list(check_source_inventory(REPO_ROOT))
    if not failures:
        print("Source inventory checks passed.")
        return 0
    print("Source inventory checks failed.", file=sys.stderr)
    for failure in failures:
        print(f"- {failure.source}: {failure.reason}", file=sys.stderr)
    return 1


def check_source_inventory(repo_root: Path) -> tuple[SourceInventoryFailure, ...]:
    failures: list[SourceInventoryFailure] = []
    sources_root = repo_root / "sources"
    source_dirs = (
        {path.name: path for path in sources_root.iterdir() if path.is_dir()}
        if sources_root.exists()
        else {}
    )

    for source in sorted(set(source_dirs) - set(EXPECTED_SOURCES)):
        failures.append(SourceInventoryFailure(source, "local clone is not documented"))

    sources_readme = repo_root / "sources" / "README.md"
    attributions = repo_root / "ATTRIBUTIONS.md"
    failures.extend(_check_unexpected_documented_rows(sources_readme))
    failures.extend(_check_attributions_source_pointer(attributions))

    for source, expected in EXPECTED_SOURCES.items():
        failures.extend(_check_documented_source_row(sources_readme, source, expected))
        source_path = source_dirs.get(source, sources_root / source)
        if source_path.exists() and not (source_path / ".git").exists():
            failures.append(
                SourceInventoryFailure(source, "local source directory is not a git clone")
            )
        elif (source_path / ".git").exists():
            actual_commit, git_failure = _git_or_failure(source_path, source, "rev-parse", "HEAD")
            if git_failure is not None:
                failures.append(git_failure)
                continue
            if actual_commit != expected["commit"]:
                failures.append(
                    SourceInventoryFailure(
                        source,
                        f"local commit {actual_commit} does not match docs {expected['commit']}",
                    )
                )
            actual_url, git_failure = _git_or_failure(
                source_path, source, "remote", "get-url", "origin"
            )
            if git_failure is not None:
                failures.append(git_failure)
            elif _canonical_source_url(actual_url) != expected["url"]:
                failures.append(
                    SourceInventoryFailure(
                        source,
                        f"remote URL {_canonical_source_url(actual_url)} does not match docs "
                        f"{expected['url']}",
                    )
                )
            dirty, git_failure = _git_or_failure(source_path, source, "status", "--porcelain")
            if git_failure is not None:
                failures.append(git_failure)
            elif dirty:
                failures.append(
                    SourceInventoryFailure(source, "local clone has uncommitted changes")
                )
            actual_license_evidence = _license_evidence(source_path)
            if actual_license_evidence != expected["license_evidence"]:
                failures.append(
                    SourceInventoryFailure(
                        source,
                        "local license evidence does not match documented expected evidence",
                    )
                )
    return tuple(failures)


def _check_attributions_source_pointer(docs_path: Path) -> tuple[SourceInventoryFailure, ...]:
    if not docs_path.exists():
        return (SourceInventoryFailure("ATTRIBUTIONS.md", "ATTRIBUTIONS.md is missing"),)
    text = docs_path.read_text(encoding="utf-8")
    failures: list[SourceInventoryFailure] = []
    rows = _source_rows(text)
    if rows:
        failures.append(
            SourceInventoryFailure(
                "ATTRIBUTIONS.md",
                "duplicate source inventory table belongs in sources/README.md",
            )
        )
    required_markers = (
        "sources/README.md",
        "scripts/check_source_inventory.py",
    )
    for marker in required_markers:
        if marker not in text:
            failures.append(
                SourceInventoryFailure(
                    "ATTRIBUTIONS.md",
                    f"missing pointer to {marker}",
                )
            )
    return tuple(failures)


def _check_unexpected_documented_rows(docs_path: Path) -> tuple[SourceInventoryFailure, ...]:
    if not docs_path.exists():
        return ()
    rows = _source_rows(docs_path.read_text(encoding="utf-8"))
    return tuple(
        SourceInventoryFailure(source, f"unexpected source row in {docs_path.name}")
        for source in sorted(set(rows) - set(EXPECTED_SOURCES))
    )


def _check_documented_source_row(
    docs_path: Path,
    source: str,
    expected: dict[str, str],
) -> tuple[SourceInventoryFailure, ...]:
    if not docs_path.exists():
        return (SourceInventoryFailure(source, f"{docs_path.name} is missing"),)

    rows = _source_rows(docs_path.read_text(encoding="utf-8"))
    row = rows.get(source)
    if row is None:
        return (SourceInventoryFailure(source, f"source row missing from {docs_path.name}"),)

    failures: list[SourceInventoryFailure] = []
    upstream = row.get("upstream", "")
    commit = row.get("local commit", "")
    license_posture = row.get("observed license posture", "")
    license_evidence = row.get("license evidence", "")
    use_posture = row.get("use posture", "")
    if _canonical_source_url(upstream) != expected["url"]:
        failures.append(
            SourceInventoryFailure(
                source,
                f"upstream URL mismatch in {docs_path.name} row",
            )
        )
    if expected["commit"] != commit:
        failures.append(
            SourceInventoryFailure(
                source,
                f"commit SHA mismatch in {docs_path.name} row",
            )
        )
    if expected["license_posture"] != license_posture:
        failures.append(
            SourceInventoryFailure(
                source,
                f"license posture mismatch in {docs_path.name} row",
            )
        )
    if expected["license_evidence"] != license_evidence:
        failures.append(
            SourceInventoryFailure(
                source,
                f"license evidence mismatch in {docs_path.name} row",
            )
        )
    if expected["use_posture"] != use_posture:
        failures.append(
            SourceInventoryFailure(
                source,
                f"use posture mismatch in {docs_path.name} row",
            )
        )
    return tuple(failures)


def _source_rows(text: str) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    headers: tuple[str, ...] = ()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or _is_markdown_separator_row(stripped):
            continue
        cells = tuple(_clean_cell(cell) for cell in stripped.strip("|").split("|"))
        if not cells:
            continue
        if cells[0] in {"Source", "Directory"}:
            headers = tuple(cell.lower() for cell in cells)
            continue
        if len(cells) < 3 or not headers:
            continue
        row = {
            header: cells[index] if index < len(cells) else ""
            for index, header in enumerate(headers)
        }
        rows[cells[0]] = row
    return rows


def _is_markdown_separator_row(stripped_line: str) -> bool:
    cells = tuple(cell.strip() for cell in stripped_line.strip("|").split("|"))
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _clean_cell(value: str) -> str:
    return value.strip().strip("`")


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _git_or_failure(
    repo_root: Path,
    source: str,
    *args: str,
) -> tuple[str, SourceInventoryFailure | None]:
    try:
        return _git(repo_root, *args), None
    except FileNotFoundError as exc:
        return "", SourceInventoryFailure(source, f"git {' '.join(args)} failed: {exc}")
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else str(exc)
        return "", SourceInventoryFailure(source, f"git {' '.join(args)} failed: {stderr}")


def _canonical_source_url(value: str) -> str:
    normalized = value.strip().strip("`").rstrip("/")
    ssh_match = re.fullmatch(r"git@github\.com:(?P<owner>[^/]+)/(?P<repo>.+)", normalized)
    if ssh_match is not None:
        normalized = f"https://github.com/{ssh_match.group('owner')}/{ssh_match.group('repo')}"
    ssh_url_match = re.fullmatch(
        r"ssh://git@github\.com/(?P<owner>[^/]+)/(?P<repo>.+)",
        normalized,
    )
    if ssh_url_match is not None:
        normalized = (
            f"https://github.com/{ssh_url_match.group('owner')}/{ssh_url_match.group('repo')}"
        )
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    return normalized.rstrip("/")


def _license_evidence(source_path: Path) -> str:
    license_parts: list[str] = []
    for path in sorted(source_path.iterdir()):
        if not path.is_file() or path.name.upper().split(".", maxsplit=1)[0] not in {
            "LICENSE",
            "NOTICE",
            "COPYING",
        }:
            continue
        license_parts.append(f"{path.name} sha256:{sha256(path.read_bytes()).hexdigest()}")
    if not license_parts:
        return "none found"
    return "; ".join(license_parts)


if __name__ == "__main__":
    raise SystemExit(main())
