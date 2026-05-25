"""Project registry and generic adapter helpers."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path, PurePath, PureWindowsPath
from urllib.parse import quote

from codex_supervisor.insights import INSIGHT_CONFIDENCE_LABELS

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
MAX_MARKDOWN_PLAN_BYTES = 64 * 1024
MAX_MARKDOWN_PLAN_FILES = 8
MAX_HARNESS_CONFIG_BYTES = 64 * 1024
MAX_HARNESS_PROMPT_BYTES = 64 * 1024
MAX_HARNESS_TASK_CANDIDATES = 20
MAX_HARNESS_TASK_ENTRIES = 64
MAX_INSIGHTS_GRAPH_BYTES = 64 * 1024
MAX_INSIGHTS_WIKI_FILES = 8
MAX_INSIGHTS_TASK_CANDIDATES = 20
MAX_INSIGHTS_TABLE_ROWS = 64
PLANNING_SQLITE_PATH = "plans/planning.sqlite3"
PLANNING_SQLITE_OPEN_TASK_STATUSES = frozenset(("pending", "ready", "blocked"))
MARKDOWN_PLAN_DIRECTORIES = ("plans/active", "plans")
MARKDOWN_PLAN_MARKER = "observe-safety-plan"
MARKDOWN_PLAN_MARKER_NOT_FOUND_FINDING = "structured markdown plan marker was not found."
MARKDOWN_PLAN_ACTIVE_STATUSES = frozenset(("active", "ready"))
HARNESS_CONFIG_CANDIDATES = (
    "harness/config.json",
    "harness/tasks.json",
    "codex-subagent-testing.json",
)
HARNESS_CONFIG_MARKER = "codex-subagent-testing"
HARNESS_CONFIG_MARKER_NOT_FOUND_FINDING = "codex-subagent-testing harness marker was not found."
INSIGHTS_GRAPH_PATH = "insights/graph.md"
INSIGHTS_GRAPH_MARKER = "tech-resume"
INSIGHTS_GRAPH_MARKER_NOT_FOUND_FINDING = "tech-resume insights graph marker was not found."
VERIFY_SCRIPT_COMMANDS = {
    "scripts/verify.py": "uv run --no-sync python -B scripts/verify.py",
    "scripts/check_protected_files.py": (
        "uv run --no-sync python -B scripts/check_protected_files.py"
    ),
}
MARKDOWN_PLAN_VERIFY_SCRIPT_COMMANDS = {
    "scripts/validate_plan.py": "uv run --no-sync python -B scripts/validate_plan.py",
    "scripts/validate_plans.py": "uv run --no-sync python -B scripts/validate_plans.py",
    **VERIFY_SCRIPT_COMMANDS,
}
HARNESS_VERIFY_SCRIPT_COMMANDS = {
    "scripts/run_harness.py": "uv run --no-sync python -B scripts/run_harness.py",
    "scripts/verify_harness.py": "uv run --no-sync python -B scripts/verify_harness.py",
    **VERIFY_SCRIPT_COMMANDS,
}
INSIGHTS_VERIFY_SCRIPT_COMMANDS = {
    "scripts/check_insights.py": "uv run --no-sync python -B scripts/check_insights.py",
    "scripts/validate_insights.py": "uv run --no-sync python -B scripts/validate_insights.py",
    **VERIFY_SCRIPT_COMMANDS,
}
TASK_TYPES = frozenset(("AFK", "HITL"))
MARKDOWN_TASK_HEADING_RE = re.compile(
    r"^##\s+Task:\s*(?P<title>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


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


class MarkdownPlanAdapter:
    """Bounded read-only adapter for structured markdown plan projects."""

    adapter_type = "observe_safety_markdown_plan"

    def __init__(self, root: Path) -> None:
        self.root = root

    def plan_paths(self) -> tuple[Path, ...]:
        paths, _total_count = _markdown_plan_paths(self.root)
        return paths

    def facts(self) -> ProjectFacts:
        verification_commands = tuple(
            command
            for relative_path, command in MARKDOWN_PLAN_VERIFY_SCRIPT_COMMANDS.items()
            if _exists(self.root, relative_path)
        )
        candidate_tasks, adapter_findings = _read_markdown_plan_candidates(
            self.root,
            default_verification_commands=verification_commands,
        )
        plan_documents = tuple(_relative_path(self.root, path) for path in self.plan_paths())
        return ProjectFacts(
            source_documents=(
                *plan_documents,
                *tuple(
                    candidate
                    for candidate in SOURCE_DOCUMENT_CANDIDATES
                    if _exists(self.root, candidate)
                ),
            ),
            authority_markers=plan_documents,
            verification_commands=verification_commands,
            candidate_tasks=candidate_tasks,
            adapter_findings=adapter_findings,
            has_planning_database=_exists(self.root, PLANNING_SQLITE_PATH),
            has_tasks_json=_exists(self.root, "TASKS.json"),
        )


class HarnessConfigAdapter:
    """Bounded read-only adapter for harness/config/prompt projects."""

    adapter_type = "codex_subagent_testing_harness_config"

    def __init__(self, root: Path) -> None:
        self.root = root

    def config_path(self) -> Path | None:
        for relative_path in HARNESS_CONFIG_CANDIDATES:
            path = self.root / relative_path
            if path.exists():
                return path
        return None

    def facts(self) -> ProjectFacts:
        verification_commands = tuple(
            command
            for relative_path, command in HARNESS_VERIFY_SCRIPT_COMMANDS.items()
            if _exists(self.root, relative_path)
        )
        config_path = self.config_path()
        candidate_tasks, adapter_findings = _read_harness_config_candidates(
            self.root,
            config_path=config_path,
            default_verification_commands=verification_commands,
        )
        config_documents = () if config_path is None else (_relative_path(self.root, config_path),)
        return ProjectFacts(
            source_documents=(
                *config_documents,
                *tuple(
                    candidate
                    for candidate in SOURCE_DOCUMENT_CANDIDATES
                    if _exists(self.root, candidate)
                ),
            ),
            authority_markers=config_documents,
            verification_commands=verification_commands,
            candidate_tasks=candidate_tasks,
            adapter_findings=adapter_findings,
            has_planning_database=_exists(self.root, PLANNING_SQLITE_PATH),
            has_tasks_json=_exists(self.root, "TASKS.json"),
        )


class InsightsGraphAdapter:
    """Bounded read-only adapter for insights graph/wiki projects."""

    adapter_type = "tech_resume_insights_graph"

    def __init__(self, root: Path) -> None:
        self.root = root
        self.graph_path = root / INSIGHTS_GRAPH_PATH

    def facts(self) -> ProjectFacts:
        verification_commands = tuple(
            command
            for relative_path, command in INSIGHTS_VERIFY_SCRIPT_COMMANDS.items()
            if _exists(self.root, relative_path)
        )
        candidate_tasks, graph_findings = _read_insights_graph_candidates(
            self.root,
            graph_path=self.graph_path,
            default_verification_commands=verification_commands,
        )
        graph_documents: tuple[str, ...] = (
            () if not self.graph_path.exists() else (INSIGHTS_GRAPH_PATH,)
        )
        wiki_documents: tuple[str, ...]
        if graph_findings:
            wiki_documents = graph_documents
            adapter_findings = graph_findings
        else:
            wiki_documents, wiki_findings = _insights_wiki_documents(self.root)
            adapter_findings = (*graph_findings, *wiki_findings)
        return ProjectFacts(
            source_documents=(
                *wiki_documents,
                *tuple(
                    candidate
                    for candidate in SOURCE_DOCUMENT_CANDIDATES
                    if _exists(self.root, candidate)
                ),
            ),
            authority_markers=graph_documents,
            verification_commands=verification_commands,
            candidate_tasks=candidate_tasks,
            adapter_findings=adapter_findings,
            has_planning_database=_exists(self.root, PLANNING_SQLITE_PATH),
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
    markdown_adapter = MarkdownPlanAdapter(resolved_root)
    if markdown_adapter.plan_paths():
        markdown_facts = markdown_adapter.facts()
        if not markdown_facts.adapter_findings:
            return ProjectRegistryEntry(
                project_id=stable_project_id_from_path(resolved_root),
                root_path=str(resolved_root),
                adapter_type=markdown_adapter.adapter_type,
                trust_policy=trust_policy,
                status="ready",
                facts=markdown_facts,
            )
        if not (
            _only_markdown_plan_marker_missing(markdown_facts)
            and _generic_authority_markers(resolved_root)
        ):
            return ProjectRegistryEntry(
                project_id=stable_project_id_from_path(resolved_root),
                root_path=str(resolved_root),
                adapter_type=markdown_adapter.adapter_type,
                trust_policy=trust_policy,
                status="unsupported",
                facts=markdown_facts,
                failure_class="unsupported_markdown_plan",
                failure_reason=markdown_facts.adapter_findings[0],
            )
    harness_adapter = HarnessConfigAdapter(resolved_root)
    if harness_adapter.config_path() is not None:
        harness_facts = harness_adapter.facts()
        if not harness_facts.adapter_findings:
            return ProjectRegistryEntry(
                project_id=stable_project_id_from_path(resolved_root),
                root_path=str(resolved_root),
                adapter_type=harness_adapter.adapter_type,
                trust_policy=trust_policy,
                status="ready",
                facts=harness_facts,
            )
        if not (
            _only_harness_config_marker_missing(harness_facts)
            and _generic_authority_markers(resolved_root)
        ):
            return ProjectRegistryEntry(
                project_id=stable_project_id_from_path(resolved_root),
                root_path=str(resolved_root),
                adapter_type=harness_adapter.adapter_type,
                trust_policy=trust_policy,
                status="unsupported",
                facts=harness_facts,
                failure_class="unsupported_harness_config",
                failure_reason=harness_facts.adapter_findings[0],
            )
    insights_adapter = InsightsGraphAdapter(resolved_root)
    if insights_adapter.graph_path.exists():
        insights_facts = insights_adapter.facts()
        if not insights_facts.adapter_findings:
            return ProjectRegistryEntry(
                project_id=stable_project_id_from_path(resolved_root),
                root_path=str(resolved_root),
                adapter_type=insights_adapter.adapter_type,
                trust_policy=trust_policy,
                status="ready",
                facts=insights_facts,
            )
        if not (
            _only_insights_graph_marker_missing(insights_facts)
            and _generic_authority_markers(resolved_root)
        ):
            return ProjectRegistryEntry(
                project_id=stable_project_id_from_path(resolved_root),
                root_path=str(resolved_root),
                adapter_type=insights_adapter.adapter_type,
                trust_policy=trust_policy,
                status="unsupported",
                facts=insights_facts,
                failure_class="unsupported_insights_graph",
                failure_reason=insights_facts.adapter_findings[0],
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


def _only_markdown_plan_marker_missing(facts: ProjectFacts) -> bool:
    return facts.adapter_findings == (MARKDOWN_PLAN_MARKER_NOT_FOUND_FINDING,)


def _only_harness_config_marker_missing(facts: ProjectFacts) -> bool:
    return facts.adapter_findings == (HARNESS_CONFIG_MARKER_NOT_FOUND_FINDING,)


def _only_insights_graph_marker_missing(facts: ProjectFacts) -> bool:
    return facts.adapter_findings == (INSIGHTS_GRAPH_MARKER_NOT_FOUND_FINDING,)


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


def _read_markdown_plan_candidates(
    root: Path,
    *,
    default_verification_commands: tuple[str, ...],
) -> tuple[tuple[ProjectTaskCandidate, ...], tuple[str, ...]]:
    plan_paths, total_plan_count = _markdown_plan_paths(root)
    if not plan_paths:
        return (), ("structured markdown plan files were not found.",)
    findings: list[str] = []
    if total_plan_count > len(plan_paths):
        findings.append(
            "structured markdown plan file limit exceeded; "
            f"inspecting first {MAX_MARKDOWN_PLAN_FILES} of {total_plan_count} files."
        )

    marker_found = False
    candidates: list[ProjectTaskCandidate] = []
    for plan_path in plan_paths:
        relative_path = _relative_path(root, plan_path)
        try:
            size = plan_path.stat().st_size
        except OSError as exc:
            findings.append(f"{relative_path} could not be inspected: {exc}")
            continue
        if size > MAX_MARKDOWN_PLAN_BYTES:
            findings.append(f"{relative_path} is larger than {MAX_MARKDOWN_PLAN_BYTES} bytes.")
            continue
        try:
            text = plan_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(f"{relative_path} could not be read: {exc}")
            continue
        if MARKDOWN_PLAN_MARKER not in text.casefold():
            continue
        marker_found = True
        plan_status = _markdown_plan_status(text)
        if plan_status is None:
            findings.append(f"{relative_path} must include nonblank Plan Status metadata.")
            continue
        if plan_status.casefold() not in MARKDOWN_PLAN_ACTIVE_STATUSES:
            continue
        candidates.extend(
            _markdown_plan_candidates_from_text(
                relative_path=relative_path,
                text=text,
                default_verification_commands=default_verification_commands,
                findings=findings,
            )
        )
    if not marker_found and not findings:
        findings.append(MARKDOWN_PLAN_MARKER_NOT_FOUND_FINDING)
    return tuple(candidates), tuple(findings)


def _markdown_plan_candidates_from_text(
    *,
    relative_path: str,
    text: str,
    default_verification_commands: tuple[str, ...],
    findings: list[str],
) -> tuple[ProjectTaskCandidate, ...]:
    matches = tuple(MARKDOWN_TASK_HEADING_RE.finditer(text))
    if not matches:
        findings.append(f"{relative_path} contains no structured task headings.")
        return ()

    candidates: list[ProjectTaskCandidate] = []
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section = text[match.end() : next_start]
        candidate = _markdown_plan_candidate_from_section(
            relative_path=relative_path,
            title=match.group("title"),
            section=section,
            default_verification_commands=default_verification_commands,
            findings=findings,
        )
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates)


def _markdown_plan_candidate_from_section(
    *,
    relative_path: str,
    title: str,
    section: str,
    default_verification_commands: tuple[str, ...],
    findings: list[str],
) -> ProjectTaskCandidate | None:
    normalized_title = _optional_nonblank_string(title)
    goal = _markdown_field(section, "Goal")
    if normalized_title is None or goal is None:
        findings.append(f"{relative_path} task must include nonblank title and Goal metadata.")
        return None
    status = (_markdown_field(section, "Status") or "ready").casefold()
    if status not in PLANNING_SQLITE_OPEN_TASK_STATUSES:
        return None
    task_type = (_markdown_field(section, "Type") or "AFK").upper()
    if task_type not in TASK_TYPES:
        findings.append(
            f"{relative_path} task {normalized_title} has unsupported Type: {task_type}."
        )
        return None
    raw_source_id = _markdown_field(section, "ID") or normalized_title
    acceptance_criteria = _markdown_bullet_section(section, "Acceptance Criteria")
    verification_commands = _markdown_bullet_section(section, "Verification Commands")
    allowed_paths = _markdown_bullet_section(section, "Allowed Paths")
    blocked_by = _markdown_bullet_section(section, "Blocked By")
    heading_anchor = f"task-{_slugify(normalized_title)}"
    return ProjectTaskCandidate(
        source_id=f"markdown-plan-{_slugify(relative_path)}-{_slugify(raw_source_id)}",
        source_path=f"{relative_path}#{heading_anchor}",
        title=normalized_title,
        goal=goal,
        task_type=task_type,
        acceptance_criteria=acceptance_criteria,
        verification_commands=verification_commands or default_verification_commands,
        allowed_paths=allowed_paths,
        blocked_by=blocked_by,
        source_authority=(relative_path, f"Task: {normalized_title}"),
    )


def _read_harness_config_candidates(
    root: Path,
    *,
    config_path: Path | None,
    default_verification_commands: tuple[str, ...],
) -> tuple[tuple[ProjectTaskCandidate, ...], tuple[str, ...]]:
    if config_path is None:
        return (), ("codex-subagent-testing harness config was not found.",)
    relative_config_path = _relative_path(root, config_path)
    try:
        size = config_path.stat().st_size
    except OSError as exc:
        return (), (f"{relative_config_path} could not be inspected: {exc}",)
    if size > MAX_HARNESS_CONFIG_BYTES:
        return (), (f"{relative_config_path} is larger than {MAX_HARNESS_CONFIG_BYTES} bytes.",)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return (), (f"{relative_config_path} could not be parsed: {exc}",)
    if not isinstance(payload, dict):
        return (), (f"{relative_config_path} must contain a top-level JSON object.",)
    if not _harness_config_has_marker(payload):
        return (), (HARNESS_CONFIG_MARKER_NOT_FOUND_FINDING,)

    entry_collection = "runs" if isinstance(payload.get("runs"), list) else "tasks"
    raw_entries = payload.get(entry_collection)
    if not isinstance(raw_entries, list):
        return (), (f"{relative_config_path} must contain a runs or tasks array.",)
    findings: list[str] = []
    if len(raw_entries) > MAX_HARNESS_TASK_ENTRIES:
        findings.append(
            "harness config task entry limit exceeded; "
            f"inspecting first {MAX_HARNESS_TASK_ENTRIES} of {len(raw_entries)} entries."
        )
    candidates: list[ProjectTaskCandidate] = []
    for index, item in enumerate(raw_entries[:MAX_HARNESS_TASK_ENTRIES]):
        if len(candidates) >= MAX_HARNESS_TASK_CANDIDATES:
            break
        candidate = _harness_config_candidate_from_payload(
            item,
            index=index,
            root=root,
            relative_config_path=relative_config_path,
            entry_collection=entry_collection,
            default_verification_commands=default_verification_commands,
            findings=findings,
        )
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates), tuple(findings)


def _harness_config_has_marker(payload: dict[str, object]) -> bool:
    for key in ("schema", "adapter", "project_type", "kind"):
        marker = _optional_nonblank_string(payload.get(key))
        if marker is not None and HARNESS_CONFIG_MARKER in marker.casefold():
            return True
    return False


def _harness_config_candidate_from_payload(
    item: object,
    *,
    index: int,
    root: Path,
    relative_config_path: str,
    entry_collection: str,
    default_verification_commands: tuple[str, ...],
    findings: list[str],
) -> ProjectTaskCandidate | None:
    if not isinstance(item, dict):
        findings.append(f"{relative_config_path} entry {index} is not an object.")
        return None

    title = _optional_nonblank_string(item.get("title"))
    goal = _optional_nonblank_string(item.get("goal"))
    if title is None or goal is None:
        findings.append(
            f"{relative_config_path} entry {index} must include nonblank title and goal."
        )
        return None
    status = (_optional_nonblank_string(item.get("status")) or "ready").casefold()
    if status not in PLANNING_SQLITE_OPEN_TASK_STATUSES:
        return None
    task_type = (_optional_nonblank_string(item.get("task_type")) or "AFK").upper()
    if task_type not in TASK_TYPES:
        findings.append(
            f"{relative_config_path} entry {index} has unsupported task_type: {task_type}."
        )
        return None
    prompt_path = _safe_relative_project_path(root, item.get("prompt_path"))
    if prompt_path is None:
        findings.append(f"{relative_config_path} entry {index} must include a safe prompt_path.")
        return None
    prompt_finding = _harness_prompt_file_finding(root, prompt_path)
    if prompt_finding is not None:
        findings.append(prompt_finding)
        return None

    raw_source_id = _optional_nonblank_string(item.get("id")) or title
    acceptance_criteria = _string_sequence(item.get("acceptance_criteria"))
    verification_commands = _string_sequence(item.get("verification_commands"))
    allowed_paths = _string_sequence(item.get("allowed_paths"))
    blocked_by = _string_sequence(item.get("blocked_by"))
    return ProjectTaskCandidate(
        source_id=f"harness-config-{_slugify(raw_source_id)}",
        source_path=f"{relative_config_path}:{entry_collection}/{_slugify(raw_source_id)}",
        title=title,
        goal=goal,
        task_type=task_type,
        acceptance_criteria=acceptance_criteria,
        verification_commands=verification_commands or default_verification_commands,
        allowed_paths=allowed_paths,
        blocked_by=blocked_by,
        source_authority=(relative_config_path, prompt_path),
    )


def _read_insights_graph_candidates(
    root: Path,
    *,
    graph_path: Path,
    default_verification_commands: tuple[str, ...],
) -> tuple[tuple[ProjectTaskCandidate, ...], tuple[str, ...]]:
    relative_graph_path = _relative_path(root, graph_path)
    try:
        size = graph_path.stat().st_size
    except OSError as exc:
        return (), (f"{relative_graph_path} could not be inspected: {exc}",)
    if size > MAX_INSIGHTS_GRAPH_BYTES:
        return (), (f"{relative_graph_path} is larger than {MAX_INSIGHTS_GRAPH_BYTES} bytes.",)
    try:
        text = graph_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return (), (f"{relative_graph_path} could not be read: {exc}",)
    if INSIGHTS_GRAPH_MARKER not in text.casefold():
        return (), (INSIGHTS_GRAPH_MARKER_NOT_FOUND_FINDING,)

    table = _insights_graph_table(text)
    if table is None:
        return (), (f"{relative_graph_path} must contain a confidence/next action table.",)
    headers, rows = table
    findings: list[str] = []
    if len(rows) > MAX_INSIGHTS_TABLE_ROWS:
        findings.append(
            "insights graph row limit exceeded; "
            f"inspecting first {MAX_INSIGHTS_TABLE_ROWS} of {len(rows)} rows."
        )
    candidates: list[ProjectTaskCandidate] = []
    for index, cells in enumerate(rows[:MAX_INSIGHTS_TABLE_ROWS]):
        if len(candidates) >= MAX_INSIGHTS_TASK_CANDIDATES:
            break
        row = _insights_graph_row(headers, cells)
        candidate = _insights_graph_candidate_from_row(
            row,
            index=index,
            root=root,
            relative_graph_path=relative_graph_path,
            default_verification_commands=default_verification_commands,
            findings=findings,
        )
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates), tuple(findings)


def _insights_wiki_documents(root: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    insights_root = root / "insights"
    if not insights_root.exists():
        return (INSIGHTS_GRAPH_PATH,), ()
    all_paths = sorted(path for path in insights_root.glob("*.md") if path.is_file())
    findings: tuple[str, ...] = ()
    if len(all_paths) > MAX_INSIGHTS_WIKI_FILES:
        findings = (
            "insights wiki file limit exceeded; "
            f"inspecting first {MAX_INSIGHTS_WIKI_FILES} of {len(all_paths)} files.",
        )
    paths = all_paths[:MAX_INSIGHTS_WIKI_FILES]
    documents = tuple(_relative_path(root, path) for path in paths)
    return documents or (INSIGHTS_GRAPH_PATH,), findings


def _insights_graph_table(text: str) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]] | None:
    lines = text.splitlines()
    for index, line in enumerate(lines[:-1]):
        if not _is_markdown_table_line(line):
            continue
        headers = tuple(_normalize_markdown_table_header(cell) for cell in _split_table_row(line))
        if "confidence" not in headers or "next action" not in headers:
            continue
        separator = lines[index + 1]
        if not _is_markdown_table_separator(separator):
            return None
        rows: list[tuple[str, ...]] = []
        for row_line in lines[index + 2 :]:
            if not _is_markdown_table_line(row_line):
                break
            rows.append(tuple(cell.strip() for cell in _split_table_row(row_line)))
        return headers, tuple(rows)
    return None


def _insights_graph_row(headers: tuple[str, ...], cells: tuple[str, ...]) -> dict[str, str]:
    return {
        header: cells[index].strip() if index < len(cells) else ""
        for index, header in enumerate(headers)
    }


def _insights_graph_candidate_from_row(
    row: dict[str, str],
    *,
    index: int,
    root: Path,
    relative_graph_path: str,
    default_verification_commands: tuple[str, ...],
    findings: list[str],
) -> ProjectTaskCandidate | None:
    confidence = _optional_nonblank_string(row.get("confidence"))
    if confidence is None:
        findings.append(f"{relative_graph_path} row {index} must include a confidence label.")
        return None
    normalized_confidence = confidence.casefold()
    if normalized_confidence not in INSIGHT_CONFIDENCE_LABELS:
        findings.append(
            f"{relative_graph_path} row {index} has unsupported confidence: {confidence}."
        )
        return None
    next_action = _optional_nonblank_string(row.get("next action"))
    if next_action is None or not _insight_next_action_is_actionable(next_action):
        return None

    task_type = (_optional_nonblank_string(row.get("task type")) or "AFK").upper()
    if task_type not in TASK_TYPES:
        findings.append(
            f"{relative_graph_path} row {index} has unsupported task_type: {task_type}."
        )
        return None
    allowed_paths = _insight_allowed_paths(root, row.get("allowed paths"), findings)
    if allowed_paths is None:
        findings.append(f"{relative_graph_path} row {index} must include safe allowed paths.")
        return None
    source = _optional_nonblank_string(row.get("source")) or relative_graph_path
    relation = _optional_nonblank_string(row.get("relation")) or "relates to"
    insight_from = _optional_nonblank_string(row.get("from")) or "Insight"
    insight_to = _optional_nonblank_string(row.get("to")) or next_action
    raw_source_id = f"{insight_from}-{relation}-{insight_to}"
    acceptance_criteria = _insight_table_sequence(row.get("acceptance criteria")) or (
        "Insight next action is completed or converted into a scoped follow-up with provenance.",
    )
    verification_commands = _insight_table_sequence(row.get("verification commands"))
    blocked_by = _insight_table_sequence(row.get("blocked by"))
    return ProjectTaskCandidate(
        source_id=f"insights-graph-{_slugify(raw_source_id)}",
        source_path=f"{relative_graph_path}:row/{index + 1}",
        title=f"Follow insight: {insight_from} {relation} {insight_to}",
        goal=next_action,
        task_type=task_type,
        acceptance_criteria=acceptance_criteria,
        verification_commands=verification_commands or default_verification_commands,
        allowed_paths=allowed_paths,
        blocked_by=blocked_by,
        source_authority=(relative_graph_path, source, f"confidence:{normalized_confidence}"),
    )


def _insight_allowed_paths(
    root: Path,
    raw_value: object,
    findings: list[str],
) -> tuple[str, ...] | None:
    raw_paths = _insight_table_sequence(raw_value) or ("insights/**",)
    paths: list[str] = []
    for raw_path in raw_paths:
        safe_path = _safe_relative_project_path(root, raw_path)
        if safe_path is None:
            findings.append(f"unsafe insights graph allowed path: {raw_path}.")
            return None
        paths.append(safe_path)
    return tuple(paths)


def _insight_table_sequence(value: object) -> tuple[str, ...]:
    raw_value = _optional_nonblank_string(value)
    if raw_value is None:
        return ()
    normalized = re.sub(r"<br\s*/?>", "\n", raw_value, flags=re.IGNORECASE)
    values: list[str] = []
    for part in re.split(r"\n|;", normalized):
        stripped = part.strip()
        if stripped and stripped != "-":
            values.append(stripped)
    return tuple(values)


def _insight_next_action_is_actionable(value: str) -> bool:
    normalized = value.strip().casefold()
    return normalized not in {"-", "none", "n/a", "no action", "done", "complete"}


def _is_markdown_table_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def _is_markdown_table_separator(line: str) -> bool:
    cells = _split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def _split_table_row(line: str) -> tuple[str, ...]:
    return tuple(cell.strip() for cell in line.strip().strip("|").split("|"))


def _normalize_markdown_table_header(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold()).replace("_", " ")


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


def _markdown_plan_paths(root: Path) -> tuple[tuple[Path, ...], int]:
    paths: list[Path] = []
    seen: set[str] = set()
    for relative_directory in MARKDOWN_PLAN_DIRECTORIES:
        directory = root / relative_directory
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md"), key=lambda candidate: candidate.name.casefold()):
            relative_path = _relative_path(root, path)
            if relative_path in seen:
                continue
            seen.add(relative_path)
            paths.append(path)
    return tuple(paths[:MAX_MARKDOWN_PLAN_FILES]), len(paths)


def _relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _markdown_plan_status(text: str) -> str | None:
    preamble = _markdown_plan_preamble(text)
    return _markdown_field(preamble, "Plan Status")


def _markdown_plan_preamble(text: str) -> str:
    match = MARKDOWN_TASK_HEADING_RE.search(text)
    return text if match is None else text[: match.start()]


def _markdown_field(text: str, label: str) -> str | None:
    match = re.search(rf"^\s*{re.escape(label)}:\s*(.+?)\s*$", text, re.IGNORECASE | re.MULTILINE)
    if match is None:
        return None
    return _optional_nonblank_string(match.group(1))


def _markdown_bullet_section(text: str, heading: str) -> tuple[str, ...]:
    heading_match = re.search(
        rf"^###\s+{re.escape(heading)}\s*$",
        text,
        re.IGNORECASE | re.MULTILINE,
    )
    if heading_match is None:
        return ()
    body_start = heading_match.end()
    next_heading = re.search(r"^#{2,3}\s+", text[body_start:], re.MULTILINE)
    body_end = len(text) if next_heading is None else body_start + next_heading.start()
    values: list[str] = []
    for line in text[body_start:body_end].splitlines():
        stripped = line.strip()
        if not stripped.startswith(("- ", "* ")):
            continue
        value = stripped[2:].strip()
        if value:
            values.append(value)
    return tuple(values)


def _safe_relative_project_path(root: Path, value: object) -> str | None:
    raw_path = _optional_nonblank_string(value)
    if raw_path is None:
        return None
    windows_path = PureWindowsPath(raw_path)
    if windows_path.drive or raw_path.startswith(("/", "\\")):
        return None
    normalized_raw_path = windows_path.as_posix()
    if any(part == ".." for part in normalized_raw_path.split("/")):
        return None
    try:
        resolved_root = root.resolve()
        resolved_path = (root / normalized_raw_path).resolve()
        relative_path = resolved_path.relative_to(resolved_root)
    except OSError, ValueError:
        return None
    normalized = relative_path.as_posix()
    return normalized if normalized and not normalized.startswith("../") else None


def _harness_prompt_file_finding(root: Path, prompt_path: str) -> str | None:
    path = root / prompt_path
    if not path.exists():
        return f"{prompt_path} was not found."
    try:
        size = path.stat().st_size
    except OSError as exc:
        return f"{prompt_path} could not be inspected: {exc}"
    if size > MAX_HARNESS_PROMPT_BYTES:
        return f"{prompt_path} is larger than {MAX_HARNESS_PROMPT_BYTES} bytes."
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return f"{prompt_path} could not be read: {exc}"
    if not text.strip():
        return f"{prompt_path} must be nonblank."
    return None


def _normalized_path_key(path: PurePath) -> str:
    if isinstance(path, PureWindowsPath):
        return path.as_posix().casefold()
    return path.as_posix()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "project"
