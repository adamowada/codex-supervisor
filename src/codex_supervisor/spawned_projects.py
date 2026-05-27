"""Spawned-project scaffold recommendation and apply contracts."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from codex_supervisor.planning import (
    PlanAcceptanceCriterionRecord,
    PlanMilestoneRecord,
    PlanningSQLiteStore,
    PlanProgressRecord,
    PlanRecord,
    SupervisorTaskRecord,
    WorkerRunRecord,
    initialize_planning_database,
)

PROJECT_COMPLEXITIES = frozenset({"prototype", "small", "standard", "production"})
TRUST_POLICIES = frozenset({"local_trusted", "controlled_runner", "untrusted"})

PROTOTYPE_LIGHT_FILES = (
    "README.md",
    "AGENTS.md",
    "HANDOFF.md",
    ".gitignore",
    "scripts/verify.py",
)
BASE_TIER_FILES = (
    "README.md",
    "AGENTS.md",
    "PLANS.md",
    "ARCHITECTURE.md",
    "CONTRACTS.md",
    "ROADMAP.md",
    "TESTING.md",
    "DECISIONS.md",
    "SOP.md",
    "HANDOFF.md",
    ".gitignore",
    ".gitattributes",
    "scripts/verify.py",
    "insights/README.md",
)
SUPERVISOR_MANAGED_FILES = (
    "plans/planning.sqlite3",
    "scripts/print_protected_hashes.py",
    "scripts/check_protected_files.py",
    "scripts/check_file_justification.py",
    "scripts/check_planning_integrity.py",
)
PUBLICATION_READY_FILES = (
    "LICENSE",
    "ATTRIBUTIONS.md",
    "scripts/check_public_repo_hygiene.py",
)
DURABLE_LEARNING_FILES = ("insights/graph.md",)
REPO_LOCAL_SKILL_FILES = (
    "scripts/check_skill_inventory.py",
    ".agents/skills/",
    ".agents/skills/project-bootstrap/SKILL.md",
)
SOURCE_STUDY_FILES = (
    "scripts/check_source_inventory.py",
    "sources/README.md",
)
BASE_VERIFICATION_COMMANDS = ("uv run --no-sync python -B scripts/verify.py",)
SUPERVISOR_VERIFICATION_COMMANDS = (
    "uv run --no-sync python -B scripts/check_protected_files.py",
    "uv run --no-sync python -B scripts/check_file_justification.py",
    "uv run --no-sync python -B scripts/check_planning_integrity.py",
)
PUBLICATION_VERIFICATION_COMMANDS = (
    "uv run --no-sync python -B scripts/check_public_repo_hygiene.py",
)
REPO_LOCAL_SKILL_VERIFICATION_COMMANDS = (
    "uv run --no-sync python -B scripts/check_skill_inventory.py",
)
SOURCE_STUDY_VERIFICATION_COMMANDS = (
    "uv run --no-sync python -B scripts/check_source_inventory.py",
)


@dataclass(frozen=True)
class SpawnedProjectBrief:
    name: str
    complexity: str = "standard"
    production_intended: bool = False
    public_or_shared: bool = False
    unattended_workers: bool = False
    durable_queue: bool = False
    protected_docs: bool = False
    durable_learning: bool = False
    repo_local_skills: bool = False
    source_study: bool = False
    plugin_full_afk: bool = False
    trust_policy: str = "local_trusted"


@dataclass(frozen=True)
class SpawnedProjectRecommendation:
    project_name: str
    tiers: tuple[str, ...]
    required_files: tuple[str, ...]
    verification_commands: tuple[str, ...]
    first_task_guidance: str
    planning_guidance: str
    classification_reason: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SpawnedProjectScaffoldAction:
    path: str
    action: str
    tier: str
    purpose: str


@dataclass(frozen=True)
class SpawnedProjectFirstTaskProposal:
    title: str
    task_type: str
    status: str
    goal: str
    acceptance_criteria: tuple[str, ...]
    verification_commands: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    review_required: bool


@dataclass(frozen=True)
class SpawnedProjectScaffoldProposal:
    project_name: str
    recommendation: SpawnedProjectRecommendation
    file_actions: tuple[SpawnedProjectScaffoldAction, ...]
    planning_actions: tuple[str, ...]
    source_lock_actions: tuple[str, ...]
    insight_actions: tuple[str, ...]
    skill_actions: tuple[str, ...]
    source_study_actions: tuple[str, ...]
    first_task: SpawnedProjectFirstTaskProposal
    writes_files: bool = False


@dataclass(frozen=True)
class SpawnedProjectScaffoldApplyResult:
    project_name: str
    project_root: str
    created_files: tuple[str, ...]
    existing_files: tuple[str, ...]
    planning_db_path: str | None
    first_task: SpawnedProjectFirstTaskProposal
    verification_commands: tuple[str, ...]
    git_initialized: bool = False
    baseline_commit_created: bool = False
    baseline_commit_sha: str | None = None
    writes_files: bool = True


@dataclass(frozen=True)
class GitBaselineResult:
    git_initialized: bool = False
    baseline_commit_created: bool = False
    baseline_commit_sha: str | None = None


def recommend_spawned_project_scaffold(
    brief: SpawnedProjectBrief,
) -> SpawnedProjectRecommendation:
    """Recommend scaffold tiers for a spawned project without writing files."""

    _validate_brief(brief)
    if _is_throwaway_prototype(brief):
        return SpawnedProjectRecommendation(
            project_name=brief.name,
            tiers=("prototype-light",),
            required_files=PROTOTYPE_LIGHT_FILES,
            verification_commands=BASE_VERIFICATION_COMMANDS,
            first_task_guidance=(
                "Create one directly verifiable prototype slice before adding planning SQLite "
                "or source-lock surfaces."
            ),
            planning_guidance=(
                "Keep the handoff compact and defer durable queue state until the work will span "
                "multiple AFK slices."
            ),
            classification_reason=(
                "prototype complexity with no production, publication, durable queue, protected "
                "docs, unattended worker, skill, or source-study requirement"
            ),
        )

    tiers = ["base"]
    required_files = list(BASE_TIER_FILES)
    verification_commands = list(BASE_VERIFICATION_COMMANDS)
    if _needs_supervisor_managed_tier(brief):
        tiers.append("supervisor-managed")
        required_files.extend(SUPERVISOR_MANAGED_FILES)
        verification_commands.extend(SUPERVISOR_VERIFICATION_COMMANDS)
    if brief.public_or_shared:
        tiers.append("publication-ready")
        required_files.extend(PUBLICATION_READY_FILES)
        verification_commands.extend(PUBLICATION_VERIFICATION_COMMANDS)
    if brief.durable_learning:
        tiers.append("durable-learning")
        required_files.extend(DURABLE_LEARNING_FILES)
    if brief.repo_local_skills or brief.source_study:
        tiers.append("skills-source-study")
        if brief.repo_local_skills:
            required_files.extend(REPO_LOCAL_SKILL_FILES)
            verification_commands.extend(REPO_LOCAL_SKILL_VERIFICATION_COMMANDS)
        if brief.source_study:
            required_files.extend(SOURCE_STUDY_FILES)
            verification_commands.extend(SOURCE_STUDY_VERIFICATION_COMMANDS)

    return SpawnedProjectRecommendation(
        project_name=brief.name,
        tiers=tuple(tiers),
        required_files=tuple(dict.fromkeys(required_files)),
        verification_commands=tuple(dict.fromkeys(verification_commands)),
        first_task_guidance=(
            "Create the first AFK-ready vertical slice with acceptance criteria, allowed paths, "
            "verification commands, and a review requirement."
        ),
        planning_guidance=_planning_guidance(brief),
        classification_reason=_classification_reason(brief, tuple(tiers)),
        warnings=_warnings(brief, tuple(tiers)),
    )


def build_spawned_project_scaffold_proposal(
    brief: SpawnedProjectBrief,
) -> SpawnedProjectScaffoldProposal:
    """Build a deterministic scaffold proposal without writing project files."""

    recommendation = recommend_spawned_project_scaffold(brief)
    file_actions = tuple(_file_actions_for_recommendation(recommendation))
    return SpawnedProjectScaffoldProposal(
        project_name=brief.name,
        recommendation=recommendation,
        file_actions=file_actions,
        planning_actions=_planning_actions_for_recommendation(recommendation),
        source_lock_actions=_source_lock_actions_for_recommendation(recommendation),
        insight_actions=_insight_actions_for_recommendation(recommendation),
        skill_actions=_skill_actions_for_recommendation(recommendation),
        source_study_actions=_source_study_actions_for_recommendation(recommendation),
        first_task=_first_task_for_recommendation(recommendation, file_actions),
    )


def apply_spawned_project_scaffold(
    brief: SpawnedProjectBrief,
    *,
    target_root: Path,
) -> SpawnedProjectScaffoldApplyResult:
    """Write the selected spawned-project scaffold into a target root."""

    proposal = build_spawned_project_scaffold_proposal(brief)
    root = target_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    existing: list[str] = []

    regular_files = tuple(
        action.path
        for action in proposal.file_actions
        if not action.path.endswith("/")
        and action.path not in {"plans/planning.sqlite3", "scripts/check_protected_files.py"}
        and action.path != "scripts/print_protected_hashes.py"
    )
    for relative_path in regular_files:
        content = _scaffold_file_content(relative_path, proposal)
        if _write_scaffold_file(root, relative_path, content, created, existing):
            continue

    for action in proposal.file_actions:
        if action.path.endswith("/"):
            directory = root / action.path
            if directory.exists():
                existing.append(action.path.rstrip("/"))
            else:
                directory.mkdir(parents=True)
                created.append(action.path.rstrip("/"))

    planning_db_path: str | None = None
    if "plans/planning.sqlite3" in proposal.recommendation.required_files:
        planning_db_path = "plans/planning.sqlite3"
        db_path = root / planning_db_path
        if db_path.exists():
            existing.append(planning_db_path)
        else:
            _initialize_spawned_planning_database(db_path, proposal)
            created.append(planning_db_path)

    if "scripts/print_protected_hashes.py" in proposal.recommendation.required_files:
        hashes = _protected_file_hashes(root, proposal)
        if _write_scaffold_file(
            root,
            "scripts/print_protected_hashes.py",
            _print_protected_hashes_script(hashes),
            created,
            existing,
        ):
            pass
    if "scripts/check_protected_files.py" in proposal.recommendation.required_files:
        hashes = _protected_file_hashes(root, proposal)
        if _write_scaffold_file(
            root,
            "scripts/check_protected_files.py",
            _check_protected_files_script(hashes),
            created,
            existing,
        ):
            pass

    _complete_spawned_scaffold_apply_task(root, proposal, tuple(created))
    git_baseline = _ensure_full_afk_git_baseline(brief, proposal, root)
    return SpawnedProjectScaffoldApplyResult(
        project_name=proposal.project_name,
        project_root=str(target_root),
        created_files=tuple(created),
        existing_files=tuple(existing),
        planning_db_path=planning_db_path,
        first_task=proposal.first_task,
        verification_commands=proposal.recommendation.verification_commands,
        git_initialized=git_baseline.git_initialized,
        baseline_commit_created=git_baseline.baseline_commit_created,
        baseline_commit_sha=git_baseline.baseline_commit_sha,
    )


def _ensure_full_afk_git_baseline(
    brief: SpawnedProjectBrief,
    proposal: SpawnedProjectScaffoldProposal,
    root: Path,
) -> GitBaselineResult:
    if "supervisor-managed" not in proposal.recommendation.tiers:
        return _git_baseline_result()
    if not (brief.plugin_full_afk or brief.unattended_workers):
        return _git_baseline_result()

    git_initialized = False
    if not (root / ".git").exists():
        _run_git(root, ("init",))
        git_initialized = True

    head = _git_head(root)
    if head is not None:
        return _git_baseline_result(git_initialized=git_initialized)

    _ensure_git_identity(root)
    scaffold_paths = tuple(
        path.rstrip("/")
        for path in proposal.recommendation.required_files
        if (root / path.rstrip("/")).exists()
    )
    if scaffold_paths:
        _run_git(root, ("add", "--", *scaffold_paths))
    status = _run_git(root, ("status", "--porcelain=v1"))
    if not status.stdout.strip():
        return _git_baseline_result(git_initialized=git_initialized)
    _run_git(root, ("commit", "-m", "Bootstrap supervisor-managed scaffold"))
    commit_sha = _git_head(root)
    return _git_baseline_result(
        git_initialized=git_initialized,
        baseline_commit_created=commit_sha is not None,
        baseline_commit_sha=commit_sha,
    )


def _git_baseline_result(
    *,
    git_initialized: bool = False,
    baseline_commit_created: bool = False,
    baseline_commit_sha: str | None = None,
) -> GitBaselineResult:
    return GitBaselineResult(
        git_initialized=git_initialized,
        baseline_commit_created=baseline_commit_created,
        baseline_commit_sha=baseline_commit_sha,
    )


def _ensure_git_identity(root: Path) -> None:
    name = _run_git(root, ("config", "--get", "user.name"), check=False)
    if name.returncode != 0 or not name.stdout.strip():
        _run_git(root, ("config", "user.name", "codex-supervisor"))
    email = _run_git(root, ("config", "--get", "user.email"), check=False)
    if email.returncode != 0 or not email.stdout.strip():
        _run_git(root, ("config", "user.email", "codex-supervisor@example.invalid"))


def _git_head(root: Path) -> str | None:
    result = _run_git(root, ("rev-parse", "--verify", "HEAD"), check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _run_git(
    root: Path,
    args: tuple[str, ...],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ("git", *args),
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        msg = f"git {' '.join(args)} failed"
        if details:
            msg = f"{msg}: {details}"
        raise RuntimeError(msg)
    return result


def _complete_spawned_scaffold_apply_task(
    root: Path,
    proposal: SpawnedProjectScaffoldProposal,
    created_files: tuple[str, ...],
) -> None:
    if "plans/planning.sqlite3" not in proposal.recommendation.required_files:
        return
    db_path = root / "plans" / "planning.sqlite3"
    if not db_path.exists():
        return

    verification = _run_spawned_scaffold_verification(root)
    slug = _slugify(proposal.project_name)
    plan_id = f"plan-{slug}-bootstrap"
    task_id = f"task-{slug}-bootstrap-scaffold"
    worker_run_id = f"run-{slug}-scaffold-apply"
    run_directory = f"runs/{worker_run_id}"
    artifact_directory = f"artifacts/{worker_run_id}"
    prompt_path = f"{run_directory}/prompt.md"
    jsonl_path = f"{run_directory}/events.jsonl"
    stdout_path = f"{run_directory}/stdout.txt"
    stderr_path = f"{run_directory}/stderr.txt"
    final_message_path = f"{run_directory}/final-message.txt"
    diff_summary_path = f"{run_directory}/diff-summary.txt"
    result_path = f"{artifact_directory}/worker-result.raw.json"
    evidence_manifest_path = f"{artifact_directory}/evidence-manifest.json"
    changed_files = _created_scaffold_files(root, created_files)
    if not changed_files:
        changed_files = ("plans/planning.sqlite3",)

    acceptance_results = {
        criterion: {
            "status": "passed",
            "evidence": "Satisfied by deterministic spawned-project scaffold apply.",
        }
        for criterion in proposal.first_task.acceptance_criteria
    }
    payload = {
        "worker_run_id": worker_run_id,
        "status": "completed",
        "summary": "Supervisor scaffold apply completed the generated scaffold task.",
        "changed_files": list(changed_files),
        "tests_run": [
            {
                "command": "python -B scripts/verify.py",
                "exit_code": verification.returncode,
                "summary": "passed",
            }
        ],
        "acceptance_results": acceptance_results,
        "risks": [],
        "follow_up_tasks": [
            "Seed the first concrete implementation task from the user's product request before "
            "running Story Loop workers."
        ],
        "artifacts": [result_path, evidence_manifest_path],
        "completion_notes": (
            "Scaffold task was completed by spawned-project-apply; Story Loop should run the "
            "next concrete implementation task, not a scaffold redo."
        ),
    }
    _write_spawned_text(
        root,
        prompt_path,
        "Deterministically apply the selected codex-supervisor spawned-project scaffold.\n",
    )
    _write_spawned_text(
        root,
        jsonl_path,
        json.dumps(
            {
                "event": "spawned_project.scaffold_apply.completed",
                "worker_run_id": worker_run_id,
                "task_id": task_id,
            },
            sort_keys=True,
        )
        + "\n",
    )
    _write_spawned_text(root, stdout_path, verification.stdout)
    _write_spawned_text(root, stderr_path, verification.stderr)
    _write_spawned_text(root, diff_summary_path, "\n".join(changed_files) + "\n")
    _write_spawned_text(root, final_message_path, json.dumps(payload, indent=2) + "\n")
    _write_spawned_text(root, result_path, json.dumps(payload, indent=2) + "\n")
    _write_spawned_evidence_manifest(
        root,
        worker_run_id=worker_run_id,
        task_id=task_id,
        paths={
            "prompt": prompt_path,
            "jsonl": jsonl_path,
            "stdout": stdout_path,
            "stderr": stderr_path,
            "final_message": final_message_path,
            "diff_summary": diff_summary_path,
            "raw_result": result_path,
        },
        output_path=evidence_manifest_path,
    )

    store = PlanningSQLiteStore(db_path, read_only=False)
    metadata = {
        "backend": "scaffold_apply",
        "execution_mode": "deterministic_supervisor_scaffold_apply",
        "launch_decision": "deterministic_scaffold_apply",
        "raw_evidence_paths": {
            "prompt": prompt_path,
            "jsonl": jsonl_path,
            "stdout": stdout_path,
            "stderr": stderr_path,
            "final_message": final_message_path,
            "diff_summary": diff_summary_path,
            "result": result_path,
            "evidence_manifest": evidence_manifest_path,
        },
        "evidence_manifest_path": evidence_manifest_path,
    }
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id=worker_run_id,
            task_id=task_id,
            backend="scaffold_apply",
            status="running",
            prompt_path=prompt_path,
            jsonl_path=jsonl_path,
            result_path=result_path,
            metadata=metadata,
        )
    )
    store.ingest_worker_result(worker_run_id, result_path)
    store.upsert_plan_milestone(
        PlanMilestoneRecord(
            milestone_id=f"milestone-{slug}-bootstrap",
            plan_id=plan_id,
            title="Bootstrap scaffold",
            status="completed",
            sort_order=10,
            details={"tiers": list(proposal.recommendation.tiers)},
        )
    )
    store.upsert_plan_acceptance_criterion(
        PlanAcceptanceCriterionRecord(
            criterion_id=f"criterion-{slug}-scaffold",
            plan_id=plan_id,
            description="Selected scaffold files exist and scaffold verification passes.",
            status="completed",
            verification_command="python -B scripts/verify.py",
        )
    )
    store.add_plan_progress(
        PlanProgressRecord(
            progress_id=f"progress-{slug}-scaffold-completed",
            plan_id=plan_id,
            event_type="scaffold_completed",
            summary="Deterministic spawned-project scaffold apply completed the scaffold task.",
            details=(
                "The bootstrap task is a scaffold-apply record, not a Story Loop worker target. "
                "Seed the user's concrete implementation request as the next task before "
                "launching codex_exec."
            ),
            linked_artifact_id=evidence_manifest_path,
        )
    )


def _run_spawned_scaffold_verification(root: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        (sys.executable, "-B", "scripts/verify.py"),
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        msg = "spawned project scaffold verification failed"
        if details:
            msg = f"{msg}: {details}"
        raise RuntimeError(msg)
    return result


def _created_scaffold_files(root: Path, created_files: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        path
        for path in dict.fromkeys(created_files)
        if not path.endswith("/") and (root / path).is_file()
    )


def _write_spawned_text(root: Path, relative_path: str, content: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_spawned_evidence_manifest(
    root: Path,
    *,
    worker_run_id: str,
    task_id: str,
    paths: dict[str, str],
    output_path: str,
) -> None:
    manifest = {
        "worker_run_id": worker_run_id,
        "task_id": task_id,
        "status": "completed",
        "launch_decision": "deterministic_scaffold_apply",
        "paths": {
            name: _spawned_evidence_path_record(root / relative_path)
            for name, relative_path in paths.items()
        },
    }
    _write_spawned_text(root, output_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def _spawned_evidence_path_record(path: Path) -> dict[str, object]:
    if not path.exists() or not path.is_file():
        return {"exists": False}
    raw_bytes = path.read_bytes()
    return {
        "exists": True,
        "bytes": len(raw_bytes),
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
    }


def _write_scaffold_file(
    root: Path,
    relative_path: str,
    content: str,
    created: list[str],
    existing: list[str],
) -> bool:
    _validate_scaffold_relative_path(relative_path)
    path = root / relative_path
    if path.exists():
        existing.append(relative_path)
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    created.append(relative_path)
    return True


def _validate_scaffold_relative_path(relative_path: str) -> None:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        msg = f"unsafe scaffold path: {relative_path}"
        raise ValueError(msg)


def _initialize_spawned_planning_database(
    path: Path,
    proposal: SpawnedProjectScaffoldProposal,
) -> PlanningSQLiteStore:
    store = initialize_planning_database(path)
    plan_id = f"plan-{_slugify(proposal.project_name)}-bootstrap"
    store.upsert_plan(
        PlanRecord(
            plan_id=plan_id,
            slug=f"{_slugify(proposal.project_name)}-bootstrap",
            title=f"{proposal.project_name} Bootstrap",
            goal=(
                "Create and verify the selected codex-supervisor spawned-project scaffold, "
                "then execute the first bounded implementation slice."
            ),
            status="active",
            priority=100,
            owner_agent="codex-supervisor",
            context={
                "project_name": proposal.project_name,
                "scaffold_tiers": list(proposal.recommendation.tiers),
            },
        )
    )
    store.upsert_plan_milestone(
        PlanMilestoneRecord(
            milestone_id=f"milestone-{_slugify(proposal.project_name)}-bootstrap",
            plan_id=plan_id,
            title="Bootstrap scaffold",
            status="active",
            sort_order=10,
            details={"tiers": list(proposal.recommendation.tiers)},
        )
    )
    store.upsert_plan_acceptance_criterion(
        PlanAcceptanceCriterionRecord(
            criterion_id=f"criterion-{_slugify(proposal.project_name)}-scaffold",
            plan_id=plan_id,
            description="Selected scaffold files exist and scaffold verification passes.",
            status="pending",
            verification_command="python -B scripts/verify.py",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id=f"task-{_slugify(proposal.project_name)}-bootstrap-scaffold",
            plan_id=plan_id,
            title=proposal.first_task.title,
            goal=proposal.first_task.goal,
            task_type=proposal.first_task.task_type,
            status=proposal.first_task.status,
            scope={
                "source": "codex-supervisor spawned-project scaffold apply",
                "project_name": proposal.project_name,
                "scaffold_tiers": list(proposal.recommendation.tiers),
            },
            acceptance_criteria=list(proposal.first_task.acceptance_criteria),
            verification_commands=list(proposal.first_task.verification_commands),
            allowed_paths=list(proposal.first_task.allowed_paths),
            worker_backend="codex_exec",
            review_required=proposal.first_task.review_required,
        ),
        validate_current_queue_contract=True,
    )
    store.add_plan_progress(
        PlanProgressRecord(
            progress_id=f"progress-{_slugify(proposal.project_name)}-scaffold-created",
            plan_id=plan_id,
            event_type="scaffold_created",
            summary="Initial codex-supervisor spawned-project scaffold was created.",
            details=(
                "Scaffold creation recorded by the project-local planning database. "
                "Operational history should continue here, not in HANDOFF.md."
            ),
        )
    )
    return store


def _scaffold_file_content(
    relative_path: str,
    proposal: SpawnedProjectScaffoldProposal,
) -> str:
    project = proposal.project_name
    if relative_path == "README.md":
        return (
            f"# {project}\n\n"
            "This spawned project is managed with a codex-supervisor scaffold. "
            "Use the planning database for active work, source-of-truth markdown for durable "
            "doctrine, and `HANDOFF.md` only as the compact current resume snapshot.\n"
        )
    if relative_path == "AGENTS.md":
        return (
            "# AGENTS.md\n\n"
            "Use `plans/planning.sqlite3` as the queue authority. Read `README.md`, this file, "
            "`PLANS.md`, and `HANDOFF.md` before selecting work. Run "
            "`python -B scripts/check_planning_integrity.py` before declaring a queue complete. "
            "Directory allowed paths must use explicit glob patterns such as `client/**`, not "
            "trailing slash forms such as `client/`. Review-required AFK work needs a separate "
            "review task and review result before completion. The scaffold task is completed by "
            "`spawned-project-apply`; seed the user's concrete implementation request as a new "
            "task before running Story Loop workers. Keep source-of-truth docs stable, run "
            "`python -B scripts/verify.py` before publishing, and do not store secrets or local "
            "absolute roots in tracked state.\n"
        )
    if relative_path == "PLANS.md":
        return (
            "# PLANS.md\n\n"
            "Planning state lives in `plans/planning.sqlite3`. Tasks need a clear goal, "
            "acceptance criteria, verification commands, allowed paths, and review posture before "
            "unattended work begins. Use repo-relative file paths or glob patterns for allowed "
            "paths; express directories as `path/**`. After scaffold apply, do not run a worker on "
            "the scaffold completion record; compile or upsert the real product task first. A "
            "completed plan must not leave `HANDOFF.md` saying review is still pending.\n"
        )
    if relative_path == "ARCHITECTURE.md":
        return (
            "# ARCHITECTURE.md\n\n"
            f"`{project}` starts with a supervisor-ready scaffold. Keep application code separate "
            "from planning, verification, and agent-operation helpers so behavior remains easy to "
            "test and review.\n"
        )
    if relative_path == "CONTRACTS.md":
        return (
            "# CONTRACTS.md\n\n"
            "Worker results must report status, changed files, artifacts, tests run, acceptance "
            "results, risks, follow-up tasks, and completion notes. Project-specific interfaces "
            "should be added here when they become stable.\n"
        )
    if relative_path == "ROADMAP.md":
        return (
            "# ROADMAP.md\n\n"
            "1. Keep the scaffold verifiable.\n"
            "2. Complete the first AFK vertical slice from planning SQLite.\n"
            "3. Promote stable lessons into `insights/` and stable decisions into `DECISIONS.md`.\n"
        )
    if relative_path == "TESTING.md":
        return (
            "# TESTING.md\n\n"
            "Run `python -B scripts/verify.py` locally. Add focused tests beside each production "
            "behavior before broadening the verification gate.\n"
        )
    if relative_path == "DECISIONS.md":
        return (
            "# DECISIONS.md\n\n"
            "- Build from a codex-supervisor spawned-project scaffold so planning, verification, "
            "source locks, and handoff behavior are present from the first commit.\n"
        )
    if relative_path == "SOP.md":
        return (
            "# SOP.md\n\n"
            "1. Inspect the current queue in `plans/planning.sqlite3`.\n"
            "2. Work one vertical slice at a time.\n"
            "3. Run focused checks, then `python -B scripts/verify.py`.\n"
            "4. Keep `HANDOFF.md` compact and current.\n"
        )
    if relative_path == "HANDOFF.md":
        return (
            "# HANDOFF.md\n\n"
            "Current snapshot: scaffold created and ready for the first planned AFK task. "
            "Use `plans/planning.sqlite3` as the queue authority and update this file only with "
            "the current resume state.\n"
        )
    if relative_path == "LICENSE":
        return (
            "MIT License\n\n"
            "Copyright (c) 2026\n\n"
            "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
            'of this software and associated documentation files (the "Software"), to deal\n'
            "in the Software without restriction, including without limitation the rights\n"
            "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell\n"
            "copies of the Software, and to permit persons to whom the Software is\n"
            "furnished to do so, subject to the following conditions:\n\n"
            "The above copyright notice and this permission notice shall be included in all\n"
            "copies or substantial portions of the Software.\n\n"
            'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\n'
            "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\n"
            "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\n"
            "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\n"
            "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\n"
            "OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\n"
            "SOFTWARE.\n"
        )
    if relative_path == "ATTRIBUTIONS.md":
        return (
            "# ATTRIBUTIONS.md\n\n"
            "This scaffold was generated from codex-supervisor project templates. Add source or "
            "inspiration attributions before publishing any copied or adapted material.\n"
        )
    if relative_path == ".gitignore":
        return (
            ".venv/\n"
            "__pycache__/\n"
            ".pytest_cache/\n"
            ".ruff_cache/\n"
            ".mypy_cache/\n"
            "artifacts/\n"
            "cache/\n"
            "runs/\n"
            "worker-results/\n"
            "worktrees/\n"
            "sources/*\n"
            "!sources/README.md\n"
        )
    if relative_path == ".gitattributes":
        return "* text=auto eol=lf\n*.sqlite3 binary\n*.db binary\n"
    if relative_path == "insights/README.md":
        return (
            "# Insight Wiki\n\n"
            "Store synthesized, provenance-backed workflow lessons here. Do not use insights as "
            "a scratch log or queue state mirror.\n"
        )
    if relative_path == "insights/graph.md":
        return (
            "# Insight Graph\n\n"
            "| From | Relation | To | Confidence | Next action |\n"
            "| --- | --- | --- | --- | --- |\n"
        )
    if relative_path == "sources/README.md":
        return (
            "# Source Study\n\nRecord external source repositories and attribution posture here.\n"
        )
    if relative_path == "scripts/verify.py":
        return _verify_script(proposal)
    if relative_path == "scripts/check_file_justification.py":
        return _check_file_justification_script(proposal)
    if relative_path == "scripts/check_planning_integrity.py":
        return _check_planning_integrity_script()
    if relative_path == "scripts/check_public_repo_hygiene.py":
        return _check_public_repo_hygiene_script()
    if relative_path == "scripts/check_skill_inventory.py":
        return _check_skill_inventory_script()
    if relative_path == "scripts/check_source_inventory.py":
        return _check_source_inventory_script()
    if relative_path == ".agents/skills/project-bootstrap/SKILL.md":
        return _project_bootstrap_skill(proposal)
    return f"# {Path(relative_path).name}\n\nManaged project bootstrap surface for {project}.\n"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "project"


def _protected_file_hashes(
    root: Path,
    proposal: SpawnedProjectScaffoldProposal,
) -> dict[str, str]:
    protected = tuple(
        path
        for path in proposal.recommendation.required_files
        if path
        in {
            ".gitattributes",
            ".gitignore",
            "README.md",
            "AGENTS.md",
            "PLANS.md",
            "ARCHITECTURE.md",
            "CONTRACTS.md",
            "ROADMAP.md",
            "SOP.md",
            "TESTING.md",
            "DECISIONS.md",
            "LICENSE",
            "ATTRIBUTIONS.md",
        }
        and (root / path).exists()
    )
    return {
        path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in sorted(protected)
    }


def _project_bootstrap_skill(proposal: SpawnedProjectScaffoldProposal) -> str:
    project = proposal.project_name
    return (
        "---\n"
        "name: project-bootstrap\n"
        "description: Use when starting or resuming the first supervised project slice.\n"
        "---\n\n"
        "# Project Bootstrap\n\n"
        f"This repo-local skill keeps `{project}` aligned with its source of truth, planning "
        "queue, and verification gates.\n\n"
        "## Workflow\n\n"
        "1. Inspect `plans/planning.sqlite3` before choosing work.\n"
        "2. Read `AGENTS.md`, `PLANS.md`, and `HANDOFF.md` for the current operating contract.\n"
        "3. Execute one bounded vertical slice and update planning SQLite with durable evidence.\n"
        "4. Run `uv run --no-sync python -B scripts/verify.py` before handoff or publication.\n"
        "5. Keep reusable lessons in `insights/` and keep `HANDOFF.md` compact.\n"
    )


def _verify_script(proposal: SpawnedProjectScaffoldProposal) -> str:
    scripts = [
        script
        for script in (
            "scripts/check_file_justification.py",
            "scripts/check_protected_files.py",
            "scripts/check_planning_integrity.py",
        )
        if script in proposal.recommendation.required_files
    ]
    if "scripts/check_public_repo_hygiene.py" in proposal.recommendation.required_files:
        scripts.append("scripts/check_public_repo_hygiene.py")
    if "scripts/check_skill_inventory.py" in proposal.recommendation.required_files:
        scripts.append("scripts/check_skill_inventory.py")
    if "scripts/check_source_inventory.py" in proposal.recommendation.required_files:
        scripts.append("scripts/check_source_inventory.py")
    required_files = repr(proposal.recommendation.required_files)
    if scripts:
        commands_literal = (
            "(\n    " + ",\n    ".join(f"({script!r},)" for script in scripts) + ",\n)"
        )
    else:
        commands_literal = "()"
    return (
        "#!/usr/bin/env python3\n"
        '"""Run spawned-project verification."""\n\n'
        "from __future__ import annotations\n\n"
        "from pathlib import Path\n"
        "import subprocess\n"
        "import sys\n\n"
        f"REQUIRED_FILES = {required_files}\n"
        f"COMMANDS = {commands_literal}\n\n"
        "def _required_file_failures() -> list[str]:\n"
        "    failures = []\n"
        "    for relative in REQUIRED_FILES:\n"
        "        path = Path(relative.rstrip('/'))\n"
        "        if relative.endswith('/'):\n"
        "            if not path.is_dir():\n"
        "                failures.append(f'missing required directory: {relative}')\n"
        "            continue\n"
        "        if not path.is_file():\n"
        "            failures.append(f'missing required file: {relative}')\n"
        "            continue\n"
        "        if path.suffix.lower() != '.sqlite3' and path.stat().st_size == 0:\n"
        "            failures.append(f'empty required file: {relative}')\n"
        "    return failures\n\n"
        "def main() -> int:\n"
        "    failures = _required_file_failures()\n"
        "    if failures:\n"
        "        for failure in failures:\n"
        "            print(failure)\n"
        "        return 1\n"
        "    for command in COMMANDS:\n"
        "        completed = subprocess.run((sys.executable, '-B', *command), check=False)\n"
        "        if completed.returncode != 0:\n"
        "            return completed.returncode\n"
        "    print('Verification passed.')\n"
        "    return 0\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n"
    )


def _check_file_justification_script(proposal: SpawnedProjectScaffoldProposal) -> str:
    known_files = sorted(
        path.rstrip("/")
        for path in proposal.recommendation.required_files
        if not path.endswith("/")
    )
    known_literal = repr(known_files)
    return (
        "#!/usr/bin/env python3\n"
        '"""Check scaffold files have known purposes."""\n\n'
        "from __future__ import annotations\n\n"
        "from pathlib import Path\n\n"
        f"KNOWN_FILES = set({known_literal})\n"
        "IGNORED_DIRS = {'.git', '.venv', '__pycache__', '.pytest_cache', '.ruff_cache', "
        "'.mypy_cache', 'artifacts', 'cache', 'runs', 'worker-results', 'worktrees', 'sources'}\n\n"
        "def main() -> int:\n"
        "    failures = []\n"
        "    for path in Path('.').rglob('*'):\n"
        "        if not path.is_file() or any(part in IGNORED_DIRS for part in path.parts):\n"
        "            continue\n"
        "        relative = path.as_posix()\n"
        "        if relative not in KNOWN_FILES:\n"
        "            failures.append(f'unknown public file: {relative}')\n"
        "            continue\n"
        "        if path.suffix.lower() != '.sqlite3' and path.stat().st_size == 0:\n"
        "            failures.append(f'empty public file: {relative}')\n"
        "    for failure in failures:\n"
        "        print(failure)\n"
        "    if failures:\n"
        "        return 1\n"
        "    print('File justification checks passed.')\n"
        "    return 0\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n"
    )


def _check_planning_integrity_script() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / "scripts" / "check_planning_integrity.py").read_text(encoding="utf-8")


def _check_public_repo_hygiene_script() -> str:
    return (
        "#!/usr/bin/env python3\n"
        '"""Check tracked-text public hygiene patterns."""\n\n'
        "from __future__ import annotations\n\n"
        "from pathlib import Path\n\n"
        "FORBIDDEN = ('C:' + chr(92) + 'Users', chr(47) + 'Users' + chr(47))\n"
        "SKIP_SUFFIXES = {'.sqlite3', '.db'}\n\n"
        "def main() -> int:\n"
        "    failures = []\n"
        "    for path in Path('.').rglob('*'):\n"
        "        if not path.is_file() or path.suffix.lower() in SKIP_SUFFIXES:\n"
        "            continue\n"
        "        if any(part in {'.git', '.venv', 'sources'} for part in path.parts):\n"
        "            continue\n"
        "        try:\n"
        "            text = path.read_text(encoding='utf-8')\n"
        "        except UnicodeDecodeError:\n"
        "            continue\n"
        "        if any(pattern in text for pattern in FORBIDDEN):\n"
        "            failures.append(f'local absolute path leak: {path.as_posix()}')\n"
        "    for failure in failures:\n"
        "        print(failure)\n"
        "    if failures:\n"
        "        return 1\n"
        "    print('Public repo hygiene checks passed.')\n"
        "    return 0\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n"
    )


def _check_skill_inventory_script() -> str:
    return (
        "#!/usr/bin/env python3\n"
        '"""Check optional repo-local skill inventory."""\n\n'
        "from pathlib import Path\n\n"
        "def main() -> int:\n"
        "    skills = Path('.agents/skills')\n"
        "    if skills.exists() and not any(skills.glob('*/SKILL.md')):\n"
        "        print('repo-local skills directory exists but contains no SKILL.md files')\n"
        "        return 1\n"
        "    print('Skill inventory checks passed.')\n"
        "    return 0\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n"
    )


def _check_source_inventory_script() -> str:
    return (
        "#!/usr/bin/env python3\n"
        '"""Check optional source-study inventory."""\n\n'
        "from pathlib import Path\n\n"
        "def main() -> int:\n"
        "    if Path('sources').exists() and not Path('sources/README.md').exists():\n"
        "        print('sources/README.md is required when sources/ exists')\n"
        "        return 1\n"
        "    print('Source inventory checks passed.')\n"
        "    return 0\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n"
    )


def _print_protected_hashes_script(hashes: dict[str, str]) -> str:
    return (
        "#!/usr/bin/env python3\n"
        '"""Print protected scaffold file hashes."""\n\n'
        "from __future__ import annotations\n\n"
        "import hashlib\n"
        "from pathlib import Path\n\n"
        f"PROTECTED_FILES = {hashes!r}\n\n"
        "def main() -> int:\n"
        "    for path in sorted(PROTECTED_FILES):\n"
        "        print(f'{path}\\t{hashlib.sha256(Path(path).read_bytes()).hexdigest()}')\n"
        "    return 0\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n"
    )


def _check_protected_files_script(hashes: dict[str, str]) -> str:
    return (
        "#!/usr/bin/env python3\n"
        '"""Check protected scaffold file hashes."""\n\n'
        "from __future__ import annotations\n\n"
        "import hashlib\n"
        "from pathlib import Path\n\n"
        f"PROTECTED_FILES = {hashes!r}\n\n"
        "def main() -> int:\n"
        "    failures = []\n"
        "    for path, expected in sorted(PROTECTED_FILES.items()):\n"
        "        file_path = Path(path)\n"
        "        if not file_path.exists():\n"
        "            failures.append(f'missing protected file: {path}')\n"
        "            continue\n"
        "        actual = hashlib.sha256(file_path.read_bytes()).hexdigest()\n"
        "        if actual != expected:\n"
        "            failures.append(f'protected file hash changed: {path}')\n"
        "    for failure in failures:\n"
        "        print(failure)\n"
        "    if failures:\n"
        "        return 1\n"
        "    print('Protected source-of-truth files are unchanged.')\n"
        "    return 0\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n"
    )


def _validate_brief(brief: SpawnedProjectBrief) -> None:
    if not isinstance(brief.name, str) or not brief.name.strip():
        msg = "name must be nonblank"
        raise ValueError(msg)
    if brief.complexity not in PROJECT_COMPLEXITIES:
        msg = f"complexity must be one of: {', '.join(sorted(PROJECT_COMPLEXITIES))}"
        raise ValueError(msg)
    if brief.trust_policy not in TRUST_POLICIES:
        msg = f"trust_policy must be one of: {', '.join(sorted(TRUST_POLICIES))}"
        raise ValueError(msg)


def _is_throwaway_prototype(brief: SpawnedProjectBrief) -> bool:
    return (
        brief.complexity == "prototype"
        and not brief.production_intended
        and not brief.public_or_shared
        and not brief.unattended_workers
        and not brief.durable_queue
        and not brief.protected_docs
        and not brief.durable_learning
        and not brief.repo_local_skills
        and not brief.source_study
        and not brief.plugin_full_afk
    )


def _needs_supervisor_managed_tier(brief: SpawnedProjectBrief) -> bool:
    return (
        brief.production_intended
        or brief.unattended_workers
        or brief.plugin_full_afk
        or brief.durable_queue
        or brief.protected_docs
        or brief.complexity in {"standard", "production"}
        or brief.trust_policy != "local_trusted"
    )


def _planning_guidance(brief: SpawnedProjectBrief) -> str:
    if _needs_supervisor_managed_tier(brief):
        return (
            "Initialize planning SQLite with one active plan, milestones, acceptance criteria, "
            "and the first AFK/HITL tasks before unattended work begins."
        )
    return "Use markdown task notes until the project earns durable queue state."


def _classification_reason(brief: SpawnedProjectBrief, tiers: tuple[str, ...]) -> str:
    reason_parts = [f"complexity={brief.complexity}", f"trust_policy={brief.trust_policy}"]
    if brief.production_intended:
        reason_parts.append("production_intended")
    if brief.public_or_shared:
        reason_parts.append("public_or_shared")
    if brief.unattended_workers:
        reason_parts.append("unattended_workers")
    if brief.plugin_full_afk:
        reason_parts.append("plugin_full_afk")
    if brief.durable_queue:
        reason_parts.append("durable_queue")
    if brief.protected_docs:
        reason_parts.append("protected_docs")
    if brief.durable_learning:
        reason_parts.append("durable_learning")
    if brief.repo_local_skills:
        reason_parts.append("repo_local_skills")
    if brief.source_study:
        reason_parts.append("source_study")
    return f"{', '.join(reason_parts)} -> {', '.join(tiers)}"


def _warnings(
    brief: SpawnedProjectBrief,
    tiers: tuple[str, ...],
) -> tuple[str, ...]:
    warnings: list[str] = []
    if brief.trust_policy == "untrusted" and "supervisor-managed" in tiers:
        warnings.append(
            "Untrusted projects need isolated worktrees or controlled runners before "
            "full-auto work."
        )
    if brief.public_or_shared and not brief.source_study:
        warnings.append(
            "Record source inspirations before publication even when no source-study tier "
            "is needed."
        )
    return tuple(warnings)


def _file_actions_for_recommendation(
    recommendation: SpawnedProjectRecommendation,
) -> tuple[SpawnedProjectScaffoldAction, ...]:
    return tuple(
        SpawnedProjectScaffoldAction(
            path=path,
            action="create_if_missing",
            tier=_tier_for_path(recommendation, path),
            purpose=_purpose_for_path(path),
        )
        for path in recommendation.required_files
    )


def _tier_for_path(recommendation: SpawnedProjectRecommendation, path: str) -> str:
    if "prototype-light" in recommendation.tiers:
        return "prototype-light"
    if path in SUPERVISOR_MANAGED_FILES:
        return "supervisor-managed"
    if path in PUBLICATION_READY_FILES:
        return "publication-ready"
    if path in DURABLE_LEARNING_FILES:
        return "durable-learning"
    if path in REPO_LOCAL_SKILL_FILES:
        return "repo-local-skills"
    if path in SOURCE_STUDY_FILES:
        return "source-study"
    return "base"


def _purpose_for_path(path: str) -> str:
    purposes = {
        ".agents/skills/": "repo-local skill surfaces when repeated project workflows appear",
        ".agents/skills/project-bootstrap/SKILL.md": "initial repo-local project bootstrap skill",
        ".gitattributes": "cross-platform text and binary normalization",
        ".gitignore": "local runtime, cache, source clone, and artifact exclusion",
        "AGENTS.md": "agent operating instructions",
        "ARCHITECTURE.md": "system structure and ownership boundaries",
        "ATTRIBUTIONS.md": "source and inspiration attribution record",
        "CONTRACTS.md": "interfaces, data contracts, and worker result contracts",
        "DECISIONS.md": "durable architecture and workflow decisions",
        "HANDOFF.md": "compact mutable fresh-thread resume snapshot",
        "LICENSE": "publication license posture",
        "PLANS.md": "planning doctrine and durable queue policy",
        "README.md": "human-facing project purpose and bootstrap guide",
        "ROADMAP.md": "stage plan and done-when gates",
        "SOP.md": "standard operating procedure",
        "TESTING.md": "verification strategy",
        "insights/README.md": "durable learning index",
        "insights/graph.md": "synthesized durable learning graph",
        "plans/planning.sqlite3": "canonical operational planning queue",
        "scripts/check_file_justification.py": "public file purpose gate",
        "scripts/check_planning_integrity.py": "planning SQLite integrity gate",
        "scripts/check_protected_files.py": "source-of-truth lock gate",
        "scripts/check_public_repo_hygiene.py": "public hygiene gate",
        "scripts/check_skill_inventory.py": "repo-local skill inventory gate",
        "scripts/check_source_inventory.py": "source-study inventory gate",
        "scripts/print_protected_hashes.py": "protected file hash helper",
        "scripts/verify.py": "project verification entrypoint",
        "sources/README.md": "source-study inventory and attribution guide",
    }
    return purposes.get(path, "spawned project scaffold file")


def _planning_actions_for_recommendation(
    recommendation: SpawnedProjectRecommendation,
) -> tuple[str, ...]:
    if "supervisor-managed" not in recommendation.tiers:
        return ("Defer planning SQLite until the work spans multiple AFK slices.",)
    return (
        "Initialize plans/planning.sqlite3 only for projects that need durable queue state.",
        "Seed one active plan with milestones, acceptance criteria, and first AFK/HITL tasks.",
        "Keep operational history in planning SQLite and HANDOFF.md as a compact resume snapshot.",
    )


def _source_lock_actions_for_recommendation(
    recommendation: SpawnedProjectRecommendation,
) -> tuple[str, ...]:
    if "supervisor-managed" not in recommendation.tiers:
        return ("Skip source locks until stable protected docs exist.",)
    return (
        "Draft protected source-of-truth docs first.",
        "Add source locks only after stable docs exist and protected hashes are intentional.",
    )


def _insight_actions_for_recommendation(
    recommendation: SpawnedProjectRecommendation,
) -> tuple[str, ...]:
    if "durable-learning" not in recommendation.tiers:
        return ("Keep lessons in the handoff until durable learning is needed.",)
    return (
        "Create insight index and graph files before repeated workflow lessons are lost.",
        "Record synthesized learning in insights/ instead of chat-only notes.",
    )


def _skill_actions_for_recommendation(
    recommendation: SpawnedProjectRecommendation,
) -> tuple[str, ...]:
    if "repo-local-skills" not in _recommended_action_tiers(recommendation):
        return ("Skip repo-local skills until a repeated project workflow appears.",)
    return (
        "Create only project-specific skills that remove repeated instructions.",
        "Validate skill inventory before publication.",
    )


def _source_study_actions_for_recommendation(
    recommendation: SpawnedProjectRecommendation,
) -> tuple[str, ...]:
    if "source-study" not in _recommended_action_tiers(recommendation):
        return ("Skip source-study surfaces unless OSS/source inspiration is actually used.",)
    return (
        "Create sources/README.md before importing or studying external source material.",
        "Record attribution posture before publication.",
    )


def _first_task_for_recommendation(
    recommendation: SpawnedProjectRecommendation,
    file_actions: tuple[SpawnedProjectScaffoldAction, ...],
) -> SpawnedProjectFirstTaskProposal:
    if "prototype-light" in recommendation.tiers:
        return SpawnedProjectFirstTaskProposal(
            title="Build first prototype slice",
            task_type="AFK",
            status="ready",
            goal="Create one directly verifiable prototype slice before adding optional ceremony.",
            acceptance_criteria=(
                "The prototype behavior is usable and covered by a focused check.",
            ),
            verification_commands=recommendation.verification_commands,
            allowed_paths=("README.md", "scripts/verify.py"),
            review_required=False,
        )
    return SpawnedProjectFirstTaskProposal(
        title="Bootstrap spawned project scaffold",
        task_type="AFK",
        status="ready",
        goal="Create the selected scaffold files and seed the first vertical implementation slice.",
        acceptance_criteria=(
            "Selected scaffold files exist with project-specific goals and acceptance criteria.",
            "Verification commands pass for the scaffold.",
            "HANDOFF.md contains a compact current resume snapshot.",
        ),
        verification_commands=("python -B scripts/verify.py",),
        allowed_paths=tuple(
            _allowed_path_for_scaffold_action(action.path) for action in file_actions
        ),
        review_required=False,
    )


def _allowed_path_for_scaffold_action(path: str) -> str:
    if path.endswith("/"):
        return f"{path.rstrip('/')}/**"
    return path


def _recommended_action_tiers(
    recommendation: SpawnedProjectRecommendation,
) -> frozenset[str]:
    return frozenset(action.tier for action in _file_actions_for_recommendation(recommendation))
