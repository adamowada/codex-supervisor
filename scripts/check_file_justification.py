#!/usr/bin/env python3
"""Fail when public files and folders do not fit an intentional bootstrap purpose."""

from __future__ import annotations

import fnmatch
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class PurposeRule:
    name: str
    purpose: str
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class FileJustificationFailure:
    relative_path: str
    reason: str


@dataclass(frozen=True)
class FolderPurposeRule:
    name: str
    purpose: str
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class FilePurpose:
    purpose: str
    verifier: str


PURPOSE_RULES = (
    PurposeRule(
        name="root-bootstrap-files",
        purpose="human and agent bootstrap doctrine, policy, and repo metadata",
        patterns=(
            ".gitattributes",
            ".gitignore",
            ".python-version",
            "AGENTS.md",
            "ARCHITECTURE.md",
            "ATTRIBUTIONS.md",
            "CONTRACTS.md",
            "DECISIONS.md",
            "HANDOFF.md",
            "LICENSE",
            "PLANS.md",
            "README.md",
            "ROADMAP.md",
            "SOP.md",
            "TESTING.md",
            "pyproject.toml",
            "uv.lock",
        ),
    ),
    PurposeRule(
        name="repo-local-skills",
        purpose="Codex bootstrap workflows and small reusable operating procedures",
        patterns=(".agents/skills/**",),
    ),
    PurposeRule(
        name="insights-memory",
        purpose="durable synthesized learning and knowledge graph memory",
        patterns=("insights/**",),
    ),
    PurposeRule(
        name="planning-state",
        purpose="tracked operational planning queue and current task state",
        patterns=("plans/planning.sqlite3",),
    ),
    PurposeRule(
        name="oss-source-index",
        purpose="public index for ignored OSS study sources",
        patterns=("sources/README.md",),
    ),
    PurposeRule(
        name="python-supervisor-package",
        purpose="Python-first supervisor CLI and planning implementation",
        patterns=("src/codex_supervisor/*.py",),
    ),
    PurposeRule(
        name="repo-verification-scripts",
        purpose="deterministic local checks for bootstrap quality and publication readiness",
        patterns=("scripts/*.py",),
    ),
    PurposeRule(
        name="tests",
        purpose="executable regression coverage for supervisor contracts",
        patterns=("tests/test_*.py",),
    ),
)

