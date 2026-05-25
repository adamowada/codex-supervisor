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
DURABLE_LEARNING_FILES = ("insights/graph.md",)
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
        verification_commands=recommendation.verification_commands,
        allowed_paths=tuple(action.path for action in file_actions),
        review_required=True,
    )


def _recommended_action_tiers(
    recommendation: SpawnedProjectRecommendation,
) -> frozenset[str]:
    return frozenset(action.tier for action in _file_actions_for_recommendation(recommendation))
