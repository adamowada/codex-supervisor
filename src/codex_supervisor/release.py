"""Release readiness audit contracts."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_supervisor.planning import PlanProgressRecord, open_existing_planning_database

RELEASE_READINESS_SECTIONS = (
    "cli",
    "mcp",
    "plugin",
    "project_scaffold",
    "ci",
    "live_evidence",
    "verification",
    "documentation",
    "os_validation",
)
RELEASE_VALIDATION_EVENT_TYPE = "release_validation_recorded"
CI_RUN_EVENT_TYPE = "ci_run_recorded"
PUBLICATION_READY_EVENT_TYPE = "publication_ready_verification_recorded"
LIVE_WORKER_SMOKE_EVENT_TYPE = "live_worker_smoke_recorded"
LIVE_REVIEW_SMOKE_EVENT_TYPE = "live_review_smoke_recorded"
MUTATING_MCP_SMOKE_EVENT_TYPE = "mutating_mcp_smoke_recorded"
REAL_PROJECT_BOOTSTRAP_SMOKE_EVENT_TYPE = "real_project_bootstrap_smoke_recorded"
EVIDENCE_ONLY_RELEASE_PATHS = frozenset(
    {
        "HANDOFF.md",
        "plans/planning.sqlite3",
    }
)
EVIDENCE_ONLY_RELEASE_PREFIXES = ("insights/",)


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
    target_commit: str | None
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
    target_commit: str | None = None,
) -> ReleaseReadinessReport:
    """Inspect repo-owned release evidence without running checks or contacting remotes."""

    root = (repo_root or Path.cwd()).resolve()
    planning_path = planning_db_path or root / "plans" / "planning.sqlite3"
    resolved_target_commit = _resolve_target_commit(root, target_commit)
    progress_events = _planning_progress(planning_path)
    checks = (
        _cli_check(root),
        _mcp_check(root),
        _plugin_check(root),
        _project_scaffold_check(root),
        _project_scaffold_apply_check(root),
        _current_ci_check(progress_events, resolved_target_commit, planning_path),
        _publication_verification_check(root),
        _current_publication_verification_check(
            progress_events,
            resolved_target_commit,
            planning_path,
        ),
        _integrity_gate_check(root),
        _documentation_check(root),
        _linux_ci_check(root),
        _external_os_validation_check(
            root,
            planning_path,
            progress_events,
            resolved_target_commit,
        ),
        _live_worker_smoke_check(progress_events, resolved_target_commit, planning_path),
        _live_review_smoke_check(progress_events, resolved_target_commit, planning_path),
        _mutating_mcp_smoke_check(progress_events, resolved_target_commit, planning_path),
        _real_project_bootstrap_smoke_check(
            progress_events,
            resolved_target_commit,
            planning_path,
        ),
    )
    passing_checks = sum(1 for check in checks if check.status == "pass")
    gap_checks = sum(1 for check in checks if check.status == "gap")
    return ReleaseReadinessReport(
        repo_root=str(root),
        target_commit=resolved_target_commit,
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


def _project_scaffold_apply_check(root: Path) -> ReleaseReadinessCheck:
    cli = _text(root / "src" / "codex_supervisor" / "cli.py")
    spawned_projects = _text(root / "src" / "codex_supervisor" / "spawned_projects.py")
    tests = _text(root / "tests" / "test_spawned_projects.py")
    has_apply_cli = "spawned-project-apply" in cli
    has_apply_service = "def apply_spawned_project_scaffold" in spawned_projects
    has_apply_tests = "spawned_project_apply" in tests
    passed = has_apply_cli and has_apply_service and has_apply_tests
    return _check(
        section="project_scaffold",
        name="Spawned-project apply surface",
        passed=passed,
        evidence=(
            _evidence("CLI exposes spawned-project-apply", has_apply_cli),
            _evidence(
                "src/codex_supervisor/spawned_projects.py writes selected scaffolds",
                has_apply_service,
            ),
            _evidence("tests cover spawned-project apply behavior", has_apply_tests),
        ),
        next_action=(
            "Restore the spawned-project apply command, scaffold writer, and apply tests."
        ),
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


def _current_ci_check(
    progress_events: tuple[PlanProgressRecord, ...],
    target_commit: str | None,
    planning_db_path: Path,
) -> ReleaseReadinessCheck:
    if target_commit is None:
        return _missing_target_commit_check(
            section="ci",
            name="Current successful CI for target commit",
        )
    matching, stale = _matching_progress_events(
        progress_events,
        event_type=CI_RUN_EVENT_TYPE,
        target_commit=target_commit,
    )
    valid = []
    for progress, details in matching:
        status = str(details.get("status", "")).casefold()
        conclusion = str(details.get("conclusion", "")).casefold()
        if status == "completed" and conclusion == "success":
            valid.append((progress, details))
    if valid:
        progress, details = valid[0]
        run_url = details.get("run_url")
        evidence = [
            f"present: {CI_RUN_EVENT_TYPE} {progress.progress_id} records successful CI "
            f"for {target_commit}",
        ]
        if isinstance(run_url, str) and run_url.strip():
            evidence.append(f"present: run_url: {run_url}")
        return _check(
            section="ci",
            name="Current successful CI for target commit",
            passed=True,
            evidence=tuple(evidence),
            next_action="Record successful GitHub Actions evidence for the target commit.",
        )
    return _check(
        section="ci",
        name="Current successful CI for target commit",
        passed=False,
        evidence=_current_evidence_gap(
            planning_db_path,
            event_type=CI_RUN_EVENT_TYPE,
            target_commit=target_commit,
            stale=stale,
            current_count=len(matching),
            missing=(
                "missing: ci_run_recorded progress with matching head_sha, "
                "status=completed, and conclusion=success"
            ),
        ),
        next_action="Record successful GitHub Actions evidence for the target commit.",
    )


def _current_publication_verification_check(
    progress_events: tuple[PlanProgressRecord, ...],
    target_commit: str | None,
    planning_db_path: Path,
) -> ReleaseReadinessCheck:
    return _release_progress_evidence_check(
        progress_events,
        target_commit,
        planning_db_path,
        section="verification",
        name="Current publication-ready verification evidence",
        event_type=PUBLICATION_READY_EVENT_TYPE,
        command_fragment="scripts/verify.py --publication-ready",
        next_action=(
            "Record publication_ready_verification_recorded evidence for the target commit."
        ),
    )


def _external_os_validation_check(
    root: Path,
    planning_db_path: Path,
    progress_events: tuple[PlanProgressRecord, ...],
    target_commit: str | None,
) -> ReleaseReadinessCheck:
    evidence = _windows_validation_evidence(progress_events, target_commit)
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
    evidence_items: tuple[str, ...]
    if target_commit is None:
        evidence_items = ("missing: target commit could not be resolved",)
    else:
        evidence_items = _windows_validation_gap_evidence(
            root,
            planning_db_path,
            progress_events,
            target_commit,
        )
    return _check(
        section="os_validation",
        name="External Windows install validation evidence",
        passed=False,
        evidence=evidence_items,
        next_action=(
            "Run and record a bounded Windows install validation artifact before tagging release."
        ),
    )


def _live_worker_smoke_check(
    progress_events: tuple[PlanProgressRecord, ...],
    target_commit: str | None,
    planning_db_path: Path,
) -> ReleaseReadinessCheck:
    return _release_progress_evidence_check(
        progress_events,
        target_commit,
        planning_db_path,
        section="live_evidence",
        name="Live worker smoke evidence",
        event_type=LIVE_WORKER_SMOKE_EVENT_TYPE,
        required_truthy=("live",),
        next_action="Record live_worker_smoke_recorded evidence for the target commit.",
    )


def _live_review_smoke_check(
    progress_events: tuple[PlanProgressRecord, ...],
    target_commit: str | None,
    planning_db_path: Path,
) -> ReleaseReadinessCheck:
    return _release_progress_evidence_check(
        progress_events,
        target_commit,
        planning_db_path,
        section="live_evidence",
        name="Live review smoke evidence",
        event_type=LIVE_REVIEW_SMOKE_EVENT_TYPE,
        required_truthy=("live",),
        next_action="Record live_review_smoke_recorded evidence for the target commit.",
    )


def _mutating_mcp_smoke_check(
    progress_events: tuple[PlanProgressRecord, ...],
    target_commit: str | None,
    planning_db_path: Path,
) -> ReleaseReadinessCheck:
    return _release_progress_evidence_check(
        progress_events,
        target_commit,
        planning_db_path,
        section="live_evidence",
        name="Mutating MCP smoke evidence",
        event_type=MUTATING_MCP_SMOKE_EVENT_TYPE,
        required_truthy=("mutating",),
        next_action="Record mutating_mcp_smoke_recorded evidence for the target commit.",
    )


def _real_project_bootstrap_smoke_check(
    progress_events: tuple[PlanProgressRecord, ...],
    target_commit: str | None,
    planning_db_path: Path,
) -> ReleaseReadinessCheck:
    return _release_progress_evidence_check(
        progress_events,
        target_commit,
        planning_db_path,
        section="live_evidence",
        name="Real project bootstrap smoke evidence",
        event_type=REAL_PROJECT_BOOTSTRAP_SMOKE_EVENT_TYPE,
        required_truthy=("writes_files",),
        next_action=(
            "Record real_project_bootstrap_smoke_recorded evidence for the target commit."
        ),
    )


def _windows_validation_evidence(
    progress_events: tuple[PlanProgressRecord, ...],
    target_commit: str | None,
) -> ReleaseValidationEvidence | None:
    if target_commit is None:
        return None
    for progress in progress_events:
        if progress.event_type != RELEASE_VALIDATION_EVENT_TYPE:
            continue
        details = _json_object(progress.details)
        platform = str(details.get("platform", "")).casefold()
        status = str(details.get("status", "")).casefold()
        reviewed = details.get("reviewed") is True
        commands = _string_tuple(details.get("commands"))
        head_sha = _details_head_sha(details)
        if (
            platform != "windows"
            or status != "passed"
            or not reviewed
            or not commands
            or head_sha != target_commit
        ):
            continue
        return ReleaseValidationEvidence(
            progress_id=progress.progress_id,
            commands=commands,
            environment=_environment_facts(details.get("environment")),
        )
    return None


def _windows_validation_gap_evidence(
    root: Path,
    planning_db_path: Path,
    progress_events: tuple[PlanProgressRecord, ...],
    target_commit: str,
) -> tuple[str, ...]:
    evidence = []
    if planning_db_path.exists():
        evidence.append(f"present: {_relative(root, planning_db_path)}")
    else:
        evidence.append(f"missing: {_relative(root, planning_db_path)}")
    matching, stale = _matching_progress_events(
        progress_events,
        event_type=RELEASE_VALIDATION_EVENT_TYPE,
        target_commit=target_commit,
    )
    evidence.extend(_stale_evidence(stale))
    if matching:
        evidence.append(
            "missing: matching release_validation_recorded progress also needs "
            "platform=windows, status=passed, reviewed=true, and at least one command"
        )
    evidence.append(
        "missing: release_validation_recorded progress with platform=windows, status=passed, "
        f"reviewed=true, head_sha={target_commit}, and at least one command"
    )
    return tuple(evidence)


def _release_progress_evidence_check(
    progress_events: tuple[PlanProgressRecord, ...],
    target_commit: str | None,
    planning_db_path: Path,
    *,
    section: str,
    name: str,
    event_type: str,
    next_action: str,
    required_truthy: tuple[str, ...] = (),
    command_fragment: str | None = None,
) -> ReleaseReadinessCheck:
    if target_commit is None:
        return _missing_target_commit_check(section=section, name=name)
    matching, stale = _matching_progress_events(
        progress_events,
        event_type=event_type,
        target_commit=target_commit,
    )
    valid: list[tuple[PlanProgressRecord, dict[str, Any]]] = []
    for progress, details in matching:
        commands = _string_tuple(details.get("commands"))
        if not _release_status_passed(details):
            continue
        if not commands:
            continue
        if command_fragment and not any(command_fragment in command for command in commands):
            continue
        if any(details.get(field_name) is not True for field_name in required_truthy):
            continue
        valid.append((progress, details))
    if valid:
        progress, details = valid[0]
        commands = _string_tuple(details.get("commands"))
        truthy_evidence = tuple(f"present: {field_name}=true" for field_name in required_truthy)
        return _check(
            section=section,
            name=name,
            passed=True,
            evidence=(
                f"present: {event_type} {progress.progress_id} records current evidence "
                f"for {target_commit}",
                *(f"present: command passed: {command}" for command in commands),
                *truthy_evidence,
            ),
            next_action=next_action,
        )
    missing = (
        f"missing: {event_type} progress with status=passed, head_sha={target_commit}, "
        "and at least one command"
    )
    if command_fragment:
        missing += f" including {command_fragment}"
    for field_name in required_truthy:
        missing += f", {field_name}=true"
    return _check(
        section=section,
        name=name,
        passed=False,
        evidence=_current_evidence_gap(
            planning_db_path,
            event_type=event_type,
            target_commit=target_commit,
            stale=stale,
            current_count=len(matching),
            missing=missing,
        ),
        next_action=next_action,
    )


def _missing_target_commit_check(*, section: str, name: str) -> ReleaseReadinessCheck:
    return _check(
        section=section,
        name=name,
        passed=False,
        evidence=("missing: target commit could not be resolved",),
        next_action="Provide --commit or run release-readiness from a Git checkout.",
    )


def _current_evidence_gap(
    planning_db_path: Path,
    *,
    event_type: str,
    target_commit: str,
    stale: tuple[tuple[PlanProgressRecord, str], ...],
    current_count: int,
    missing: str,
) -> tuple[str, ...]:
    evidence = []
    db_label = planning_db_path.name or "planning database"
    if planning_db_path.exists():
        evidence.append(f"present: planning database {db_label}")
    else:
        evidence.append(f"missing: planning database {db_label}")
    evidence.extend(_stale_evidence(stale))
    if current_count:
        evidence.append(
            f"missing: {event_type} progress for {target_commit} did not satisfy "
            "the release evidence schema"
        )
    evidence.append(missing)
    return tuple(evidence)


def _stale_evidence(
    stale: tuple[tuple[PlanProgressRecord, str], ...],
) -> tuple[str, ...]:
    return tuple(
        f"stale: {progress.event_type} {progress.progress_id} targets {head_sha}"
        for progress, head_sha in stale
    )


def _matching_progress_events(
    progress_events: tuple[PlanProgressRecord, ...],
    *,
    event_type: str,
    target_commit: str,
) -> tuple[
    tuple[tuple[PlanProgressRecord, dict[str, Any]], ...],
    tuple[tuple[PlanProgressRecord, str], ...],
]:
    matching: list[tuple[PlanProgressRecord, dict[str, Any]]] = []
    stale: list[tuple[PlanProgressRecord, str]] = []
    for progress in progress_events:
        if progress.event_type != event_type:
            continue
        details = _json_object(progress.details)
        head_sha = _details_head_sha(details)
        if head_sha == target_commit:
            matching.append((progress, details))
        elif head_sha:
            stale.append((progress, head_sha))
    return tuple(matching), tuple(stale)


def _release_status_passed(details: dict[str, Any]) -> bool:
    return str(details.get("status", "")).casefold() in {
        "pass",
        "passed",
        "success",
        "succeeded",
    }


def _details_head_sha(details: dict[str, Any]) -> str | None:
    for key in ("head_sha", "target_commit", "commit_sha"):
        value = details.get(key)
        if isinstance(value, str):
            normalized = _normalize_commit(value)
            if normalized is not None:
                return normalized
    environment = details.get("environment")
    if isinstance(environment, dict):
        value = environment.get("head_sha")
        if isinstance(value, str):
            return _normalize_commit(value)
    return None


def _planning_progress(planning_db_path: Path) -> tuple[PlanProgressRecord, ...]:
    if not planning_db_path.exists():
        return ()
    try:
        store = open_existing_planning_database(planning_db_path, read_only=True)
        return store.list_plan_progress()
    except Exception:
        return ()


def _resolve_target_commit(root: Path, target_commit: str | None) -> str | None:
    if target_commit is not None:
        return _normalize_commit(target_commit)
    current_head = _current_head(root)
    if current_head is None:
        return None
    return _release_subject_commit(root, current_head)


def _current_head(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return _normalize_commit(result.stdout.strip())


def _release_subject_commit(root: Path, commit: str) -> str:
    """Return the code/doc commit audited by trailing evidence-only commits."""

    current = commit
    while True:
        parent = _single_parent(root, current)
        if parent is None:
            return current
        changed_paths = _changed_paths_for_commit(root, current)
        if not changed_paths:
            return current
        if not all(_is_evidence_only_release_path(path) for path in changed_paths):
            return current
        current = parent


def _single_parent(root: Path, commit: str) -> str | None:
    try:
        result = subprocess.run(
            ("git", "rev-list", "--parents", "-n", "1", commit),
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    parts = result.stdout.strip().split()
    if len(parts) != 2:
        return None
    return _normalize_commit(parts[1])


def _changed_paths_for_commit(root: Path, commit: str) -> tuple[str, ...]:
    try:
        result = subprocess.run(
            ("git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit),
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return ()
    if result.returncode != 0:
        return ()
    return tuple(line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line)


def _is_evidence_only_release_path(path: str) -> bool:
    normalized = path.strip().replace("\\", "/")
    return normalized in EVIDENCE_ONLY_RELEASE_PATHS or normalized.startswith(
        EVIDENCE_ONLY_RELEASE_PREFIXES
    )


def _normalize_commit(value: str) -> str | None:
    normalized = value.strip().casefold()
    if len(normalized) != 40:
        return None
    if any(character not in "0123456789abcdef" for character in normalized):
        return None
    return normalized


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
