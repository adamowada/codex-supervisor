"""Release readiness audit contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_supervisor.planning import open_existing_planning_database

RELEASE_READINESS_SECTIONS = (
    "cli",
    "mcp",
    "plugin",
    "project_scaffold",
    "verification",
    "documentation",
    "os_validation",
)
RELEASE_VALIDATION_EVENT_TYPE = "release_validation_recorded"


@dataclass(frozen=True)
class ReleaseReadinessCheck:
    section: str
    name: str
    status: str
    evidence: tuple[str, ...]
    next_action: str


@dataclass(frozen=True)
class ReleaseReadinessReport:
    repo_root: str
    ready: bool
    checks: tuple[ReleaseReadinessCheck, ...]
    passing_checks: int
    gap_checks: int


@dataclass(frozen=True)
class ReleaseValidationEvidence:
    progress_id: str
    commands: tuple[str, ...]
    environment: tuple[str, ...]


def build_release_readiness_report(
    repo_root: Path | None = None,
    *,
    planning_db_path: Path | None = None,
) -> ReleaseReadinessReport:
    """Inspect repo-owned release evidence without running checks or contacting remotes."""

    root = (repo_root or Path.cwd()).resolve()
    planning_path = planning_db_path or root / "plans" / "planning.sqlite3"
    checks = (
        _cli_check(root),
        _mcp_check(root),
        _plugin_check(root),
        _project_scaffold_check(root),
        _publication_verification_check(root),
        _integrity_gate_check(root),
        _documentation_check(root),
        _linux_ci_check(root),
        _external_os_validation_check(root, planning_path),
    )
    passing_checks = sum(1 for check in checks if check.status == "pass")
    gap_checks = sum(1 for check in checks if check.status == "gap")
    return ReleaseReadinessReport(
        repo_root=str(root),
        ready=gap_checks == 0,
        checks=checks,
        passing_checks=passing_checks,
        gap_checks=gap_checks,
    )


def _cli_check(root: Path) -> ReleaseReadinessCheck:
    pyproject = _text(root / "pyproject.toml")
    cli = root / "src" / "codex_supervisor" / "cli.py"
    has_script = 'codex-supervisor = "codex_supervisor.cli:main"' in pyproject
    has_cli = cli.exists()
    return _check(
        section="cli",
        name="Package CLI entry point",
        passed=has_cli and has_script,
        evidence=(
            _evidence("pyproject.toml declares the codex-supervisor console script", has_script),
            _evidence("src/codex_supervisor/cli.py exists", has_cli),
        ),
        next_action="Restore the project script and CLI module before release.",
    )


def _mcp_check(root: Path) -> ReleaseReadinessCheck:
    paths = (
        root / "src" / "codex_supervisor" / "mcp_server.py",
        root / "src" / "codex_supervisor" / "mcp_stdio.py",
        root / "tests" / "test_mcp_server.py",
        root / "tests" / "test_mcp_stdio.py",
    )
    return _path_check(
        root=root,
        section="mcp",
        name="MCP server and stdio tests",
        paths=paths,
        next_action="Restore MCP server, stdio transport, and tests before release.",
    )


def _plugin_check(root: Path) -> ReleaseReadinessCheck:
    paths = (
        root / "plugins" / "codex-supervisor" / ".codex-plugin" / "plugin.json",
        root / "plugins" / "codex-supervisor" / ".mcp.json",
        root / "plugins" / "codex-supervisor" / "README.md",
        root / "plugins" / "codex-supervisor" / "skills" / "codex-supervisor" / "SKILL.md",
    )
    return _path_check(
        root=root,
        section="plugin",
        name="Codex Desktop plugin surface",
        paths=paths,
        next_action="Restore plugin metadata, MCP wiring, README, and packaged skill.",
    )


def _project_scaffold_check(root: Path) -> ReleaseReadinessCheck:
    cli = _text(root / "src" / "codex_supervisor" / "cli.py")
    paths = (
        root / "src" / "codex_supervisor" / "spawned_projects.py",
        root / "tests" / "test_spawned_projects.py",
    )
    has_model = paths[0].exists()
    has_tests = paths[1].exists()
    has_classify = "spawned-project-classify" in cli
    has_propose = "spawned-project-propose" in cli
    passed = has_model and has_tests and has_classify and has_propose
    return _check(
        section="project_scaffold",
        name="Spawned-project dry-run scaffold surface",
        passed=passed,
        evidence=(
            _evidence("src/codex_supervisor/spawned_projects.py exists", has_model),
            _evidence("tests/test_spawned_projects.py exists", has_tests),
            _evidence("CLI exposes spawned-project-classify", has_classify),
            _evidence("CLI exposes spawned-project-propose", has_propose),
        ),
        next_action="Restore spawned-project classifier/proposal model, CLI commands, and tests.",
    )


def _publication_verification_check(root: Path) -> ReleaseReadinessCheck:
    workflow = _text(root / ".github" / "workflows" / "verify.yml")
    verify = root / "scripts" / "verify.py"
    has_verify = verify.exists()
    has_publication_gate = "scripts/verify.py --publication-ready" in workflow
    passed = has_verify and has_publication_gate
    return _check(
        section="verification",
        name="Publication-ready verification posture",
        passed=passed,
        evidence=(
            _evidence("scripts/verify.py exists", has_verify),
            _evidence(
                ".github/workflows/verify.yml runs scripts/verify.py --publication-ready",
                has_publication_gate,
            ),
        ),
        next_action="Restore the publication-ready verifier and GitHub Actions workflow.",
    )


def _integrity_gate_check(root: Path) -> ReleaseReadinessCheck:
    paths = (
        root / "scripts" / "check_public_repo_hygiene.py",
        root / "scripts" / "check_planning_integrity.py",
        root / "scripts" / "check_protected_files.py",
        root / "scripts" / "check_skill_inventory.py",
        root / "plans" / "planning.sqlite3",
    )
    return _path_check(
        root=root,
        section="verification",
        name="Integrity and hygiene gates",
        paths=paths,
        next_action="Restore public hygiene, planning integrity, source-lock, skill, and DB gates.",
    )


def _documentation_check(root: Path) -> ReleaseReadinessCheck:
    readme = _text(root / "README.md")
    testing = _text(root / "TESTING.md")
    plugin_readme = _text(root / "plugins" / "codex-supervisor" / "README.md")
    sop = _text(root / "SOP.md")
    has_dependency_setup = "uv sync --dev" in readme
    has_cli_docs = "codex-supervisor" in readme
    has_mcp_docs = "MCP" in readme
    has_plugin_docs = "plugin" in plugin_readme
    has_publication_docs = "scripts/verify.py --publication-ready" in testing
    has_scaffold_docs = "spawned" in sop
    passed = all(
        (
            has_dependency_setup,
            has_cli_docs,
            has_mcp_docs,
            has_plugin_docs,
            has_publication_docs,
            has_scaffold_docs,
        )
    )
    return _check(
        section="documentation",
        name="Install, run, plugin, and scaffold docs",
        passed=passed,
        evidence=(
            _evidence("README.md documents dependency setup", has_dependency_setup),
            _evidence("README.md documents CLI queue commands", has_cli_docs),
            _evidence("README.md documents MCP surface", has_mcp_docs),
            _evidence(
                "plugins/codex-supervisor/README.md documents plugin use",
                has_plugin_docs,
            ),
            _evidence(
                "TESTING.md documents publication-ready verification",
                has_publication_docs,
            ),
            _evidence("SOP.md documents spawned-project scaffold policy", has_scaffold_docs),
        ),
        next_action="Add release-facing install, CLI, MCP/plugin, verification, and scaffold docs.",
    )


def _linux_ci_check(root: Path) -> ReleaseReadinessCheck:
    workflow = _text(root / ".github" / "workflows" / "verify.yml")
    has_ubuntu = "runs-on: ubuntu-latest" in workflow
    has_python = 'python-version: "3.14"' in workflow
    return _check(
        section="os_validation",
        name="Linux CI validation surface",
        passed=has_ubuntu and has_python,
        evidence=(
            _evidence(".github/workflows/verify.yml runs on ubuntu-latest", has_ubuntu),
            _evidence("GitHub Actions config sets up Python 3.14", has_python),
        ),
        next_action="Restore Linux CI validation for the publication-ready gate.",
    )


def _external_os_validation_check(root: Path, planning_db_path: Path) -> ReleaseReadinessCheck:
    evidence = _windows_validation_evidence(planning_db_path)
    if evidence is not None:
        return _check(
            section="os_validation",
            name="External Windows install validation evidence",
            passed=True,
            evidence=(
                f"present: {RELEASE_VALIDATION_EVENT_TYPE} {evidence.progress_id} "
                "records reviewed Windows setup validation",
                *(f"present: command passed: {command}" for command in evidence.commands),
                *(f"present: environment: {fact}" for fact in evidence.environment),
            ),
            next_action=(
                "Run and record a bounded Windows install validation artifact before "
                "tagging release."
            ),
        )
    return _check(
        section="os_validation",
        name="External Windows install validation evidence",
        passed=False,
        evidence=_windows_validation_gap_evidence(root, planning_db_path),
        next_action=(
            "Run and record a bounded Windows install validation artifact before tagging release."
        ),
    )


def _windows_validation_evidence(planning_db_path: Path) -> ReleaseValidationEvidence | None:
    if not planning_db_path.exists():
        return None
    try:
        store = open_existing_planning_database(planning_db_path, read_only=True)
        progress_events = store.list_plan_progress()
    except Exception:
        return None
    for progress in progress_events:
        if progress.event_type != RELEASE_VALIDATION_EVENT_TYPE:
            continue
        details = _json_object(progress.details)
        platform = str(details.get("platform", "")).casefold()
        status = str(details.get("status", "")).casefold()
        reviewed = details.get("reviewed") is True
        commands = _string_tuple(details.get("commands"))
        if platform != "windows" or status != "passed" or not reviewed or not commands:
            continue
        return ReleaseValidationEvidence(
            progress_id=progress.progress_id,
            commands=commands,
            environment=_environment_facts(details.get("environment")),
        )
    return None


def _windows_validation_gap_evidence(root: Path, planning_db_path: Path) -> tuple[str, ...]:
    evidence = []
    if planning_db_path.exists():
        evidence.append(f"present: {_relative(root, planning_db_path)}")
    else:
        evidence.append(f"missing: {_relative(root, planning_db_path)}")
    evidence.append(
        "missing: release_validation_recorded progress with platform=windows, status=passed, "
        "reviewed=true, and at least one command"
    )
    return tuple(evidence)


def _path_check(
    *,
    root: Path,
    section: str,
    name: str,
    paths: tuple[Path, ...],
    next_action: str,
    require_any: bool = False,
) -> ReleaseReadinessCheck:
    existing = tuple(path for path in paths if path.exists())
    missing = tuple(path for path in paths if not path.exists())
    passed = bool(existing) if require_any else len(existing) == len(paths)
    evidence = tuple(f"present: {_relative(root, path)}" for path in existing) + tuple(
        f"missing: {_relative(root, path)}" for path in missing
    )
    return _check(
        section=section,
        name=name,
        passed=passed,
        evidence=evidence,
        next_action=next_action,
    )


def _check(
    *,
    section: str,
    name: str,
    passed: bool,
    evidence: tuple[str, ...],
    next_action: str,
) -> ReleaseReadinessCheck:
    return ReleaseReadinessCheck(
        section=section,
        name=name,
        status="pass" if passed else "gap",
        evidence=evidence,
        next_action="" if passed else next_action,
    )


def _evidence(description: str, present: bool) -> str:
    prefix = "present" if present else "missing"
    return f"{prefix}: {description}"


def _json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    strings = tuple(item for item in value if isinstance(item, str) and item.strip())
    if len(strings) != len(value):
        return ()
    return strings


def _environment_facts(value: object) -> tuple[str, ...]:
    if not isinstance(value, dict):
        return ()
    facts = []
    for key, item in sorted(value.items()):
        if isinstance(key, str) and isinstance(item, str) and item.strip():
            facts.append(f"{key}={item}")
    return tuple(facts)


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _relative(root: Path, path: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
        return relative.as_posix()
    except ValueError:
        return path.as_posix()