FILE_PURPOSES = {
    ".gitattributes": FilePurpose(
        "line-ending and binary-file guardrails", "check_protected_files"
    ),
    ".gitignore": FilePurpose(
        "exclude caches, virtualenvs, and ignored source clones", "check_protected_files"
    ),
    ".python-version": FilePurpose(
        "requested latest Python runtime pin", "uv run python --version"
    ),
    ".agents/skills/NOTICE.md": FilePurpose(
        "repo-local skill provenance index", "check_skill_inventory"
    ),
    ".agents/skills/grill-with-docs/ADR-FORMAT.md": FilePurpose(
        "ADR template used by grill-with-docs", "check_skill_inventory"
    ),
    ".agents/skills/grill-with-docs/CONTEXT-FORMAT.md": FilePurpose(
        "context template used by grill-with-docs", "check_skill_inventory"
    ),
    ".agents/skills/diagnose/scripts/hitl-loop.template.sh": FilePurpose(
        "optional POSIX HITL diagnostic template", "check_skill_inventory"
    ),
    ".agents/skills/diagnose/scripts/hitl_loop_template.py": FilePurpose(
        "cross-platform HITL diagnostic template", "check_skill_inventory"
    ),
    ".agents/skills/improve-codebase-architecture/DEEPENING.md": FilePurpose(
        "architecture deepening reference", "check_skill_inventory"
    ),
    ".agents/skills/improve-codebase-architecture/HTML-REPORT.md": FilePurpose(
        "architecture report reference", "check_skill_inventory"
    ),
    ".agents/skills/improve-codebase-architecture/INTERFACE-DESIGN.md": FilePurpose(
        "architecture interface design reference", "check_skill_inventory"
    ),
    ".agents/skills/improve-codebase-architecture/LANGUAGE.md": FilePurpose(
        "architecture language reference", "check_skill_inventory"
    ),
    ".agents/skills/prototype/LOGIC.md": FilePurpose(
        "prototype logic reference", "check_skill_inventory"
    ),
    ".agents/skills/prototype/UI.md": FilePurpose(
        "prototype UI reference", "check_skill_inventory"
    ),
    ".agents/skills/setup-agent-docs/domain.md": FilePurpose(
        "agent docs domain template", "check_skill_inventory"
    ),
    ".agents/skills/setup-agent-docs/issue-tracker-github.md": FilePurpose(
        "agent docs GitHub issue tracker template", "check_skill_inventory"
    ),
    ".agents/skills/setup-agent-docs/issue-tracker-local.md": FilePurpose(
        "agent docs local issue tracker template", "check_skill_inventory"
    ),
    ".agents/skills/setup-agent-docs/source-of-truth.md": FilePurpose(
        "agent docs source-of-truth template", "check_skill_inventory"
    ),
    ".agents/skills/setup-agent-docs/triage-labels.md": FilePurpose(
        "agent docs triage labels template", "check_skill_inventory"
    ),
    ".agents/skills/tdd/deep-modules.md": FilePurpose(
        "TDD deep modules reference", "check_skill_inventory"
    ),
    ".agents/skills/tdd/interface-design.md": FilePurpose(
        "TDD interface design reference", "check_skill_inventory"
    ),
    ".agents/skills/tdd/mocking.md": FilePurpose("TDD mocking reference", "check_skill_inventory"),
    ".agents/skills/tdd/refactoring.md": FilePurpose(
        "TDD refactoring reference", "check_skill_inventory"
    ),
    ".agents/skills/tdd/tests.md": FilePurpose("TDD tests reference", "check_skill_inventory"),
    ".agents/skills/triage/AGENT-BRIEF.md": FilePurpose(
        "triage agent brief template", "check_skill_inventory"
    ),
    ".agents/skills/triage/OUT-OF-SCOPE.md": FilePurpose(
        "triage out-of-scope template", "check_skill_inventory"
    ),
    "AGENTS.md": FilePurpose("agent operating rules and authority matrix", "check_protected_files"),
    "ARCHITECTURE.md": FilePurpose(
        "supervisor architecture source of truth", "check_protected_files"
    ),
    "ATTRIBUTIONS.md": FilePurpose(
        "public reuse rules and copied-material attribution", "check_protected_files"
    ),
    "CONTRACTS.md": FilePurpose(
        "durable task, goal, worker, and project contracts", "check_protected_files"
    ),
    "DECISIONS.md": FilePurpose("stable bootstrap decision record", "check_protected_files"),
    "HANDOFF.md": FilePurpose("mutable fresh-thread handoff snapshot", "manual review"),
    "LICENSE": FilePurpose("repository MIT license", "check_protected_files"),
    "PLANS.md": FilePurpose("planning SQLite contract", "check_protected_files"),
    "README.md": FilePurpose(
        "human-facing project purpose and bootstrap guide", "check_protected_files"
    ),
    "ROADMAP.md": FilePurpose("staged implementation plan", "check_protected_files"),
    "SOP.md": FilePurpose("spawned-project operating procedure", "check_protected_files"),
    "TESTING.md": FilePurpose("verification and coverage policy", "check_protected_files"),
    "insights/README.md": FilePurpose(
        "insight wiki policy and public posture", "check_file_justification"
    ),
    "insights/bootstrap-landmine-audit.md": FilePurpose(
        "bootstrap landmine audit synthesis", "check_planning_integrity"
    ),
    "insights/bootstrap-landmine-worker-result.json": FilePurpose(
        "structured worker-result evidence for completed explorer runs", "check_planning_integrity"
    ),
    "insights/bootstrap-historical-afk-worker-result.json": FilePurpose(
        "structured worker-result evidence for historical completed AFK tasks",
        "check_planning_integrity",
    ),
    "insights/stage6-codex-exec-backend-design-worker-result.json": FilePurpose(
        "structured worker-result evidence for the Stage 6 Codex Exec backend design slice",
        "check_planning_integrity",
    ),
    "insights/stage6a-backend-protocol-worker-result.json": FilePurpose(
        "structured worker-result evidence for the Stage 6A backend protocol slice",
        "check_planning_integrity",
    ),
    "insights/stage6b-codex-exec-preflight-worker-result.json": FilePurpose(
        "structured worker-result evidence for the Stage 6B Codex Exec preflight slice",
        "check_planning_integrity",
    ),
    "insights/stage6c-codex-exec-launch-worker-result.json": FilePurpose(
        "structured worker-result evidence for the Stage 6C Codex Exec launch-path slice",
        "check_planning_integrity",
    ),
    "insights/stage7a-worktree-layout-worker-result.json": FilePurpose(
        "structured worker-result evidence for the Stage 7A worktree layout slice",
        "check_planning_integrity",
    ),
    "insights/stage7b-worker-launch-preparation-worker-result.json": FilePurpose(
        "structured worker-result evidence for the Stage 7B worker launch preparation slice",
        "check_planning_integrity",
    ),
    "insights/codex-usage-skill-synthesis.md": FilePurpose(
        "privacy-safe Codex usage pattern synthesis", "check_public_repo_hygiene"
    ),
    "insights/goal-mode-and-ralph-loop.md": FilePurpose(
        "Goal Mode and Ralph loop synthesis", "check_public_repo_hygiene"
    ),
    "insights/graph.md": FilePurpose("markdown knowledge graph", "check_file_justification"),
    "insights/open-questions.md": FilePurpose(
        "open planning questions", "check_file_justification"
    ),
    "insights/project-sop.md": FilePurpose(
        "spawned-project SOP insight", "check_file_justification"
    ),
    "insights/skill-learning-loop.md": FilePurpose(
        "skill evolution and eval loop doctrine", "check_skill_inventory"
    ),
    "insights/source-index.md": FilePurpose(
        "source corpus usefulness index", "check_source_inventory"
    ),
    "insights/workflow-patterns.md": FilePurpose(
        "workflow pattern synthesis", "check_file_justification"
    ),
    "plans/planning.sqlite3": FilePurpose(
        "tracked operational planning state", "check_planning_integrity"
    ),
    "pyproject.toml": FilePurpose("Python package and tooling configuration", "uv lock --check"),
    "scripts/check_file_justification.py": FilePurpose("public file purpose gate", "pytest"),
    "scripts/check_planning_integrity.py": FilePurpose("planning SQLite integrity gate", "pytest"),
    "scripts/check_protected_files.py": FilePurpose("source lock guard", "pytest"),
    "scripts/check_public_repo_hygiene.py": FilePurpose(
        "public hygiene and publication gate", "pytest"
    ),
    "scripts/check_skill_inventory.py": FilePurpose("repo-local skill inventory gate", "pytest"),
    "scripts/check_source_inventory.py": FilePurpose("source clone inventory gate", "pytest"),
    "scripts/print_protected_hashes.py": FilePurpose("protected hash refresh helper", "pytest"),
    "scripts/verify.py": FilePurpose("aggregated local verification runner", "pytest"),
    "sources/README.md": FilePurpose("ignored source clone inventory", "check_source_inventory"),
    ".agents/skills/worker-result-contract.md": FilePurpose(
        "shared worker-result contract for repo-local skills", "check_skill_inventory"
    ),
    "src/codex_supervisor/__init__.py": FilePurpose("Python package marker", "mypy"),
    "src/codex_supervisor/cli.py": FilePurpose("codex-supervisor CLI", "pytest"),
    "src/codex_supervisor/goal_contracts.py": FilePurpose("Goal Contract renderer", "pytest"),
    "src/codex_supervisor/locks.py": FilePurpose("protected file lock helpers", "pytest"),
    "src/codex_supervisor/paths.py": FilePurpose("repo/planning path discovery", "pytest"),
    "src/codex_supervisor/planning.py": FilePurpose("SQLite planning store", "pytest"),
    "src/codex_supervisor/story_loop.py": FilePurpose("Story Loop queue state machine", "pytest"),
    "src/codex_supervisor/worker_backends.py": FilePurpose(
        "worker backend protocol and fake backend", "pytest"
    ),
    "src/codex_supervisor/worker_launches.py": FilePurpose(
        "worker launch request preparation", "pytest"
    ),
    "src/codex_supervisor/worker_results.py": FilePurpose(
        "Worker Result Contract validation", "pytest"
    ),
    "src/codex_supervisor/worktree_artifacts.py": FilePurpose(
        "worktree and run-artifact path guards", "pytest"
    ),
    "tests/test_file_justification.py": FilePurpose("file purpose gate tests", "pytest"),
    "tests/test_goal_contracts.py": FilePurpose("Goal Contract renderer tests", "pytest"),
    "tests/test_locks.py": FilePurpose("protected lock helper tests", "pytest"),
    "tests/test_planning.py": FilePurpose("planning store and CLI tests", "pytest"),
    "tests/test_planning_integrity.py": FilePurpose("planning integrity gate tests", "pytest"),
    "tests/test_public_repo_hygiene.py": FilePurpose("public hygiene gate tests", "pytest"),
    "tests/test_skill_inventory.py": FilePurpose("skill inventory gate tests", "pytest"),
    "tests/test_source_inventory.py": FilePurpose("source inventory gate tests", "pytest"),
    "tests/test_story_loop.py": FilePurpose("Story Loop tests", "pytest"),
    "tests/test_worker_backends.py": FilePurpose("worker backend protocol tests", "pytest"),
    "tests/test_worker_launches.py": FilePurpose(
        "worker launch request preparation tests", "pytest"
    ),
    "tests/test_worker_results.py": FilePurpose("worker result validation tests", "pytest"),
    "tests/test_worktree_artifacts.py": FilePurpose(
        "worktree and run-artifact guard tests", "pytest"
    ),
    "tests/test_verify_script.py": FilePurpose("verification runner tests", "pytest"),
    "uv.lock": FilePurpose("locked development dependency graph", "uv lock --check"),
}

