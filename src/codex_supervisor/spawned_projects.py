"""Spawned-project scaffold recommendation contracts."""

from __future__ import annotations

from dataclasses import dataclass

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
DURABLE_LEARNING_FILES = (
    "insights/graph.md",
    "insights/open-questions.md",
)
REPO_LOCAL_SKILL_FILES = (
    "scripts/check_skill_inventory.py",
    ".agents/skills/",
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
    )


def _needs_supervisor_managed_tier(brief: SpawnedProjectBrief) -> bool:
    return (
        brief.production_intended
        or brief.unattended_workers
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
