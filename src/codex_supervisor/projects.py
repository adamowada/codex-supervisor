"""Project registry and generic adapter helpers."""

from __future__ import annotations

import hashlib
import json
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
MAX_TASKS_JSON_BYTES = 64 * 1024
VERIFY_SCRIPT_COMMANDS = {
    "scripts/verify.py": "uv run --no-sync python -B scripts/verify.py",
    "scripts/check_protected_files.py": (
        "uv run --no-sync python -B scripts/check_protected_files.py"
    ),
}
TASK_TYPES = frozenset(("AFK", "HITL"))


@dataclass(frozen=True)
class ProjectTaskCandidate:
    source_id: str
    source_path: str
    title: str
    goal: str
    task_type: str
    acceptance_criteria: tuple[str, ...]
    verification_commands: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    blocked_by: tuple[str, ...]
    source_authority: tuple[str, ...]


@dataclass(frozen=True)
class ProjectFacts:
    source_documents: tuple[str, ...]
    authority_markers: tuple[str, ...]
    verification_commands: tuple[str, ...]
    candidate_tasks: tuple[ProjectTaskCandidate, ...]
    adapter_findings: tuple[str, ...]
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
        verification_commands = tuple(
            command
            for relative_path, command in VERIFY_SCRIPT_COMMANDS.items()
            if _exists(self.root, relative_path)
        )
        candidate_tasks, adapter_findings = _read_tasks_json_candidates(
            self.root,
            default_verification_commands=verification_commands,
        )
        return ProjectFacts(
            source_documents=tuple(
                candidate
                for candidate in SOURCE_DOCUMENT_CANDIDATES
                if _exists(self.root, candidate)
            ),
            authority_markers=tuple(
                candidate for candidate in GENERIC_REPO_MARKERS if _exists(self.root, candidate)
            ),
            verification_commands=verification_commands,
            candidate_tasks=candidate_tasks,
            adapter_findings=adapter_findings,
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


def _read_tasks_json_candidates(
    root: Path,
    *,
    default_verification_commands: tuple[str, ...],
) -> tuple[tuple[ProjectTaskCandidate, ...], tuple[str, ...]]:
    tasks_path = root / "TASKS.json"
    if not tasks_path.exists():
        return (), ()
    findings: list[str] = []
    try:
        size = tasks_path.stat().st_size
    except OSError as exc:
        return (), (f"TASKS.json could not be inspected: {exc}",)
    if size > MAX_TASKS_JSON_BYTES:
        return (), (f"TASKS.json is larger than {MAX_TASKS_JSON_BYTES} bytes.",)
    try:
        payload = json.loads(tasks_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return (), (f"TASKS.json could not be parsed: {exc}",)
    if not isinstance(payload, list):
        return (), ("TASKS.json must contain a top-level JSON array of task objects.",)

    candidates: list[ProjectTaskCandidate] = []
    for index, item in enumerate(payload):
        candidate = _project_task_candidate_from_payload(
            item,
            index=index,
            default_verification_commands=default_verification_commands,
            findings=findings,
        )
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates), tuple(findings)


def _project_task_candidate_from_payload(
    item: object,
    *,
    index: int,
    default_verification_commands: tuple[str, ...],
    findings: list[str],
) -> ProjectTaskCandidate | None:
    if not isinstance(item, dict):
        findings.append(f"TASKS.json entry {index} is not an object.")
        return None

    title = _optional_nonblank_string(item.get("title"))
    goal = _optional_nonblank_string(item.get("goal"))
    if title is None or goal is None:
        findings.append(f"TASKS.json entry {index} must include nonblank title and goal.")
        return None

    task_type = (_optional_nonblank_string(item.get("task_type")) or "AFK").upper()
    if task_type not in TASK_TYPES:
        findings.append(f"TASKS.json entry {index} has unsupported task_type: {task_type}.")
        return None

    raw_source_id = _optional_nonblank_string(item.get("id"))
    source_id = _task_candidate_source_id(
        raw_source_id=raw_source_id,
        index=index,
        title=title,
        goal=goal,
    )
    acceptance_criteria = _string_sequence(item.get("acceptance_criteria"))
    verification_commands = _string_sequence(item.get("verification_commands"))
    allowed_paths = _string_sequence(item.get("allowed_paths"))
    blocked_by = _string_sequence(item.get("blocked_by"))

    return ProjectTaskCandidate(
        source_id=source_id,
        source_path="TASKS.json",
        title=title,
        goal=goal,
        task_type=task_type,
        acceptance_criteria=acceptance_criteria,
        verification_commands=verification_commands or default_verification_commands,
        allowed_paths=allowed_paths,
        blocked_by=blocked_by,
        source_authority=("TASKS.json",),
    )


def _task_candidate_source_id(
    *,
    raw_source_id: str | None,
    index: int,
    title: str,
    goal: str,
) -> str:
    if raw_source_id:
        return f"tasks-json-{_slugify(raw_source_id)}"
    slug = _slugify(title)
    digest = hashlib.sha256(f"{index}\0{title}\0{goal}".encode()).hexdigest()[:8]
    return f"tasks-json-{slug}-{digest}"


def _optional_nonblank_string(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _string_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    values: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            values.append(item.strip())
    return tuple(values)


def _normalized_path_key(path: PurePath) -> str:
    if isinstance(path, PureWindowsPath):
        return path.as_posix().casefold()
    return path.as_posix()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "project"