ALLOWED_FILE_PURPOSE_VERIFIERS = frozenset(
    {
        "check_file_justification",
        "check_planning_integrity",
        "check_protected_files",
        "check_public_repo_hygiene",
        "check_skill_inventory",
        "check_source_inventory",
        "mypy",
        "pytest",
        "uv lock --check",
        "uv run python --version",
    }
)

REQUIRED_PYTHON_MARKERS = {
    "scripts/check_file_justification.py": "check_file_justification",
    "scripts/check_planning_integrity.py": "check_planning_integrity",
    "scripts/check_protected_files.py": "PROTECTED_FILE_HASHES",
    "scripts/check_public_repo_hygiene.py": "_check_publication_ready",
    "scripts/check_skill_inventory.py": "check_skill_inventory",
    "scripts/check_source_inventory.py": "check_source_inventory",
    "scripts/print_protected_hashes.py": "PROTECTED_FILE_HASHES",
    "scripts/verify.py": "BASE_COMMANDS",
    "src/codex_supervisor/cli.py": "def main",
    "src/codex_supervisor/goal_contracts.py": "render_goal_contract",
    "src/codex_supervisor/locks.py": "PROTECTED_FILES",
    "src/codex_supervisor/paths.py": "default_planning_database_path",
    "src/codex_supervisor/planning.py": "PlanningSQLiteStore",
    "src/codex_supervisor/story_loop.py": "build_story_loop_status",
}

