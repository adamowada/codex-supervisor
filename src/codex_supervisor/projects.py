"""Project registry and generic adapter helpers."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path, PurePath, PureWindowsPath
from urllib.parse import quote

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
MAX_PLANNING_SQLITE_TASK_CANDIDATES = 20
PLANNING_SQLITE_PATH = "plans/planning.sqlite3"
PLANNING_SQLITE_OPEN_TASK_STATUSES = frozenset(("pending", "ready", "blocked"))
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
class ProjectTaskSeed:
    task_id: str
    plan_id: str
    title: str
    goal: str
    task_type: str
    status: str
    scope: dict[str, object]
    out_of_scope: dict[str, object]
    acceptance_criteria: tuple[str, ...]
    verification_commands: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    blocked_by: tuple[str, ...]
    worker_backend: str
    review_required: bool


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
            has_planning_database=_exists(self.root, PLANNING_SQLITE_PATH),
            has_tasks_json=_exists(self.root, "TASKS.json"),
        )


class PlanningSQLiteAdapter:
    """Bounded read-only adapter for planning SQLite oriented projects."""

    adapter_type = "nlp_stock_prediction_planning_sqlite"

    def __init__(self, root: Path) -> None:
        self.root = root
        self.database_path = root / PLANNING_SQLITE_PATH

    def facts(self) -> ProjectFacts:
        verification_commands = tuple(
            command
            for relative_path, command in VERIFY_SCRIPT_COMMANDS.items()
            if _exists(self.root, relative_path)
        )
        candidate_tasks, adapter_findings = _read_planning_sqlite_candidates(
            self.database_path,
            default_verification_commands=verification_commands,
        )
        return ProjectFacts(
            source_documents=tuple(
                candidate
                for candidate in SOURCE_DOCUMENT_CANDIDATES
                if _exists(self.root, candidate)
            ),
            authority_markers=(PLANNING_SQLITE_PATH,),
            verification_commands=verification_commands,
            candidate_tasks=candidate_tasks,
            adapter_findings=adapter_findings,
            has_planning_database=self.database_path.exists(),
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


def build_project_task_seeds(
    entry: ProjectRegistryEntry,
    *,
    plan_id: str,
    status: str = "pending",
    worker_backend: str = "codex_exec",
    review_required: bool = True,
) -> tuple[ProjectTaskSeed, ...]:
    if entry.facts is None:
        return ()
    return tuple(
        _project_task_seed_from_candidate(
            candidate,
            entry=entry,
            plan_id=plan_id,
            status=status,
            worker_backend=worker_backend,
            review_required=review_required,
        )
        for candidate in entry.facts.candidate_tasks
    )


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
    planning_adapter = PlanningSQLiteAdapter(resolved_root)
    if planning_adapter.database_path.exists():
        planning_facts = planning_adapter.facts()
        if not planning_facts.adapter_findings:
            return ProjectRegistryEntry(
                project_id=stable_project_id_from_path(resolved_root),
                root_path=str(resolved_root),
                adapter_type=planning_adapter.adapter_type,
                trust_policy=trust_policy,
                status="ready",
                facts=planning_facts,
            )
        if not _generic_non_planning_authority_markers(resolved_root):
            return ProjectRegistryEntry(
                project_id=stable_project_id_from_path(resolved_root),
                root_path=str(resolved_root),
                adapter_type=planning_adapter.adapter_type,
                trust_policy=trust_policy,
                status="unsupported",
                facts=planning_facts,
                failure_class="unsupported_planning_sqlite",
                failure_reason=planning_facts.adapter_findings[0],
            )
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


def _project_task_seed_from_candidate(
    candidate: ProjectTaskCandidate,
    *,
    entry: ProjectRegistryEntry,
    plan_id: str,
    status: str,
    worker_backend: str,
    review_required: bool,
) -> ProjectTaskSeed:
    return ProjectTaskSeed(
        task_id=_task_seed_id(entry.project_id, candidate.source_id),
        plan_id=plan_id,
        title=candidate.title,
        goal=candidate.goal,
        task_type=candidate.task_type,
        status=status,
        scope={
            "source_project": {
                "project_id": entry.project_id,
                "root_path": entry.root_path,
                "adapter_type": entry.adapter_type,
                "trust_policy": entry.trust_policy,
            },
            "source_candidate": {
                "source_id": candidate.source_id,
                "source_path": candidate.source_path,
                "source_authority": list(candidate.source_authority),
            },
        },
        out_of_scope={
            "source_adapter_non_goals": [
                "Seeded tasks preserve adapter output only; downstream task refinement belongs "
                "to the task compiler."
            ]
        },
        acceptance_criteria=candidate.acceptance_criteria,
        verification_commands=candidate.verification_commands,
        allowed_paths=candidate.allowed_paths,
        blocked_by=candidate.blocked_by,
        worker_backend=worker_backend,
        review_required=review_required,
    )


def _task_seed_id(project_id: str, source_id: str) -> str:
    return f"task-{_slugify(project_id)}-{_slugify(source_id)}"


def _exists(root: Path, relative_path: str) -> bool:
    return (root / relative_path).exists()


def _generic_authority_markers(root: Path) -> tuple[str, ...]:
    return tuple(candidate for candidate in GENERIC_REPO_MARKERS if _exists(root, candidate))


def _generic_non_planning_authority_markers(root: Path) -> tuple[str, ...]:
    return tuple(
        marker for marker in _generic_authority_markers(root) if marker != PLANNING_SQLITE_PATH
    )


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


def _read_planning_sqlite_candidates(
    database_path: Path,
    *,
    default_verification_commands: tuple[str, ...],
) -> tuple[tuple[ProjectTaskCandidate, ...], tuple[str, ...]]:
    if not database_path.exists():
        return (), (f"{PLANNING_SQLITE_PATH} was not found.",)
    try:
        with sqlite3.connect(_sqlite_read_only_uri(database_path), uri=True) as connection:
            connection.row_factory = sqlite3.Row
            tables = _sqlite_tables(connection)
            if "tasks" not in tables:
                return (), ("planning SQLite database does not contain a tasks table.",)
            columns = _sqlite_columns(connection, "tasks")
            required_columns = {
                "task_id",
                "title",
                "goal",
                "status",
                "task_type",
                "acceptance_criteria_json",
                "verification_commands_json",
                "allowed_paths_json",
                "blocked_by_json",
            }
            missing_columns = sorted(required_columns - columns)
            if missing_columns:
                return (), (
                    "planning SQLite tasks table is missing required columns: "
                    + ", ".join(missing_columns)
                    + ".",
                )
            open_statuses = tuple(sorted(PLANNING_SQLITE_OPEN_TASK_STATUSES))
            status_placeholders = ", ".join("?" for _ in open_statuses)
            rows = connection.execute(
                f"""
                SELECT task_id, title, goal, status, task_type,
                       acceptance_criteria_json, verification_commands_json,
                       allowed_paths_json, blocked_by_json
                FROM tasks
                WHERE lower(status) IN ({status_placeholders})
                ORDER BY task_id
                LIMIT ?
                """,
                (*open_statuses, MAX_PLANNING_SQLITE_TASK_CANDIDATES),
            ).fetchall()
    except sqlite3.Error as exc:
        return (), (f"planning SQLite database could not be read: {exc}",)
    candidates: list[ProjectTaskCandidate] = []
    findings: list[str] = []
    for row in rows:
        candidate = _planning_sqlite_candidate_from_row(
            row,
            default_verification_commands=default_verification_commands,
            findings=findings,
        )
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates), tuple(findings)


def _sqlite_read_only_uri(path: Path) -> str:
    return f"file:{quote(path.resolve().as_posix(), safe='/:')}?mode=ro"


def _sqlite_tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(row["name"]) for row in rows}


def _sqlite_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row["name"]) for row in rows}


def _planning_sqlite_candidate_from_row(
    row: sqlite3.Row,
    *,
    default_verification_commands: tuple[str, ...],
    findings: list[str],
) -> ProjectTaskCandidate | None:
    task_id = _optional_nonblank_string(row["task_id"])
    title = _optional_nonblank_string(row["title"])
    goal = _optional_nonblank_string(row["goal"])
    if task_id is None or title is None or goal is None:
        findings.append("planning SQLite task row must include nonblank task_id, title, and goal.")
        return None
    status = (_optional_nonblank_string(row["status"]) or "").casefold()
    if status not in PLANNING_SQLITE_OPEN_TASK_STATUSES:
        return None
    task_type = (_optional_nonblank_string(row["task_type"]) or "AFK").upper()
    if task_type not in TASK_TYPES:
        findings.append(f"planning SQLite task {task_id} has unsupported task_type: {task_type}.")
        return None
    acceptance_criteria = _json_string_sequence(row["acceptance_criteria_json"])
    verification_commands = _json_string_sequence(row["verification_commands_json"])
    allowed_paths = _json_string_sequence(row["allowed_paths_json"])
    blocked_by = _json_string_sequence(row["blocked_by_json"])
    return ProjectTaskCandidate(
        source_id=f"planning-sqlite-{_slugify(task_id)}",
        source_path=f"{PLANNING_SQLITE_PATH}:tasks/{task_id}",
        title=title,
        goal=goal,
        task_type=task_type,
        acceptance_criteria=acceptance_criteria,
        verification_commands=verification_commands or default_verification_commands,
        allowed_paths=allowed_paths,
        blocked_by=blocked_by,
        source_authority=(PLANNING_SQLITE_PATH, "tasks"),
    )


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


def _json_string_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, str):
        return ()
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return ()
    return _string_sequence(payload)


def _normalized_path_key(path: PurePath) -> str:
    if isinstance(path, PureWindowsPath):
        return path.as_posix().casefold()
    return path.as_posix()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "project"
