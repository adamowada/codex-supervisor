"""Project registry and generic adapter helpers."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path, PurePath, PureWindowsPath

SOURCE_DOCUMENT_CANDIDATES = (
    "AGENTS.md",
    "PLANS.md",
    "CONTRACTS.md",
    "ARCHITECTURE.md",
    "ROADMAP.md",
    "TESTING.md",
    "README.md",
)
GENERIC_REPO_MARKERS = ("AGENTS.md", "PLANS.md", "plans/planning.sqlite3", "TASKS.json")
VERIFY_SCRIPT_COMMANDS = {
    "scripts/verify.py": "uv run python -B scripts/verify.py",
    "scripts/check_protected_files.py": "uv run python -B scripts/check_protected_files.py",
}


@dataclass(frozen=True)
class ProjectFacts:
    source_documents: tuple[str, ...]
    authority_markers: tuple[str, ...]
    verification_commands: tuple[str, ...]
    has_planning_database: bool
    has_tasks_json: bool


@dataclass(frozen=True)
class ProjectRegistryEntry:
    project_id: str
    root_path: str
    adapter_type: str
    trust_policy: str
    status: str
    facts: ProjectFacts | None = None
    failure_class: str | None = None
    failure_reason: str | None = None


class GenericRepoAdapter:
    """Bounded adapter for repos with Codex-friendly source-of-truth markers."""

    adapter_type = "generic_repo"

    def __init__(self, root: Path) -> None:
        self.root = root

    def facts(self) -> ProjectFacts:
        return ProjectFacts(
            source_documents=tuple(
                candidate
                for candidate in SOURCE_DOCUMENT_CANDIDATES
                if _exists(self.root, candidate)
            ),
            authority_markers=tuple(
                candidate for candidate in GENERIC_REPO_MARKERS if _exists(self.root, candidate)
            ),
            verification_commands=tuple(
                command
                for relative_path, command in VERIFY_SCRIPT_COMMANDS.items()
                if _exists(self.root, relative_path)
            ),
            has_planning_database=_exists(self.root, "plans/planning.sqlite3"),
            has_tasks_json=_exists(self.root, "TASKS.json"),
        )


def discover_projects(
    roots: tuple[Path, ...] | list[Path],
    *,
    trust_policy: str = "local_trusted",
) -> tuple[ProjectRegistryEntry, ...]:
    """Build registry entries for explicit project roots without mutating them."""

    return tuple(_discover_project(root, trust_policy=trust_policy) for root in roots)


def stable_project_id_from_path(path: PurePath) -> str:
    normalized_key = _normalized_path_key(path)
    slug = _slugify(path.name or "project")
    digest = hashlib.sha256(normalized_key.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}"


def _discover_project(root: Path, *, trust_policy: str) -> ProjectRegistryEntry:
    if not root.exists():
        return ProjectRegistryEntry(
            project_id=stable_project_id_from_path(root),
            root_path=str(root),
            adapter_type="unknown",
            trust_policy=trust_policy,
            status="missing",
            failure_class="missing_root",
            failure_reason=f"Project root does not exist: {root}",
        )
    resolved_root = root.resolve()
    adapter = GenericRepoAdapter(resolved_root)
    facts = adapter.facts()
    if not facts.authority_markers:
        return ProjectRegistryEntry(
            project_id=stable_project_id_from_path(resolved_root),
            root_path=str(resolved_root),
            adapter_type="unknown",
            trust_policy=trust_policy,
            status="unsupported",
            facts=facts,
            failure_class="unsupported_project",
            failure_reason="No generic repository authority markers were found.",
        )
    return ProjectRegistryEntry(
        project_id=stable_project_id_from_path(resolved_root),
        root_path=str(resolved_root),
        adapter_type=adapter.adapter_type,
        trust_policy=trust_policy,
        status="ready",
        facts=facts,
    )


def _exists(root: Path, relative_path: str) -> bool:
    return (root / relative_path).exists()


def _normalized_path_key(path: PurePath) -> str:
    if isinstance(path, PureWindowsPath):
        return path.as_posix().casefold()
    return path.as_posix()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "project"