FOLDER_PURPOSE_RULES = (
    FolderPurposeRule(
        name="repo-local-skills",
        purpose="Codex bootstrap workflows and small reusable operating procedures",
        patterns=(".agents", ".agents/skills", ".agents/skills/**"),
    ),
    FolderPurposeRule(
        name="insights-memory",
        purpose="durable synthesized learning and knowledge graph memory",
        patterns=("insights", "insights/**"),
    ),
    FolderPurposeRule(
        name="planning-state",
        purpose="tracked operational planning queue and current task state",
        patterns=("plans",),
    ),
    FolderPurposeRule(
        name="oss-source-index",
        purpose="public index for ignored OSS study sources",
        patterns=("sources",),
    ),
    FolderPurposeRule(
        name="repo-verification-scripts",
        purpose="deterministic local checks for bootstrap quality and publication readiness",
        patterns=("scripts",),
    ),
    FolderPurposeRule(
        name="python-supervisor-package",
        purpose="Python-first supervisor implementation package",
        patterns=("src", "src/codex_supervisor"),
    ),
    FolderPurposeRule(
        name="tests",
        purpose="executable regression coverage for supervisor contracts",
        patterns=("tests",),
    ),
)

TEXT_SUFFIXES = {
    ".md",
    ".json",
    ".lock",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
TEXT_FILENAMES = {
    ".gitattributes",
    ".gitignore",
    ".python-version",
    "LICENSE",
}


def main() -> int:
    failures = check_file_justification(REPO_ROOT)
    if failures:
        print("File justification checks failed.", file=sys.stderr)
        for failure in failures:
            print(f"- {failure.relative_path}: {failure.reason}", file=sys.stderr)
        return 1
    print("File justification checks passed.")
    return 0


def check_file_justification(repo_root: Path) -> tuple[FileJustificationFailure, ...]:
    failures: list[FileJustificationFailure] = []
    failures.extend(_file_purpose_manifest_failures(repo_root))
    failures.extend(_deleted_tracked_public_file_failures(repo_root))
    relative_paths = _candidate_public_files(repo_root)
    for relative_path in _candidate_public_folders(relative_paths):
        if _folder_purpose_for_path(relative_path) is None:
            failures.append(
                FileJustificationFailure(
                    relative_path,
                    "folder does not match any intentional public-folder purpose category",
                )
            )
    for relative_path in relative_paths:
        if _purpose_for_path(relative_path) is None:
            failures.append(
                FileJustificationFailure(
                    relative_path,
                    "does not match any intentional public-file purpose category",
                )
            )
            continue
        if relative_path not in FILE_PURPOSES and not _is_skill_primary_file(relative_path):
            failures.append(
                FileJustificationFailure(
                    relative_path,
                    "does not have a file-level purpose entry",
                )
            )
        path = repo_root / relative_path
        if _invalid_text_file_reason(path) is not None:
            failures.append(
                FileJustificationFailure(relative_path, "public text file is not valid UTF-8")
            )
        if _is_empty_text_file(path):
            failures.append(FileJustificationFailure(relative_path, "public text file is empty"))
        marker = REQUIRED_PYTHON_MARKERS.get(relative_path)
        if marker is not None and not _text_file_contains(path, marker):
            failures.append(
                FileJustificationFailure(
                    relative_path,
                    f"missing required purpose marker: {marker}",
                )
            )
    return tuple(failures)


def _is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_FILENAMES


def _invalid_text_file_reason(path: Path) -> str | None:
    if not _is_text_candidate(path):
        return None
    try:
        path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return str(exc)
    except FileNotFoundError, OSError:
        return None
    return None


def _candidate_public_files(repo_root: Path) -> tuple[str, ...]:
    completed = subprocess.run(
        ("git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"),
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=False,
    )
    paths: list[str] = []
    for item in completed.stdout.split(b"\0"):
        if not item:
            continue
        relative_path = item.decode("utf-8").replace("\\", "/")
        if (repo_root / relative_path).is_file():
            paths.append(relative_path)
    return tuple(paths)


def _deleted_tracked_public_file_failures(repo_root: Path) -> tuple[FileJustificationFailure, ...]:
    completed = subprocess.run(
        ("git", "ls-files", "-z", "--deleted"),
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=False,
    )
    failures: list[FileJustificationFailure] = []
    for item in completed.stdout.split(b"\0"):
        if not item:
            continue
        relative_path = item.decode("utf-8").replace("\\", "/")
        failures.append(
            FileJustificationFailure(
                relative_path,
                "tracked file is deleted in the working tree; stage the deletion or restore it",
            )
        )
    return tuple(failures)


def _purpose_for_path(relative_path: str) -> PurposeRule | None:
    normalized = relative_path.replace("\\", "/")
    for rule in PURPOSE_RULES:
        if any(fnmatch.fnmatchcase(normalized, pattern) for pattern in rule.patterns):
            return rule
    return None


def _candidate_public_folders(relative_paths: tuple[str, ...]) -> tuple[str, ...]:
    folders: set[str] = set()
    for relative_path in relative_paths:
        parent = Path(relative_path).parent
        while str(parent) not in {"", "."}:
            folders.add(parent.as_posix())
            parent = parent.parent
    return tuple(sorted(folders))


def _folder_purpose_for_path(relative_path: str) -> FolderPurposeRule | None:
    normalized = relative_path.replace("\\", "/")
    for rule in FOLDER_PURPOSE_RULES:
        if any(fnmatch.fnmatchcase(normalized, pattern) for pattern in rule.patterns):
            return rule
    return None


def _is_empty_text_file(path: Path) -> bool:
    if not _is_text_candidate(path):
        return False
    try:
        return path.read_text(encoding="utf-8").strip() == ""
    except FileNotFoundError:
        return False
    except OSError:
        return False
    except UnicodeDecodeError:
        return False


def _file_purpose_manifest_failures(repo_root: Path) -> tuple[FileJustificationFailure, ...]:
    public_files = set(_candidate_public_files(repo_root))
    failures: list[FileJustificationFailure] = []
    for relative_path, purpose in sorted(FILE_PURPOSES.items()):
        if purpose.verifier == "manual review" and relative_path == "HANDOFF.md":
            continue
        if purpose.verifier not in ALLOWED_FILE_PURPOSE_VERIFIERS:
            failures.append(
                FileJustificationFailure(
                    relative_path,
                    f"file-level purpose verifier {purpose.verifier!r} is not an allowed gate",
                )
            )
        if repo_root.resolve() == REPO_ROOT.resolve() and relative_path not in public_files:
            failures.append(
                FileJustificationFailure(
                    relative_path,
                    "file-level purpose entry is stale; path is not a public candidate",
                )
            )
    return tuple(failures)


def _is_skill_primary_file(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    return normalized.startswith(".agents/skills/") and normalized.endswith("/SKILL.md")


def _text_file_contains(path: Path, marker: str) -> bool:
    try:
        return marker in path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    except OSError:
        return False
    except UnicodeDecodeError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
