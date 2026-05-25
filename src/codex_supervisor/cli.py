"""Command line entry point for codex-supervisor."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import fields, is_dataclass
from functools import partial
from pathlib import Path
from typing import Any, cast

from codex_supervisor.codex_automation import (
    CodexAutomationBridgeDryRunReport,
    build_codex_automation_bridge_dry_run,
    default_codex_automation_bridge_specs,
)
from codex_supervisor.codex_state import (
    CodexStateInventory,
    CodexStateObservationReport,
    CodexStateReconciliationDryRunReport,
    build_codex_state_observation_report,
    build_codex_state_reconciliation_dry_run,
    inventory_codex_state,
)
from codex_supervisor.codex_state_reconciliation import (
    CodexStateReconciliationApplyError,
    CodexStateReconciliationApplyReport,
    apply_codex_state_reconciliation_report,
    codex_state_reconciliation_report_from_payload,
)
from codex_supervisor.factory_demo import (
    FactoryLoopDemoReport,
    run_factory_loop_demo,
)
from codex_supervisor.goal_contracts import (
    render_goal_contract,
    render_goal_contract_markdown,
)
from codex_supervisor.insight_updates import (
    AppliedInsightUpdate,
    InsightMarkdownUpdate,
    InsightUpdateError,
    apply_insight_update,
    render_insight_markdown_update,
)
from codex_supervisor.insights import (
    InsightContractError,
    InsightRecord,
    validate_insight_record_payload,
)
from codex_supervisor.paths import default_planning_database_path
from codex_supervisor.planning import (
    CLAIM_WORKER_RUN_STATUSES,
    CRITERION_STATUSES,
    CURRENT_QUEUE_PLAN_STATUSES,
    MILESTONE_STATUSES,
    PLAN_STATUSES,
    TASK_STATUSES,
    TASK_TYPES,
    WORKER_RUN_STATUSES,
    CiRunEvidenceRecord,
    IssueCommentEvidenceRecord,
    PlanAcceptanceCriterionRecord,
    PlanArtifactLinkRecord,
    PlanCommitLinkRecord,
    PlanDecisionRecord,
    PlanMilestoneRecord,
    PlanningSQLiteStore,
    PlanningSummarySnapshot,
    PlanProgressRecord,
    PlanRecord,
    PullRequestEvidenceRecord,
    SupervisorTaskRecord,
    SupervisorTaskSummaryRecord,
    WorkerRunRecord,
    has_nonterminal_worker_run,
    initialize_planning_database,
    missing_execution_contract_fields,
    open_existing_planning_database,
    unresolved_task_blockers,
)
from codex_supervisor.projects import (
    ProjectRegistryEntry,
    ProjectTaskSeed,
    build_project_task_seeds,
    discover_projects,
)
from codex_supervisor.release import (
    ReleaseReadinessReport,
    build_release_readiness_report,
)
from codex_supervisor.review_loop import (
    ReviewContractError,
    ReviewResult,
    validate_review_result_payload,
)
from codex_supervisor.review_persistence import (
    LiveReviewRunResult,
    ReviewResultPersistenceRecord,
    record_review_result,
    run_live_review_for_task,
)
from codex_supervisor.review_repairs import (
    DEFAULT_REPAIR_VERIFICATION_COMMANDS,
    ReviewRepairRoutingResult,
    apply_repair_task_plan,
    plan_repair_tasks_from_review_result,
)
from codex_supervisor.skill_promotion import (
    SkillPromotionContractError,
    SkillPromotionProposal,
    validate_skill_promotion_payload,
)
from codex_supervisor.spawned_projects import (
    PROJECT_COMPLEXITIES,
    TRUST_POLICIES,
    SpawnedProjectBrief,
    SpawnedProjectRecommendation,
    SpawnedProjectScaffoldApplyResult,
    SpawnedProjectScaffoldProposal,
    apply_spawned_project_scaffold,
    build_spawned_project_scaffold_proposal,
    recommend_spawned_project_scaffold,
)
from codex_supervisor.story_loop import (
    build_story_loop_status,
    record_story_loop_progress,
    run_live_story_loop_once,
)
from codex_supervisor.worktree_artifacts import WorktreeArtifactError
from codex_supervisor.worktree_cleanup import CleanupPlan, plan_cleanup_targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="codex-supervisor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("plan-init", help="Initialize planning SQLite")
    init_parser.add_argument("--path", type=Path, default=None)
    init_parser.add_argument("--seed-bootstrap-plan", action="store_true", default=False)

    migrate_parser = subparsers.add_parser(
        "plan-migrate-schema",
        help="Apply tracked planning SQLite schema migrations",
    )
    migrate_parser.add_argument("--path", type=Path, default=None)

    project_list_parser = subparsers.add_parser(
        "project-list",
        help="List supervised project roots and adapter facts",
    )
    project_list_parser.add_argument(
        "--root",
        action="append",
        type=Path,
        default=None,
        help="Explicit project root to inspect. Defaults to the current working directory.",
    )
    project_list_parser.add_argument("--trust-policy", default="local_trusted")
    project_list_parser.add_argument("--json", action="store_true", default=False)

    project_seed_parser = subparsers.add_parser(
        "project-seed-tasks",
        help="Seed supervisor tasks from project adapter candidate tasks",
    )
    project_seed_parser.add_argument("--path", type=Path, default=None)
    project_seed_parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Project root to inspect. Defaults to the current working directory.",
    )
    project_seed_parser.add_argument("--plan-id", required=True)
    project_seed_parser.add_argument("--trust-policy", default="local_trusted")
    project_seed_parser.add_argument(
        "--status",
        choices=("blocked", "pending", "ready"),
        default="pending",
    )
    project_seed_parser.add_argument("--worker-backend", default="codex_exec")
    project_seed_parser.add_argument(
        "--review-required",
        dest="review_required",
        action="store_true",
        default=True,
    )
    project_seed_parser.add_argument(
        "--no-review-required",
        dest="review_required",
        action="store_false",
    )
    project_seed_parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Write the generated task seeds to planning SQLite. Omit for dry-run output.",
    )
    project_seed_parser.add_argument("--json", action="store_true", default=False)

    spawned_classify_parser = subparsers.add_parser(
        "spawned-project-classify",
        help="Dry-run spawned project scaffold tier recommendation",
    )
    _add_spawned_project_brief_arguments(spawned_classify_parser)

    spawned_propose_parser = subparsers.add_parser(
        "spawned-project-propose",
        help="Dry-run spawned project scaffold file and task proposal",
    )
    _add_spawned_project_brief_arguments(spawned_propose_parser)

    spawned_apply_parser = subparsers.add_parser(
        "spawned-project-apply",
        help="Write the selected spawned project scaffold into a target root",
    )
    _add_spawned_project_brief_arguments(spawned_apply_parser)
    spawned_apply_parser.add_argument("--target-root", type=Path, required=True)

    release_readiness_parser = subparsers.add_parser(
        "release-readiness",
        help="Dry-run release readiness audit from repo-owned evidence",
    )
    release_readiness_parser.add_argument("--repo-root", type=Path, default=None)
    release_readiness_parser.add_argument("--planning-db", type=Path, default=None)
    release_readiness_parser.add_argument("--commit", default=None)
    release_readiness_parser.add_argument("--json", action="store_true", default=False)

    factory_demo_parser = subparsers.add_parser(
        "factory-loop-demo",
        help="Run a deterministic throwaway factory-loop demo",
    )
    factory_demo_parser.add_argument("--workspace", type=Path, default=None)
    factory_demo_parser.add_argument("--keep-workspace", action="store_true", default=False)
    factory_demo_parser.add_argument("--json", action="store_true", default=False)

    list_parser = subparsers.add_parser("plan-list", help="List plans")
    list_parser.add_argument("--path", type=Path, default=None)
    list_parser.add_argument("--status", choices=sorted(PLAN_STATUSES), default=None)
    list_parser.add_argument("--json", action="store_true", default=False)

    summary_parser = subparsers.add_parser(
        "plan-summary",
        help="Summarize plans, milestones, decisions, progress, and tasks",
    )
    summary_parser.add_argument("--path", type=Path, default=None)
    summary_parser.add_argument("--plan-id", default=None)
    summary_parser.add_argument("--active-only", action="store_true", default=False)
    summary_parser.add_argument(
        "--current-queue",
        action="store_true",
        default=False,
        help="Summarize active and blocked current-queue plans.",
    )
    summary_parser.add_argument("--json", action="store_true", default=False)

    task_list_parser = subparsers.add_parser("task-list", help="List supervisor tasks")
    task_list_parser.add_argument("--path", type=Path, default=None)
    task_list_parser.add_argument("--status", choices=sorted(TASK_STATUSES), default=None)
    task_list_parser.add_argument("--active-plans-only", action="store_true", default=False)
    task_list_parser.add_argument(
        "--current-queue-plans-only",
        action="store_true",
        default=False,
        help="List tasks attached to active and blocked current-queue plans.",
    )
    task_list_parser.add_argument("--json", action="store_true", default=False)

    task_show_parser = subparsers.add_parser("task-show", help="Show one supervisor task")
    task_show_parser.add_argument("task_id")
    task_show_parser.add_argument("--path", type=Path, default=None)
    task_show_parser.add_argument("--json", action="store_true", default=False)

    worker_list_parser = subparsers.add_parser("worker-run-list", help="List worker runs")
    worker_list_parser.add_argument("--path", type=Path, default=None)
    worker_list_parser.add_argument("--task-id", default=None)
    worker_list_parser.add_argument("--json", action="store_true", default=False)

    worker_show_parser = subparsers.add_parser("worker-run-show", help="Show one worker run")
    worker_show_parser.add_argument("worker_run_id")
    worker_show_parser.add_argument("--path", type=Path, default=None)
    worker_show_parser.add_argument("--json", action="store_true", default=False)

    worker_result_list_parser = subparsers.add_parser(
        "worker-result-list",
        help="List DB-backed worker result records",
    )
    worker_result_list_parser.add_argument("--path", type=Path, default=None)
    worker_result_list_parser.add_argument("--json", action="store_true", default=False)

    worker_result_show_parser = subparsers.add_parser(
        "worker-result-show",
        help="Show one DB-backed worker result record",
    )
    worker_result_show_parser.add_argument("result_id")
    worker_result_show_parser.add_argument("--path", type=Path, default=None)
    worker_result_show_parser.add_argument("--json", action="store_true", default=False)

    current_task_parser = subparsers.add_parser(
        "task-current",
        help="Show the highest-priority unblocked ready AFK task attached to an active plan",
    )
    current_task_parser.add_argument("--path", type=Path, default=None)
    current_task_parser.add_argument("--json", action="store_true", default=False)

    task_claim_parser = subparsers.add_parser(
        "task-claim",
        help="Atomically claim the current ready AFK task and create a worker run",
    )
    task_claim_parser.add_argument("--path", type=Path, default=None)
    task_claim_parser.add_argument(
        "--task-id",
        default=None,
        help="Only claim this ready AFK task; return null if another task is current.",
    )
    task_claim_parser.add_argument("--worker-run-id", required=True)
    task_claim_parser.add_argument("--backend", default="codex_exec")
    task_claim_parser.add_argument(
        "--status",
        choices=sorted(CLAIM_WORKER_RUN_STATUSES),
        default="running",
    )
    task_claim_parser.add_argument("--worktree-path", default=None)
    task_claim_parser.add_argument("--prompt-path", default=None)
    task_claim_parser.add_argument("--jsonl-path", default=None)
    task_claim_parser.add_argument("--metadata-json", type=_json_object_arg, default={})
    task_claim_parser.add_argument("--json", action="store_true", default=False)

    goal_contract_parser = subparsers.add_parser(
        "goal-contract-render",
        help="Render a worker-ready Goal Contract for a supervisor task",
    )
    goal_contract_parser.add_argument("--path", type=Path, default=None)
    goal_contract_parser.add_argument(
        "--task-id",
        default=None,
        help="Task to render. Defaults to the current ready AFK task.",
    )
    goal_contract_parser.add_argument("--json", action="store_true", default=False)

    story_status_parser = subparsers.add_parser(
        "story-loop-status",
        help="Report Story Loop status from canonical planning state",
    )
    story_status_parser.add_argument("--path", type=Path, default=None)
    story_status_parser.add_argument("--plan-id", default=None)
    story_status_parser.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Include completed, abandoned, and superseded historical plans.",
    )
    story_status_parser.add_argument("--json", action="store_true", default=False)

    story_record_parser = subparsers.add_parser(
        "story-loop-record",
        help="Record Story Loop progress and artifact links",
    )
    story_record_parser.add_argument("--path", type=Path, default=None)
    story_record_parser.add_argument("--progress-id", required=True)
    story_record_parser.add_argument("--plan-id", required=True)
    story_record_parser.add_argument("--event-type", default="story-loop-iteration")
    story_record_parser.add_argument("--summary", required=True)
    story_record_parser.add_argument("--details", default=None)
    story_record_parser.add_argument("--task-id", default=None)
    story_record_parser.add_argument("--worker-run-id", default=None)
    story_record_parser.add_argument("--artifact-id", action="append", default=[])
    story_record_parser.add_argument(
        "--artifact-relationship",
        default="story-loop-evidence",
    )
    story_record_parser.add_argument("--linked-artifact-id", default=None)
    story_record_parser.add_argument("--json", action="store_true", default=False)

    story_run_parser = subparsers.add_parser(
        "story-loop-run-once",
        help="Claim and run one ready AFK task through the live Codex Exec worker path",
    )
    story_run_parser.add_argument("--path", type=Path, default=None)
    story_run_parser.add_argument("--repo-root", type=Path, default=None)
    story_run_parser.add_argument("--worker-run-id", required=True)
    story_run_parser.add_argument(
        "--result-schema-path",
        default=None,
        help="Override the generated ignored run-local Worker Result schema path.",
    )
    story_run_parser.add_argument("--sandbox-mode", default="workspace-write")
    story_run_parser.add_argument("--approval-policy", default="never")
    story_run_parser.add_argument("--codex-bin", default=None)
    story_run_parser.add_argument("--codex-home", default=None)
    story_run_parser.add_argument("--codex-config-path", default=None)
    story_run_parser.add_argument("--model", default=None)
    story_run_parser.add_argument("--reasoning-effort", default=None)
    story_run_parser.add_argument("--service-tier", default=None)
    story_run_parser.add_argument("--native-goal-mode", action="store_true", default=False)
    story_run_parser.add_argument("--ignore-user-config", action="store_true", default=False)
    story_run_parser.add_argument("--environment-json", type=_json_object_arg, default={})
    story_run_parser.add_argument("--json", action="store_true", default=False)

    decision_add_parser = subparsers.add_parser("decision-add", help="Record a plan decision")
    decision_add_parser.add_argument("--path", type=Path, default=None)
    decision_add_parser.add_argument("--decision-id", required=True)
    decision_add_parser.add_argument("--plan-id", required=True)
    decision_add_parser.add_argument("--decision", required=True)
    decision_add_parser.add_argument("--rationale", required=True)
    decision_add_parser.add_argument("--alternatives-considered", default=None)
    decision_add_parser.add_argument("--consequences", default=None)
    decision_add_parser.add_argument("--json", action="store_true", default=False)

    progress_add_parser = subparsers.add_parser("progress-add", help="Record plan progress")
    progress_add_parser.add_argument("--path", type=Path, default=None)
    progress_add_parser.add_argument("--progress-id", required=True)
    progress_add_parser.add_argument("--plan-id", required=True)
    progress_add_parser.add_argument("--event-type", required=True)
    progress_add_parser.add_argument("--summary", required=True)
    progress_add_parser.add_argument("--details", default=None)
    progress_add_parser.add_argument("--linked-artifact-id", default=None)
    progress_add_parser.add_argument("--json", action="store_true", default=False)

    artifact_add_parser = subparsers.add_parser("artifact-link-add", help="Link a plan artifact")
    artifact_add_parser.add_argument("--path", type=Path, default=None)
    artifact_add_parser.add_argument("--plan-id", required=True)
    artifact_add_parser.add_argument("--artifact-id", required=True)
    artifact_add_parser.add_argument("--relationship", required=True)
    artifact_add_parser.add_argument("--json", action="store_true", default=False)

    commit_add_parser = subparsers.add_parser("commit-link-add", help="Link a plan commit")
    commit_add_parser.add_argument("--path", type=Path, default=None)
    commit_add_parser.add_argument("--plan-id", required=True)
    commit_add_parser.add_argument("--commit-sha", required=True)
    commit_add_parser.add_argument("--relationship", required=True)
    commit_add_parser.add_argument("--json", action="store_true", default=False)

    ci_run_parser = subparsers.add_parser(
        "ci-run-record",
        help=(
            "Record CI run evidence as planning progress, an optional artifact link, "
            "and a commit link"
        ),
    )
    ci_run_parser.add_argument("--path", type=Path, default=None)
    ci_run_parser.add_argument("--progress-id", required=True)
    ci_run_parser.add_argument("--plan-id", required=True)
    ci_run_parser.add_argument("--provider", default="github-actions")
    ci_run_parser.add_argument("--run-id", required=True)
    ci_run_parser.add_argument("--run-url", required=True)
    ci_run_parser.add_argument("--head-sha", required=True)
    ci_run_parser.add_argument("--status", required=True)
    ci_run_parser.add_argument("--conclusion", required=True)
    ci_run_parser.add_argument("--workflow", default=None)
    ci_run_parser.add_argument("--job-id", default=None)
    ci_run_parser.add_argument("--job-name", default=None)
    ci_run_parser.add_argument("--event", default=None)
    ci_run_parser.add_argument("--summary", default=None)
    ci_run_parser.add_argument("--artifact-id", default=None)
    ci_run_parser.add_argument("--artifact-relationship", default="ci-run")
    ci_run_parser.add_argument("--commit-relationship", default="ci-head")
    ci_run_parser.add_argument("--json", action="store_true", default=False)

    pr_parser = subparsers.add_parser(
        "pr-evidence-record",
        help="Record pull request evidence as planning progress and optional links",
    )
    pr_parser.add_argument("--path", type=Path, default=None)
    pr_parser.add_argument("--progress-id", required=True)
    pr_parser.add_argument("--plan-id", required=True)
    pr_parser.add_argument("--provider", default="github")
    pr_parser.add_argument("--repository", required=True)
    pr_parser.add_argument("--pr-number", type=int, required=True)
    pr_parser.add_argument("--pr-url", required=True)
    pr_parser.add_argument("--state", required=True)
    pr_parser.add_argument("--title", default=None)
    pr_parser.add_argument("--summary", default=None)
    pr_parser.add_argument("--head-ref", default=None)
    pr_parser.add_argument("--base-ref", default=None)
    pr_parser.add_argument("--head-sha", default=None)
    pr_parser.add_argument("--base-sha", default=None)
    pr_parser.add_argument("--draft", action="store_true", default=False)
    pr_parser.add_argument("--merged", action="store_true", default=False)
    pr_parser.add_argument("--issue-number", type=int, default=None)
    pr_parser.add_argument("--artifact-id", default=None)
    pr_parser.add_argument("--artifact-relationship", default="pr-evidence")
    pr_parser.add_argument("--commit-relationship", default="pr-head")
    pr_parser.add_argument("--json", action="store_true", default=False)

    issue_comment_parser = subparsers.add_parser(
        "issue-comment-record",
        help="Record issue comment evidence as planning progress and optional links",
    )
    issue_comment_parser.add_argument("--path", type=Path, default=None)
    issue_comment_parser.add_argument("--progress-id", required=True)
    issue_comment_parser.add_argument("--plan-id", required=True)
    issue_comment_parser.add_argument("--provider", default="github")
    issue_comment_parser.add_argument("--repository", required=True)
    issue_comment_parser.add_argument("--issue-number", type=int, required=True)
    issue_comment_parser.add_argument("--comment-id", required=True)
    issue_comment_parser.add_argument("--comment-url", required=True)
    issue_comment_parser.add_argument("--summary", default=None)
    issue_comment_parser.add_argument("--details", default=None)
    issue_comment_parser.add_argument("--pr-number", type=int, default=None)
    issue_comment_parser.add_argument("--author", default=None)
    issue_comment_parser.add_argument("--commit-sha", default=None)
    issue_comment_parser.add_argument("--artifact-id", default=None)
    issue_comment_parser.add_argument("--artifact-relationship", default="issue-comment")
    issue_comment_parser.add_argument("--commit-relationship", default="issue-comment-commit")
    issue_comment_parser.add_argument("--json", action="store_true", default=False)

    commit_delete_parser = subparsers.add_parser("commit-link-delete", help="Unlink a plan commit")
    commit_delete_parser.add_argument("--path", type=Path, default=None)
    commit_delete_parser.add_argument("--plan-id", required=True)
    commit_delete_parser.add_argument("--commit-sha", required=True)
    commit_delete_parser.add_argument("--relationship", required=True)
    commit_delete_parser.add_argument("--json", action="store_true", default=False)

    task_upsert_parser = subparsers.add_parser(
        "task-upsert",
        help="Create a task or safely update one while preserving omitted optional fields",
    )
    task_upsert_parser.add_argument("--path", type=Path, default=None)
    task_upsert_parser.add_argument("--task-id", required=True)
    task_upsert_parser.add_argument("--plan-id", required=True)
    task_upsert_parser.add_argument("--title", required=True)
    task_upsert_parser.add_argument("--goal", required=True)
    task_upsert_parser.add_argument("--task-type", choices=sorted(TASK_TYPES), required=True)
    task_upsert_parser.add_argument("--status", choices=sorted(TASK_STATUSES), required=True)
    task_upsert_parser.add_argument("--scope-json", type=_json_object_arg, default=None)
    task_upsert_parser.add_argument("--out-of-scope-json", type=_json_object_arg, default=None)
    task_upsert_parser.add_argument("--acceptance-criterion", action="append", default=None)
    task_upsert_parser.add_argument("--verification-command", action="append", default=None)
    task_upsert_parser.add_argument("--allowed-path", action="append", default=None)
    task_upsert_parser.add_argument("--blocked-by", action="append", default=None)
    task_upsert_parser.add_argument("--worker-backend", default=None)
    task_upsert_parser.add_argument(
        "--review-required",
        dest="review_required",
        action="store_true",
    )
    task_upsert_parser.add_argument(
        "--no-review-required",
        dest="review_required",
        action="store_false",
    )
    task_upsert_parser.set_defaults(review_required=None)
    task_upsert_parser.add_argument(
        "--replace",
        action="store_true",
        default=False,
        help="Reset omitted optional fields instead of preserving them.",
    )
    task_upsert_parser.add_argument("--json", action="store_true", default=False)

    worker_upsert_parser = subparsers.add_parser(
        "worker-run-upsert",
        help="Create a run or safely update one while preserving omitted evidence fields",
    )
    worker_upsert_parser.add_argument("--path", type=Path, default=None)
    worker_upsert_parser.add_argument("--worker-run-id", required=True)
    worker_upsert_parser.add_argument("--task-id", required=True)
    worker_upsert_parser.add_argument("--backend", required=True)
    worker_upsert_parser.add_argument(
        "--status", choices=sorted(WORKER_RUN_STATUSES), required=True
    )
    worker_upsert_parser.add_argument("--worktree-path", default=None)
    worker_upsert_parser.add_argument("--prompt-path", default=None)
    worker_upsert_parser.add_argument("--jsonl-path", default=None)
    worker_upsert_parser.add_argument("--result-path", default=None)
    worker_upsert_parser.add_argument("--result-id", default=None)
    worker_upsert_parser.add_argument("--started-at", default=None)
    worker_upsert_parser.add_argument("--completed-at", default=None)
    worker_upsert_parser.add_argument("--failure-class", default=None)
    worker_upsert_parser.add_argument("--metadata-json", type=_json_object_arg, default=None)
    worker_upsert_parser.add_argument(
        "--replace",
        action="store_true",
        default=False,
        help="Replace omitted optional fields with null/default values instead of preserving them.",
    )
    worker_upsert_parser.add_argument("--json", action="store_true", default=False)

    plan_upsert_parser = subparsers.add_parser("plan-upsert", help="Create or update a plan")
    plan_upsert_parser.add_argument("--path", type=Path, default=None)
    plan_upsert_parser.add_argument("--plan-id", required=True)
    plan_upsert_parser.add_argument("--slug", required=True)
    plan_upsert_parser.add_argument("--title", required=True)
    plan_upsert_parser.add_argument("--goal", required=True)
    plan_upsert_parser.add_argument("--status", choices=sorted(PLAN_STATUSES), required=True)
    plan_upsert_parser.add_argument("--priority", type=int, default=0)
    plan_upsert_parser.add_argument("--owner-agent", default=None)
    plan_upsert_parser.add_argument("--non-goals-json", type=_json_object_arg, default={})
    plan_upsert_parser.add_argument("--context-json", type=_json_object_arg, default={})
    plan_upsert_parser.add_argument("--superseded-by-plan-id", default=None)
    plan_upsert_parser.add_argument("--json", action="store_true", default=False)

    milestone_upsert_parser = subparsers.add_parser(
        "milestone-upsert", help="Create or update a milestone"
    )
    milestone_upsert_parser.add_argument("--path", type=Path, default=None)
    milestone_upsert_parser.add_argument("--milestone-id", required=True)
    milestone_upsert_parser.add_argument("--plan-id", required=True)
    milestone_upsert_parser.add_argument("--title", required=True)
    milestone_upsert_parser.add_argument(
        "--status", choices=sorted(MILESTONE_STATUSES), required=True
    )
    milestone_upsert_parser.add_argument("--sort-order", type=int, default=0)
    milestone_upsert_parser.add_argument("--details-json", type=_json_object_arg, default={})
    milestone_upsert_parser.add_argument("--json", action="store_true", default=False)

    criterion_upsert_parser = subparsers.add_parser(
        "criterion-upsert", help="Create or update an acceptance criterion"
    )
    criterion_upsert_parser.add_argument("--path", type=Path, default=None)
    criterion_upsert_parser.add_argument("--criterion-id", required=True)
    criterion_upsert_parser.add_argument("--plan-id", required=True)
    criterion_upsert_parser.add_argument("--description", required=True)
    criterion_upsert_parser.add_argument(
        "--status", choices=sorted(CRITERION_STATUSES), required=True
    )
    criterion_upsert_parser.add_argument("--verification-command", default=None)
    criterion_upsert_parser.add_argument("--json", action="store_true", default=False)

    plan_status_parser = subparsers.add_parser("plan-status", help="Update a plan status")
    plan_status_parser.add_argument("--path", type=Path, default=None)
    plan_status_parser.add_argument("--plan-id", required=True)
    plan_status_parser.add_argument("--status", choices=sorted(PLAN_STATUSES), required=True)
    plan_status_parser.add_argument("--superseded-by-plan-id", default=None)

    milestone_status_parser = subparsers.add_parser(
        "milestone-status", help="Update a milestone status"
    )
    milestone_status_parser.add_argument("--path", type=Path, default=None)
    milestone_status_parser.add_argument("--milestone-id", required=True)
    milestone_status_parser.add_argument(
        "--status", choices=sorted(MILESTONE_STATUSES), required=True
    )

    criterion_status_parser = subparsers.add_parser(
        "criterion-status", help="Update an acceptance criterion status"
    )
    criterion_status_parser.add_argument("--path", type=Path, default=None)
    criterion_status_parser.add_argument("--criterion-id", required=True)
    criterion_status_parser.add_argument(
        "--status", choices=sorted(CRITERION_STATUSES), required=True
    )

    task_status_parser = subparsers.add_parser("task-status", help="Update a task status")
    task_status_parser.add_argument("--path", type=Path, default=None)
    task_status_parser.add_argument("--task-id", required=True)
    task_status_parser.add_argument("--status", choices=sorted(TASK_STATUSES), required=True)

    worker_status_parser = subparsers.add_parser("worker-run-status", help="Update run status")
    worker_status_parser.add_argument("--path", type=Path, default=None)
    worker_status_parser.add_argument("--worker-run-id", required=True)
    worker_status_parser.add_argument(
        "--status", choices=sorted(WORKER_RUN_STATUSES), required=True
    )
    worker_status_parser.add_argument("--failure-class", default=None)
    worker_status_parser.add_argument("--completed-at", default=None)
    worker_status_parser.add_argument("--result-path", default=None)
    worker_status_parser.add_argument("--result-id", default=None)

    review_ingest_parser = subparsers.add_parser(
        "review-result-ingest",
        help="Validate and persist a structured review result JSON file",
    )
    review_ingest_parser.add_argument("--path", type=Path, default=None)
    review_ingest_parser.add_argument("--plan-id", required=True)
    review_ingest_parser.add_argument("--progress-id", required=True)
    review_ingest_parser.add_argument("--review-result-path", type=Path, required=True)
    review_ingest_parser.add_argument(
        "--review-result-artifact-id",
        default=None,
        help=(
            "Repo-relative artifact ID for the review result JSON. Defaults to "
            "--review-result-path when it is repo-relative or under the current directory."
        ),
    )
    review_ingest_parser.add_argument("--review-artifact-id", action="append", default=[])
    review_ingest_parser.add_argument("--create-repair-tasks", action="store_true", default=False)
    review_ingest_parser.add_argument("--source-task-id", default=None)
    review_ingest_parser.add_argument("--repair-task-id-prefix", default="task-review-repair")
    review_ingest_parser.add_argument(
        "--repair-verification-command",
        action="append",
        default=None,
    )
    review_ingest_parser.add_argument("--json", action="store_true", default=False)

    review_live_parser = subparsers.add_parser(
        "review-run-live",
        help="Launch Codex Exec as a structured live reviewer for one task",
    )
    review_live_parser.add_argument("--path", type=Path, default=None)
    review_live_parser.add_argument("--task-id", required=True)
    review_live_parser.add_argument("--review-id", required=True)
    review_live_parser.add_argument("--repo-root", type=Path, default=Path("."))
    review_live_parser.add_argument(
        "--mode",
        choices=("everything", "code_quality", "architecture", "source_of_truth_drift"),
        default="everything",
    )
    review_live_parser.add_argument("--target", default=None)
    review_live_parser.add_argument("--progress-id", default=None)
    review_live_parser.add_argument("--review-result-artifact-id", required=True)
    review_live_parser.add_argument("--review-artifact-id", action="append", default=[])
    review_live_parser.add_argument(
        "--no-create-repair-tasks",
        action="store_false",
        dest="create_repair_tasks",
        default=True,
    )
    review_live_parser.add_argument("--repair-task-id-prefix", default="task-review-repair")
    review_live_parser.add_argument(
        "--repair-verification-command",
        action="append",
        default=None,
    )
    review_live_parser.add_argument("--codex-bin", dest="codex_executable", default=None)
    review_live_parser.add_argument("--codex-home", default=None)
    review_live_parser.add_argument("--model", default=None)
    review_live_parser.add_argument("--sandbox-mode", default="workspace-write")
    review_live_parser.add_argument("--approval-policy", default="never")
    review_live_parser.add_argument("--json", action="store_true", default=False)

    insight_validate_parser = subparsers.add_parser(
        "insight-validate",
        help="Validate a reusable insight JSON file without writing durable state",
    )
    insight_validate_parser.add_argument("--insight-path", type=Path, required=True)
    insight_validate_parser.add_argument("--json", action="store_true", default=False)

    insight_update_parser = subparsers.add_parser(
        "insight-update",
        help="Render or apply a guarded reusable insight markdown update",
    )
    insight_update_parser.add_argument("--insight-path", type=Path, required=True)
    insight_update_parser.add_argument(
        "--target-path",
        type=Path,
        default=None,
        help="Markdown file to update. Omit to print only the rendered update block.",
    )
    insight_update_parser.add_argument("--promotion-criterion", action="append", default=[])
    insight_update_parser.add_argument("--provenance", action="append", default=[])
    insight_update_parser.add_argument("--json", action="store_true", default=False)

    skill_promotion_parser = subparsers.add_parser(
        "skill-promotion-validate",
        help="Validate a skill promotion proposal without writing durable state",
    )
    skill_promotion_parser.add_argument("--proposal-path", type=Path, required=True)
    skill_promotion_parser.add_argument("--json", action="store_true", default=False)

    codex_state_parser = subparsers.add_parser(
        "codex-state-inventory",
        help="Inventory documented Codex local SQLite databases read-only",
    )
    codex_state_parser.add_argument("--codex-home", type=Path, required=True)
    codex_state_parser.add_argument("--observed-at", default=None)
    codex_state_parser.add_argument("--json", action="store_true", default=False)

    codex_observation_parser = subparsers.add_parser(
        "codex-state-observations",
        help="Build privacy-safe Codex local-state observation summaries",
    )
    codex_observation_parser.add_argument("--codex-home", type=Path, required=True)
    codex_observation_parser.add_argument("--linked-plan-id", default="")
    codex_observation_parser.add_argument("--linked-task-id", default="")
    codex_observation_parser.add_argument("--observed-at", default=None)
    codex_observation_parser.add_argument("--json", action="store_true", default=False)

    codex_reconciliation_parser = subparsers.add_parser(
        "codex-state-reconcile-dry-run",
        help="Build a non-mutating Codex local-state reconciliation proposal report",
    )
    codex_reconciliation_parser.add_argument("--codex-home", type=Path, required=True)
    codex_reconciliation_parser.add_argument("--linked-plan-id", default="")
    codex_reconciliation_parser.add_argument("--linked-task-id", default="")
    codex_reconciliation_parser.add_argument("--known-plan-id", action="append", default=None)
    codex_reconciliation_parser.add_argument("--known-task-id", action="append", default=None)
    codex_reconciliation_parser.add_argument("--observed-at", default=None)
    codex_reconciliation_parser.add_argument("--json", action="store_true", default=False)

    codex_reconciliation_apply_parser = subparsers.add_parser(
        "codex-state-reconcile-apply",
        help="Apply reviewed Codex local-state reconciliation proposals to planning evidence",
    )
    codex_reconciliation_apply_parser.add_argument("--path", type=Path, default=None)
    codex_reconciliation_apply_parser.add_argument("--report-path", type=Path, required=True)
    codex_reconciliation_apply_parser.add_argument(
        "--approve-proposal-id",
        action="append",
        default=[],
        help="Proposal ID from a reviewed dry-run report to apply. Repeat for multiple IDs.",
    )
    codex_reconciliation_apply_parser.add_argument("--json", action="store_true", default=False)

    codex_automation_parser = subparsers.add_parser(
        "codex-automation-dry-run",
        help="Build non-mutating official Codex automation proposals",
    )
    codex_automation_parser.add_argument("--workspace-root", type=Path, required=True)
    codex_automation_parser.add_argument("--queue-reconciliation-rrule", required=True)
    codex_automation_parser.add_argument("--health-check-rrule", required=True)
    codex_automation_parser.add_argument("--source-plan-id", default="")
    codex_automation_parser.add_argument("--source-task-id", default="")
    codex_automation_parser.add_argument("--model", default="")
    codex_automation_parser.add_argument("--reasoning-effort", default="")
    codex_automation_parser.add_argument(
        "--execution-environment",
        choices=("local", "worktree"),
        default="local",
    )
    codex_automation_parser.add_argument(
        "--status",
        choices=("ACTIVE", "PAUSED"),
        default="ACTIVE",
    )
    codex_automation_parser.add_argument("--observed-at", default=None)
    codex_automation_parser.add_argument("--json", action="store_true", default=False)

    cleanup_plan_parser = subparsers.add_parser(
        "cleanup-plan",
        help="Build a non-destructive cleanup plan for ignored runtime paths",
    )
    cleanup_plan_parser.add_argument("--workspace-root", type=Path, required=True)
    cleanup_plan_parser.add_argument("--candidate", type=Path, action="append", default=[])
    cleanup_plan_parser.add_argument("--active-worker-run-id", action="append", default=[])
    cleanup_plan_parser.add_argument("--reason", default="orphaned_runtime_path")
    cleanup_plan_parser.add_argument("--json", action="store_true", default=False)

    args = parser.parse_args(argv)

    if args.command == "plan-migrate-schema":
        resolved_path = _planning_path_or_report(args.path)
        if resolved_path is None:
            return 1
        if not resolved_path.exists():
            print(f"Planning database is not initialized: {resolved_path}", file=sys.stderr)
            return 1
        try:
            store = open_existing_planning_database(
                resolved_path,
                read_only=False,
                validate=False,
            )
            store.migrate_to_current_schema()
        except (ValueError, sqlite3.Error) as exc:
            print(f"Could not migrate planning database: {exc}", file=sys.stderr)
            return 1
        print(f"Migrated planning database to schema {store.schema_version()}")
        return 0

    if args.command == "project-list":
        roots = tuple(args.root or (Path.cwd(),))
        entries = discover_projects(roots, trust_policy=args.trust_policy)
        missing_entries = tuple(entry for entry in entries if entry.status == "missing")
        if missing_entries:
            for entry in missing_entries:
                message = entry.failure_reason or f"Project root does not exist: {entry.root_path}"
                print(message, file=sys.stderr)
            return 1
        if args.json:
            _print_json(entries)
            return 0
        _print_project_registry_entries(entries)
        return 0

    if args.command == "project-seed-tasks":
        entry = discover_projects(
            (args.root or Path.cwd(),),
            trust_policy=args.trust_policy,
        )[0]
        if entry.status != "ready":
            message = entry.failure_reason or f"Project is not seedable: {entry.root_path}"
            print(message, file=sys.stderr)
            return 1
        task_seeds = build_project_task_seeds(
            entry,
            plan_id=args.plan_id,
            status=args.status,
            worker_backend=args.worker_backend,
            review_required=args.review_required,
        )
        seed_result = {
            "project": entry,
            "task_seeds": task_seeds,
            "applied": args.apply,
            "task_ids": [seed.task_id for seed in task_seeds],
        }
        if not task_seeds:
            if args.json:
                _print_json(seed_result | {"message": "No project task candidates were found."})
            else:
                print(f"No project task candidates were found for {entry.root_path}.")
            return 1
        if args.apply:
            write_store = _open_write_store(args.path)
            if write_store is None:
                return 1
            for seed in task_seeds:
                record = _supervisor_task_record_from_project_task_seed(seed)
                if not _write_or_report(partial(_upsert_seeded_task, write_store, record)):
                    return 1
        if args.json:
            _print_json(seed_result)
        else:
            _print_project_task_seed_result(entry, task_seeds, applied=args.apply)
        return 0

    if args.command == "spawned-project-classify":
        recommendation = recommend_spawned_project_scaffold(_spawned_project_brief_from_args(args))
        if args.json:
            _print_json(recommendation)
        else:
            _print_spawned_project_recommendation(recommendation)
        return 0

    if args.command == "spawned-project-propose":
        proposal = build_spawned_project_scaffold_proposal(_spawned_project_brief_from_args(args))
        if args.json:
            _print_json(proposal)
        else:
            _print_spawned_project_proposal(proposal)
        return 0

    if args.command == "spawned-project-apply":
        apply_result = apply_spawned_project_scaffold(
            _spawned_project_brief_from_args(args),
            target_root=args.target_root,
        )
        if args.json:
            _print_json(apply_result)
        else:
            _print_spawned_project_apply_result(apply_result)
        return 0

    if args.command == "release-readiness":
        release_report = build_release_readiness_report(
            args.repo_root,
            planning_db_path=args.planning_db,
            target_commit=args.commit,
        )
        if args.json:
            _print_json(release_report)
        else:
            _print_release_readiness_report(release_report)
        return 0

    if args.command == "factory-loop-demo":
        if args.keep_workspace and args.workspace is None:
            print("--keep-workspace requires --workspace", file=sys.stderr)
            return 1
        factory_demo_report = run_factory_loop_demo(
            workspace_root=args.workspace,
            keep_workspace=args.keep_workspace,
        )
        if args.json:
            _print_json(factory_demo_report)
        else:
            _print_factory_loop_demo_report(factory_demo_report)
        return 0

    if args.command == "codex-state-inventory":
        inventory = inventory_codex_state(args.codex_home, observed_at=args.observed_at)
        if args.json:
            _print_json(inventory)
        else:
            _print_codex_state_inventory(inventory)
        return 0

    if args.command == "codex-state-observations":
        inventory = inventory_codex_state(args.codex_home, observed_at=args.observed_at)
        report = build_codex_state_observation_report(
            inventory,
            linked_plan_id=args.linked_plan_id,
            linked_task_id=args.linked_task_id,
        )
        if args.json:
            _print_json(report)
        else:
            _print_codex_state_observation_report(report)
        return 0

    if args.command == "codex-state-reconcile-dry-run":
        inventory = inventory_codex_state(args.codex_home, observed_at=args.observed_at)
        observation_report = build_codex_state_observation_report(
            inventory,
            linked_plan_id=args.linked_plan_id,
            linked_task_id=args.linked_task_id,
        )
        reconciliation_report = build_codex_state_reconciliation_dry_run(
            observation_report,
            known_plan_ids=None if args.known_plan_id is None else tuple(args.known_plan_id),
            known_task_ids=None if args.known_task_id is None else tuple(args.known_task_id),
        )
        if args.json:
            _print_json(reconciliation_report)
        else:
            _print_codex_state_reconciliation_dry_run(reconciliation_report)
        return 0

    if args.command == "codex-state-reconcile-apply":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        apply_store = write_store
        try:
            payload = json.loads(args.report_path.read_text(encoding="utf-8"))
            dry_run_report = codex_state_reconciliation_report_from_payload(payload)
        except (OSError, json.JSONDecodeError, CodexStateReconciliationApplyError) as exc:
            print(f"Could not read Codex state reconciliation report: {exc}", file=sys.stderr)
            return 1
        apply_report = _write_value_or_report(
            lambda: apply_codex_state_reconciliation_report(
                apply_store,
                dry_run_report,
                approved_proposal_ids=tuple(args.approve_proposal_id),
            )
        )
        if apply_report is None:
            return 1
        if args.json:
            _print_json(apply_report)
        else:
            _print_codex_state_reconciliation_apply_report(apply_report)
        return 0

    if args.command == "codex-automation-dry-run":
        automation_report = build_codex_automation_bridge_dry_run(
            workspace_root=args.workspace_root,
            specs=default_codex_automation_bridge_specs(
                queue_reconciliation_rrule=args.queue_reconciliation_rrule,
                health_check_rrule=args.health_check_rrule,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                status=args.status,
                execution_environment=args.execution_environment,
            ),
            source_plan_id=args.source_plan_id,
            source_task_id=args.source_task_id,
            observed_at=args.observed_at,
        )
        if args.json:
            _print_json(automation_report)
        else:
            _print_codex_automation_bridge_dry_run(automation_report)
        return 0

    if args.command == "cleanup-plan":
        try:
            cleanup_plan = plan_cleanup_targets(
                workspace_root=args.workspace_root,
                candidate_paths=tuple(args.candidate),
                active_worker_run_ids=tuple(args.active_worker_run_id),
                reason=args.reason,
            )
        except WorktreeArtifactError as exc:
            print(f"cleanup-plan failed: {exc}", file=sys.stderr)
            return 1
        if args.json:
            _print_json(cleanup_plan)
        else:
            _print_cleanup_plan(cleanup_plan)
        return 0

    if args.command == "plan-init":
        path = _planning_path_or_report(args.path)
        if path is None:
            return 1
        store = initialize_planning_database(path)
        if args.seed_bootstrap_plan:
            seed_bootstrap_plan(store)
        print(f"Initialized planning database: {path}")
        return 0

    if args.command == "plan-list":
        read_store = _open_read_store(args.path)
        if read_store is None:
            return 1
        plan_store = read_store
        plans = _read_or_report(lambda: plan_store.list_plans(status=args.status))
        if plans is None:
            return 1
        if not plans:
            if args.json:
                _print_json(())
                return 0
            print("No plans found.")
            return 0
        if args.json:
            _print_json(plans)
            return 0
        for plan in plans:
            print(f"{plan.plan_id}\t{plan.status}\tpriority={plan.priority}\t{plan.title}")
        return 0

    if args.command == "plan-summary":
        read_store = _open_read_store(args.path)
        if read_store is None:
            return 1
        snapshot = _read_or_report(read_store.read_summary_snapshot)
        if snapshot is None:
            return 1
        if args.plan_id is not None:
            plans = tuple(plan for plan in snapshot.plans if plan.plan_id == args.plan_id)
            if not plans:
                if args.json:
                    _print_json(())
                else:
                    print(f"No plan found: {args.plan_id}")
                return 1
        elif args.active_only and args.current_queue:
            print("--active-only and --current-queue are mutually exclusive", file=sys.stderr)
            return 1
        elif args.current_queue:
            plans = tuple(
                plan for plan in snapshot.plans if plan.status in CURRENT_QUEUE_PLAN_STATUSES
            )
        elif args.active_only:
            plans = tuple(plan for plan in snapshot.plans if plan.status == "active")
        else:
            plans = snapshot.plans
        summaries = tuple(_build_plan_summary_entry(snapshot, plan) for plan in plans)
        if args.json:
            _print_json(summaries)
            return 0
        for summary in summaries:
            _print_plan_summary(summary)
        return 0

    if args.command == "task-list":
        read_store = _open_read_store(args.path)
        if read_store is None:
            return 1
        if args.active_plans_only and args.current_queue_plans_only:
            print(
                "--active-plans-only and --current-queue-plans-only are mutually exclusive",
                file=sys.stderr,
            )
            return 1
        task_store = read_store
        tasks = _read_or_report(
            lambda: task_store.list_supervisor_tasks(
                status=args.status,
                active_plans_only=args.active_plans_only,
                current_queue_plans_only=args.current_queue_plans_only,
            )
        )
        if tasks is None:
            return 1
        if not tasks:
            if args.json:
                _print_json(())
                return 0
            print("No supervisor tasks found.")
            return 0
        if args.json:
            _print_json(tasks)
            return 0
        for task in tasks:
            print(
                f"{task.task_id}\t{task.status}\t{task.task_type}\t"
                f"plan={task.plan_id}({task.plan_status})\t{task.title}"
            )
        return 0

    if args.command == "task-show":
        read_store = _open_read_store(args.path)
        if read_store is None:
            return 1
        task_store = read_store
        tasks = _read_or_report(
            lambda: tuple(
                task for task in task_store.list_supervisor_tasks() if task.task_id == args.task_id
            )
        )
        if tasks is None:
            return 1
        if not tasks:
            if args.json:
                _print_json(None)
                return 1
            print(f"No supervisor task found: {args.task_id}")
            return 1
        if args.json:
            _print_json(tasks[0])
        else:
            _print_task_detail(tasks[0])
        return 0

    if args.command == "worker-run-list":
        read_store = _open_read_store(args.path)
        if read_store is None:
            return 1
        worker_store = read_store
        runs = _read_or_report(lambda: worker_store.list_worker_runs(task_id=args.task_id))
        if runs is None:
            return 1
        if not runs:
            if args.json:
                _print_json(())
                return 0
            print("No worker runs found.")
            return 0
        if args.json:
            _print_json(runs)
            return 0
        for run in runs:
            print(f"{run.worker_run_id}\t{run.status}\t{run.backend}\ttask={run.task_id}")
        return 0

    if args.command == "worker-run-show":
        read_store = _open_read_store(args.path)
        if read_store is None:
            return 1
        worker_store = read_store
        runs = _read_or_report(
            lambda: tuple(
                run
                for run in worker_store.list_worker_runs()
                if run.worker_run_id == args.worker_run_id
            )
        )
        if runs is None:
            return 1
        if not runs:
            if args.json:
                _print_json(None)
                return 1
            print(f"No worker run found: {args.worker_run_id}")
            return 1
        if args.json:
            _print_json(runs[0])
        else:
            run = runs[0]
            print(f"worker_run_id: {run.worker_run_id}")
            print(f"task_id: {run.task_id}")
            print(f"backend: {run.backend}")
            print(f"status: {run.status}")
            if run.result_id:
                print(f"result_id: {run.result_id}")
            if run.result_path:
                print(f"result_path: {run.result_path}")
        return 0

    if args.command == "worker-result-list":
        read_store = _open_read_store(args.path)
        if read_store is None:
            return 1
        worker_result_store = read_store
        results = _read_or_report(worker_result_store.list_worker_results)
        if results is None:
            return 1
        if args.json:
            _print_json(results)
            return 0
        if not results:
            print("No worker result records found.")
            return 0
        for worker_result_record in results:
            print(
                f"{worker_result_record.result_id}\t"
                f"{worker_result_record.status}\t"
                f"{worker_result_record.summary}"
            )
        return 0

    if args.command == "worker-result-show":
        read_store = _open_read_store(args.path)
        if read_store is None:
            return 1
        worker_result_store = read_store
        results = _read_or_report(
            lambda: tuple(
                result
                for result in worker_result_store.list_worker_results()
                if result.result_id == args.result_id
            )
        )
        if results is None:
            return 1
        if not results:
            if args.json:
                _print_json(None)
                return 1
            print(f"No worker result found: {args.result_id}")
            return 1
        if args.json:
            _print_json(results[0])
        else:
            worker_result = results[0]
            print(f"result_id: {worker_result.result_id}")
            print(f"status: {worker_result.status}")
            print(f"summary: {worker_result.summary}")
            if worker_result.source_path:
                print(f"source_path: {worker_result.source_path}")
        return 0

    if args.command == "task-current":
        read_store = _open_read_store(args.path)
        if read_store is None:
            return 1
        task_store = read_store
        current_task = _read_or_report(task_store.next_ready_afk_task)
        if current_task is None and _last_read_failed:
            return 1
        if current_task is not None:
            if args.json:
                _print_json(current_task)
            else:
                _print_task_detail(current_task)
            return 0
        if args.json:
            _print_json(None)
            return 0
        queue_snapshot = _read_or_report(
            lambda: (
                task_store.list_supervisor_tasks(),
                task_store.list_worker_runs(),
            )
        )
        if queue_snapshot is None:
            return 1
        ready_all_tasks, worker_runs = queue_snapshot
        all_ready_tasks = tuple(task for task in ready_all_tasks if task.status == "ready")
        if all_ready_tasks:
            print("No unblocked ready AFK tasks are attached to active plans.")
            print(
                "Run `uv run --no-sync python -B -m codex_supervisor.cli story-loop-status` "
                "to distinguish HITL, blocked, completed, and empty queue states."
            )
            print("Other ready tasks:")
            for task in all_ready_tasks:
                blocked = _task_claimability_reason(task, ready_all_tasks, worker_runs)
                print(
                    f"{task.task_id}\t{task.task_type}\t{blocked}\t"
                    f"plan={task.plan_id}({task.plan_status})\t{task.title}"
                )
            return 0
        print("No ready supervisor tasks found.")
        print(
            "Run `uv run --no-sync python -B -m codex_supervisor.cli story-loop-status` to confirm "
            "whether the queue is blocked, completed, or empty."
        )
        return 0

    if args.command == "task-claim":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        try:
            claim = write_store.claim_next_ready_afk_task(
                worker_run_id=args.worker_run_id,
                backend=args.backend,
                task_id=args.task_id,
                status=args.status,
                worktree_path=args.worktree_path,
                prompt_path=args.prompt_path,
                jsonl_path=args.jsonl_path,
                metadata=args.metadata_json,
            )
        except (KeyError, ValueError, sqlite3.Error) as exc:
            print(f"Could not claim current task: {exc}", file=sys.stderr)
            return 1
        if claim is None:
            if args.json:
                _print_json(None)
            else:
                print("No claimable ready AFK task found.")
                print(
                    "Run: uv run --no-sync python -B -m codex_supervisor.cli "
                    "story-loop-status --json"
                )
            return 0
        if args.json:
            _print_json(claim)
        else:
            print(f"Claimed task: {claim.task.task_id}")
            print(f"worker_run_id: {claim.worker_run.worker_run_id}")
            print(f"worker_status: {claim.worker_run.status}")
        return 0

    if args.command == "goal-contract-render":
        read_store = _open_read_store(args.path)
        if read_store is None:
            return 1
        contract_task = _select_goal_contract_task(read_store, task_id=args.task_id)
        if contract_task is None and _last_read_failed:
            return 1
        if contract_task is None:
            if args.json:
                _print_json(None)
            elif args.task_id is None:
                print("No current ready AFK task found.")
                print("Run: uv run --no-sync python -B -m codex_supervisor.cli story-loop-status")
            else:
                print(f"No supervisor task found: {args.task_id}")
            return 1
        all_tasks = _read_or_report(read_store.list_supervisor_tasks)
        if all_tasks is None:
            return 1
        contract = render_goal_contract(
            contract_task,
            unresolved_blockers=unresolved_task_blockers(contract_task, all_tasks),
        )
        if args.json:
            _print_json(contract)
        else:
            print(render_goal_contract_markdown(contract))
        return 0

    if args.command == "story-loop-status":
        read_store = _open_read_store(args.path)
        if read_store is None:
            return 1
        if args.plan_id is not None:
            matching_plans = _read_or_report(
                lambda: tuple(
                    plan for plan in read_store.list_plans() if plan.plan_id == args.plan_id
                )
            )
            if matching_plans is None:
                return 1
            if not matching_plans:
                print(f"No plan found: {args.plan_id}", file=sys.stderr)
                return 1
            selected_plan = matching_plans[0]
            if not args.all and selected_plan.status not in CURRENT_QUEUE_PLAN_STATUSES:
                print(
                    f"Plan {args.plan_id} is {selected_plan.status}; rerun with --all to inspect "
                    "historical plans.",
                    file=sys.stderr,
                )
                return 1
        status = _read_or_report(
            lambda: build_story_loop_status(
                read_store,
                active_only=not args.all,
                plan_id=args.plan_id,
            )
        )
        if status is None:
            return 1
        if args.json:
            _print_json(status)
        else:
            _print_story_loop_status(status)
        return 0

    if args.command == "story-loop-record":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        story_result = _write_story_loop_record_or_report(
            write_store,
            progress_id=args.progress_id,
            plan_id=args.plan_id,
            event_type=args.event_type,
            summary=args.summary,
            details=args.details,
            artifact_ids=tuple(args.artifact_id),
            artifact_relationship=args.artifact_relationship,
            task_id=args.task_id,
            worker_run_id=args.worker_run_id,
            linked_artifact_id=args.linked_artifact_id,
        )
        if story_result is None:
            return 1
        _print_mutation_result("story_loop_progress", args.progress_id, story_result, args.json)
        return 0

    if args.command == "story-loop-run-once":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        story_run_store = write_store
        repo_root = args.repo_root or Path.cwd()
        environment = {str(key): str(value) for key, value in args.environment_json.items()}
        run_result = _write_value_or_report(
            lambda: run_live_story_loop_once(
                story_run_store,
                repo_root=repo_root,
                worker_run_id=args.worker_run_id,
                result_schema_path=args.result_schema_path,
                sandbox_mode=args.sandbox_mode,
                approval_policy=args.approval_policy,
                codex_executable=args.codex_bin,
                codex_home=args.codex_home,
                codex_config_path=args.codex_config_path,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                service_tier=args.service_tier,
                native_goal_mode=args.native_goal_mode,
                ignore_user_config=args.ignore_user_config,
                environment=environment,
            )
        )
        if run_result is None:
            return 1
        if args.json:
            _print_json(run_result)
        else:
            print(
                f"story_loop_run: {run_result.status} "
                f"{run_result.task_id or 'none'} {run_result.worker_run_id}"
            )
            if run_result.failure_class:
                print(f"failure_class: {run_result.failure_class}")
            if run_result.result_id:
                print(f"result_id: {run_result.result_id}")
        return 0 if run_result.status == "completed" else 1

    if args.command == "decision-add":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        decision_store = write_store
        decision_record = PlanDecisionRecord(
            decision_id=args.decision_id,
            plan_id=args.plan_id,
            decision=args.decision,
            rationale=args.rationale,
            alternatives_considered=args.alternatives_considered,
            consequences=args.consequences,
        )
        if not _write_or_report(lambda: decision_store.add_plan_decision(decision_record)):
            return 1
        _print_mutation_result("decision", decision_record.decision_id, decision_record, args.json)
        return 0

    if args.command == "progress-add":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        progress_store = write_store
        progress_record = PlanProgressRecord(
            progress_id=args.progress_id,
            plan_id=args.plan_id,
            event_type=args.event_type,
            summary=args.summary,
            details=args.details,
            linked_artifact_id=args.linked_artifact_id,
        )
        if not _write_or_report(lambda: progress_store.add_plan_progress(progress_record)):
            return 1
        _print_mutation_result("progress", progress_record.progress_id, progress_record, args.json)
        return 0

    if args.command == "artifact-link-add":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        artifact_store = write_store
        artifact_record = PlanArtifactLinkRecord(
            plan_id=args.plan_id,
            artifact_id=args.artifact_id,
            relationship=args.relationship,
        )
        if not _write_or_report(lambda: artifact_store.add_plan_artifact_link(artifact_record)):
            return 1
        _print_mutation_result(
            "artifact_link",
            artifact_record.artifact_id,
            artifact_record,
            args.json,
        )
        return 0

    if args.command == "commit-link-add":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        commit_store = write_store
        commit_record = PlanCommitLinkRecord(
            plan_id=args.plan_id,
            commit_sha=args.commit_sha,
            relationship=args.relationship,
        )
        if not _write_or_report(lambda: commit_store.add_plan_commit_link(commit_record)):
            return 1
        _print_mutation_result("commit_link", commit_record.commit_sha, commit_record, args.json)
        return 0

    if args.command == "ci-run-record":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        ci_run_store = write_store
        ci_run_record = CiRunEvidenceRecord(
            progress_id=args.progress_id,
            plan_id=args.plan_id,
            provider=args.provider,
            run_id=args.run_id,
            run_url=args.run_url,
            head_sha=args.head_sha,
            status=args.status,
            conclusion=args.conclusion,
            workflow=args.workflow,
            job_id=args.job_id,
            job_name=args.job_name,
            event=args.event,
            summary=args.summary,
            artifact_id=args.artifact_id,
            artifact_relationship=args.artifact_relationship,
            commit_relationship=args.commit_relationship,
        )
        ci_recorded = _write_value_or_report(
            lambda: ci_run_store.record_ci_run_evidence(ci_run_record)
        )
        if ci_recorded is None:
            return 1
        if args.json:
            _print_json(ci_recorded)
        else:
            print(f"Recorded ci_run: {args.provider}/{args.run_id}")
        return 0

    if args.command == "pr-evidence-record":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        pr_store = write_store
        pr_record = PullRequestEvidenceRecord(
            progress_id=args.progress_id,
            plan_id=args.plan_id,
            provider=args.provider,
            repository=args.repository,
            pr_number=args.pr_number,
            pr_url=args.pr_url,
            state=args.state,
            title=args.title,
            summary=args.summary,
            head_ref=args.head_ref,
            base_ref=args.base_ref,
            head_sha=args.head_sha,
            base_sha=args.base_sha,
            draft=args.draft,
            merged=args.merged,
            issue_number=args.issue_number,
            artifact_id=args.artifact_id,
            artifact_relationship=args.artifact_relationship,
            commit_relationship=args.commit_relationship,
        )
        pr_recorded = _write_value_or_report(
            lambda: pr_store.record_pull_request_evidence(pr_record)
        )
        if pr_recorded is None:
            return 1
        if args.json:
            _print_json(pr_recorded)
        else:
            print(f"Recorded pr: {args.repository}#{args.pr_number}")
        return 0

    if args.command == "issue-comment-record":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        issue_comment_store = write_store
        issue_comment_record = IssueCommentEvidenceRecord(
            progress_id=args.progress_id,
            plan_id=args.plan_id,
            provider=args.provider,
            repository=args.repository,
            issue_number=args.issue_number,
            comment_id=args.comment_id,
            comment_url=args.comment_url,
            summary=args.summary,
            details=args.details,
            pr_number=args.pr_number,
            author=args.author,
            commit_sha=args.commit_sha,
            artifact_id=args.artifact_id,
            artifact_relationship=args.artifact_relationship,
            commit_relationship=args.commit_relationship,
        )
        issue_comment_recorded = _write_value_or_report(
            lambda: issue_comment_store.record_issue_comment_evidence(issue_comment_record)
        )
        if issue_comment_recorded is None:
            return 1
        if args.json:
            _print_json(issue_comment_recorded)
        else:
            print(f"Recorded issue_comment: {args.repository}#{args.issue_number}")
        return 0

    if args.command == "commit-link-delete":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        commit_store = write_store
        commit_record = PlanCommitLinkRecord(
            plan_id=args.plan_id,
            commit_sha=args.commit_sha,
            relationship=args.relationship,
        )
        deleted = _write_value_or_report(
            lambda: commit_store.delete_plan_commit_link(commit_record)
        )
        if deleted is None:
            return 1
        if args.json:
            _print_json({"deleted": deleted, "commit_link": commit_record})
        else:
            action = "Deleted" if deleted else "No matching"
            print(f"{action} commit_link: {commit_record.commit_sha}")
        return 0

    if args.command == "task-upsert":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        task_store = write_store
        task_record = _write_value_or_report(
            lambda: _build_task_upsert_record(
                task_store,
                task_id=args.task_id,
                plan_id=args.plan_id,
                title=args.title,
                goal=args.goal,
                task_type=args.task_type,
                status=args.status,
                scope=args.scope_json,
                out_of_scope=args.out_of_scope_json,
                acceptance_criteria=args.acceptance_criterion,
                verification_commands=args.verification_command,
                allowed_paths=args.allowed_path,
                blocked_by=args.blocked_by,
                worker_backend=args.worker_backend,
                review_required=args.review_required,
                replace=args.replace,
            )
        )
        if task_record is None:
            return 1
        if not _write_or_report(
            lambda: task_store.upsert_supervisor_task(
                task_record,
                validate_current_queue_contract=True,
            )
        ):
            return 1
        _print_mutation_result("task", task_record.task_id, task_record, args.json)
        return 0

    if args.command == "worker-run-upsert":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        worker_store = write_store
        worker_record = _write_value_or_report(
            lambda: _build_worker_run_upsert_record(
                worker_store,
                worker_run_id=args.worker_run_id,
                task_id=args.task_id,
                backend=args.backend,
                status=args.status,
                worktree_path=args.worktree_path,
                prompt_path=args.prompt_path,
                jsonl_path=args.jsonl_path,
                result_path=args.result_path,
                result_id=args.result_id,
                started_at=args.started_at,
                completed_at=args.completed_at,
                failure_class=args.failure_class,
                metadata=args.metadata_json,
                replace=args.replace,
            )
        )
        if worker_record is None:
            return 1
        if worker_record.status == "completed":
            if worker_record.result_path is None:
                if not _write_or_report(lambda: worker_store.upsert_worker_run(worker_record)):
                    return 1
                _print_mutation_result(
                    "worker_run",
                    worker_record.worker_run_id,
                    worker_record,
                    args.json,
                )
                return 0
            ingested_result = _write_value_or_report(
                lambda: worker_store.ingest_worker_result_for_record(worker_record)
            )
            if ingested_result is None:
                return 1
            updated_worker_record = _read_or_report(
                lambda: _find_worker_run(worker_store, worker_record.worker_run_id)
            )
            if updated_worker_record is None:
                return 1
            _print_mutation_result(
                "worker_run",
                updated_worker_record.worker_run_id,
                updated_worker_record,
                args.json,
            )
            return 0
        if not _write_or_report(lambda: worker_store.upsert_worker_run(worker_record)):
            return 1
        _print_mutation_result("worker_run", worker_record.worker_run_id, worker_record, args.json)
        return 0

    if args.command == "review-result-ingest":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        try:
            review_result = _load_review_result(args.review_result_path)
            review_result_artifact_id = _review_result_artifact_id(
                args.review_result_path,
                args.review_result_artifact_id,
            )
            repair_result: ReviewRepairRoutingResult | None = None
            repair_plan: ReviewRepairRoutingResult | None = None
            if args.create_repair_tasks:
                repair_verification_commands = (
                    tuple(args.repair_verification_command)
                    if args.repair_verification_command is not None
                    else DEFAULT_REPAIR_VERIFICATION_COMMANDS
                )
                repair_plan = plan_repair_tasks_from_review_result(
                    write_store,
                    plan_id=args.plan_id,
                    review_result=review_result,
                    source_task_id=args.source_task_id,
                    task_id_prefix=args.repair_task_id_prefix,
                    verification_commands=repair_verification_commands,
                )
            persistence_record = record_review_result(
                write_store,
                plan_id=args.plan_id,
                progress_id=args.progress_id,
                review_result=review_result,
                review_result_artifact_id=review_result_artifact_id,
                review_artifact_ids=tuple(args.review_artifact_id),
            )
            if repair_plan is not None:
                repair_result = apply_repair_task_plan(write_store, repair_plan)
        except (
            OSError,
            json.JSONDecodeError,
            ReviewContractError,
            ValueError,
            sqlite3.Error,
        ) as exc:
            print(f"Could not ingest review result: {exc}", file=sys.stderr)
            return 1
        output = _review_result_ingestion_output(
            review_result=review_result,
            persistence_record=persistence_record,
            repair_result=repair_result,
            repair_requested=args.create_repair_tasks,
        )
        if args.json:
            _print_json(output)
        else:
            _print_review_result_ingestion(output)
        return 0

    if args.command == "review-run-live":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        repair_verification_commands = (
            tuple(args.repair_verification_command)
            if args.repair_verification_command is not None
            else DEFAULT_REPAIR_VERIFICATION_COMMANDS
        )
        try:
            live_review_result = run_live_review_for_task(
                write_store,
                task_id=args.task_id,
                review_id=args.review_id,
                repo_root=args.repo_root,
                review_result_artifact_id=args.review_result_artifact_id,
                mode=args.mode,
                target=args.target,
                progress_id=args.progress_id,
                review_artifact_ids=tuple(args.review_artifact_id),
                create_repair_tasks=args.create_repair_tasks,
                repair_task_id_prefix=args.repair_task_id_prefix,
                repair_verification_commands=repair_verification_commands,
                codex_executable=args.codex_executable,
                codex_home=args.codex_home,
                model=args.model,
                sandbox_mode=args.sandbox_mode,
                approval_policy=args.approval_policy,
            )
        except (
            OSError,
            json.JSONDecodeError,
            ReviewContractError,
            ValueError,
            sqlite3.Error,
        ) as exc:
            print(f"Could not run live review: {exc}", file=sys.stderr)
            return 1
        if args.json:
            _print_json(live_review_result)
        else:
            _print_live_review_run_result(live_review_result)
        return 0 if live_review_result.status in {"completed", "needs_hitl"} else 1

    if args.command == "insight-validate":
        try:
            insight_record = _load_insight_record(args.insight_path)
        except (OSError, json.JSONDecodeError, InsightContractError) as exc:
            print(f"Could not validate insight: {exc}", file=sys.stderr)
            return 1
        if args.json:
            _print_json(insight_record)
        else:
            _print_insight_record(insight_record)
        return 0

    if args.command == "insight-update":
        try:
            insight_record = _load_insight_record(args.insight_path)
            insight_update: AppliedInsightUpdate | InsightMarkdownUpdate
            if args.target_path is None:
                insight_update = render_insight_markdown_update(
                    insight_record,
                    promotion_criteria=tuple(args.promotion_criterion),
                    provenance=tuple(args.provenance),
                )
            else:
                insight_update = apply_insight_update(
                    args.target_path,
                    insight_record,
                    promotion_criteria=tuple(args.promotion_criterion),
                    provenance=tuple(args.provenance),
                )
        except (OSError, json.JSONDecodeError, InsightContractError, InsightUpdateError) as exc:
            print(f"Could not update insight: {exc}", file=sys.stderr)
            return 1
        if args.json:
            _print_json(insight_update)
        elif isinstance(insight_update, AppliedInsightUpdate):
            _print_applied_insight_update(insight_update)
        else:
            print(insight_update.markdown, end="")
        return 0

    if args.command == "skill-promotion-validate":
        try:
            skill_proposal = _load_skill_promotion_proposal(args.proposal_path)
        except (OSError, json.JSONDecodeError, SkillPromotionContractError) as exc:
            print(f"Could not validate skill promotion proposal: {exc}", file=sys.stderr)
            return 1
        if args.json:
            _print_json(skill_proposal)
        else:
            _print_skill_promotion_proposal(skill_proposal)
        return 0

    if args.command == "plan-upsert":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        plan_store = write_store
        plan_record = PlanRecord(
            plan_id=args.plan_id,
            slug=args.slug,
            title=args.title,
            goal=args.goal,
            status=args.status,
            priority=args.priority,
            owner_agent=args.owner_agent,
            non_goals=args.non_goals_json,
            context=args.context_json,
            superseded_by_plan_id=args.superseded_by_plan_id,
        )
        if not _write_or_report(lambda: plan_store.upsert_plan(plan_record)):
            return 1
        _print_mutation_result("plan", plan_record.plan_id, plan_record, args.json)
        return 0

    if args.command == "milestone-upsert":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        milestone_store = write_store
        milestone_record = PlanMilestoneRecord(
            milestone_id=args.milestone_id,
            plan_id=args.plan_id,
            title=args.title,
            status=args.status,
            sort_order=args.sort_order,
            details=args.details_json,
        )
        if not _write_or_report(lambda: milestone_store.upsert_plan_milestone(milestone_record)):
            return 1
        _print_mutation_result(
            "milestone",
            milestone_record.milestone_id,
            milestone_record,
            args.json,
        )
        return 0

    if args.command == "criterion-upsert":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        criterion_store = write_store
        criterion_record = PlanAcceptanceCriterionRecord(
            criterion_id=args.criterion_id,
            plan_id=args.plan_id,
            description=args.description,
            status=args.status,
            verification_command=args.verification_command,
        )
        if not _write_or_report(
            lambda: criterion_store.upsert_plan_acceptance_criterion(criterion_record)
        ):
            return 1
        _print_mutation_result(
            "criterion",
            criterion_record.criterion_id,
            criterion_record,
            args.json,
        )
        return 0

    if args.command == "plan-status":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        plan_store = write_store
        if not _write_or_report(
            lambda: plan_store.update_plan_status(
                args.plan_id,
                args.status,
                superseded_by_plan_id=args.superseded_by_plan_id,
            )
        ):
            return 1
        print(f"Updated plan {args.plan_id} -> {args.status}")
        return 0

    if args.command == "milestone-status":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        milestone_store = write_store
        if not _write_or_report(
            lambda: milestone_store.update_plan_milestone_status(args.milestone_id, args.status)
        ):
            return 1
        print(f"Updated milestone {args.milestone_id} -> {args.status}")
        return 0

    if args.command == "criterion-status":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        criterion_store = write_store
        if not _write_or_report(
            lambda: criterion_store.update_plan_acceptance_criterion_status(
                args.criterion_id,
                args.status,
            )
        ):
            return 1
        print(f"Updated criterion {args.criterion_id} -> {args.status}")
        return 0

    if args.command == "task-status":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        task_store = write_store
        if not _write_or_report(
            lambda: task_store.update_supervisor_task_status(args.task_id, args.status)
        ):
            return 1
        print(f"Updated task {args.task_id} -> {args.status}")
        return 0

    if args.command == "worker-run-status":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        worker_store = write_store
        if args.status == "completed":
            if args.result_path is None and args.result_id is None:
                print(
                    "worker-run-status completed requires --result-path or --result-id",
                    file=sys.stderr,
                )
                return 1
            if args.result_path is not None:
                ingested_worker_result = _write_value_or_report(
                    lambda: worker_store.ingest_worker_result(
                        args.worker_run_id,
                        args.result_path,
                    )
                )
                if ingested_worker_result is None:
                    return 1
                print(f"Updated worker_run {args.worker_run_id} -> {ingested_worker_result.status}")
                return 0
        if not _write_or_report(
            lambda: worker_store.update_worker_run_status(
                args.worker_run_id,
                args.status,
                failure_class=args.failure_class,
                completed_at=args.completed_at,
                result_path=args.result_path,
                result_id=args.result_id,
            )
        ):
            return 1
        print(f"Updated worker_run {args.worker_run_id} -> {args.status}")
        return 0

    return 1


_last_read_failed = False


def _planning_path_or_report(path: Path | None) -> Path | None:
    if path is not None:
        return path
    try:
        return default_planning_database_path()
    except RuntimeError as exc:
        print(f"Could not locate planning database: {exc}", file=sys.stderr)
        print(
            "Run from a codex-supervisor/supervised project root or pass "
            "--path <repo>/plans/planning.sqlite3.",
            file=sys.stderr,
        )
        return None


def _open_read_store(path: Path | None) -> PlanningSQLiteStore | None:
    resolved_path = _planning_path_or_report(path)
    if resolved_path is None:
        return None
    path = resolved_path
    if not path.exists():
        print(
            f"Planning database is not initialized: {path}",
            file=sys.stderr,
        )
        print(
            "Run: uv run --no-sync python -B -m codex_supervisor.cli "
            "plan-init --seed-bootstrap-plan",
            file=sys.stderr,
        )
        return None
    try:
        return open_existing_planning_database(path, validate=True)
    except (ValueError, sqlite3.Error) as exc:
        print(f"Planning database schema is not valid: {exc}", file=sys.stderr)
        print(
            "Run: uv run --no-sync python -B scripts/check_planning_integrity.py",
            file=sys.stderr,
        )
        return None


def _open_write_store(path: Path | None) -> PlanningSQLiteStore | None:
    resolved_path = _planning_path_or_report(path)
    if resolved_path is None:
        return None
    path = resolved_path
    if not path.exists():
        print(
            f"Planning database is not initialized: {path}",
            file=sys.stderr,
        )
        print(
            "Run: uv run --no-sync python -B -m codex_supervisor.cli "
            "plan-init --seed-bootstrap-plan",
            file=sys.stderr,
        )
        return None
    try:
        return open_existing_planning_database(path, read_only=False, validate=True)
    except (ValueError, sqlite3.Error) as exc:
        print(f"Planning database schema is not valid: {exc}", file=sys.stderr)
        print(
            "Run: uv run --no-sync python -B scripts/check_planning_integrity.py",
            file=sys.stderr,
        )
        return None


def _read_or_report[T](operation: Callable[[], T]) -> T | None:
    global _last_read_failed
    _last_read_failed = False
    try:
        return operation()
    except (KeyError, ValueError, sqlite3.Error) as exc:
        _last_read_failed = True
        print(f"Could not read planning database: {exc}", file=sys.stderr)
        print(
            "Run: uv run --no-sync python -B scripts/check_planning_integrity.py",
            file=sys.stderr,
        )
        return None


def _write_or_report(operation: Callable[[], None]) -> bool:
    try:
        operation()
    except (KeyError, ValueError, sqlite3.Error) as exc:
        print(f"Could not update planning database: {exc}", file=sys.stderr)
        return False
    return True


def _write_value_or_report[T](operation: Callable[[], T]) -> T | None:
    try:
        return operation()
    except (KeyError, ValueError, sqlite3.Error) as exc:
        print(f"Could not update planning database: {exc}", file=sys.stderr)
        return None


def _write_story_loop_record_or_report(
    store: PlanningSQLiteStore,
    *,
    progress_id: str,
    plan_id: str,
    event_type: str,
    summary: str,
    details: str | None,
    artifact_ids: tuple[str, ...],
    artifact_relationship: str,
    task_id: str | None,
    worker_run_id: str | None,
    linked_artifact_id: str | None,
) -> object | None:
    try:
        return record_story_loop_progress(
            store,
            progress_id=progress_id,
            plan_id=plan_id,
            event_type=event_type,
            summary=summary,
            details=details,
            artifact_ids=artifact_ids,
            artifact_relationship=artifact_relationship,
            task_id=task_id,
            worker_run_id=worker_run_id,
            linked_artifact_id=linked_artifact_id,
        )
    except (KeyError, ValueError, sqlite3.Error) as exc:
        print(f"Could not update planning database: {exc}", file=sys.stderr)
        return None


def _load_review_result(path: Path) -> ReviewResult:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_review_result_payload(payload)


def _load_insight_record(path: Path) -> InsightRecord:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_insight_record_payload(payload)


def _load_skill_promotion_proposal(path: Path) -> SkillPromotionProposal:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_skill_promotion_payload(payload)


def _review_result_artifact_id(path: Path, explicit_artifact_id: str | None) -> str:
    if explicit_artifact_id is not None:
        return explicit_artifact_id
    if not path.is_absolute():
        return path.as_posix()
    resolved_path = path.resolve()
    try:
        return resolved_path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError as exc:
        msg = (
            "--review-result-artifact-id is required when --review-result-path is outside "
            "the current repository"
        )
        raise ValueError(msg) from exc


def _review_result_ingestion_output(
    *,
    review_result: ReviewResult,
    persistence_record: ReviewResultPersistenceRecord,
    repair_result: ReviewRepairRoutingResult | None,
    repair_requested: bool,
) -> dict[str, object]:
    repair_tasks: dict[str, object] = {
        "requested": repair_requested,
        "created_tasks": (),
        "created_task_ids": (),
        "existing_task_ids": (),
        "skipped_findings": (),
    }
    if repair_result is not None:
        repair_tasks = {
            "requested": repair_requested,
            "created_tasks": repair_result.created_tasks,
            "created_task_ids": tuple(task.task_id for task in repair_result.created_tasks),
            "existing_task_ids": repair_result.existing_task_ids,
            "skipped_findings": repair_result.skipped_findings,
        }
    return {
        "review_result": {
            "review_id": review_result.review_id,
            "mode": review_result.mode,
            "target": review_result.target,
            "finding_counts": {
                "total": len(review_result.findings),
                "accepted": len(review_result.accepted_findings),
                "waived": len(review_result.waived_findings),
                "needs_hitl": len(
                    tuple(
                        finding
                        for finding in review_result.findings
                        if finding.status == "needs_hitl"
                    )
                ),
            },
        },
        "progress": persistence_record.progress,
        "artifact_links": persistence_record.artifact_links,
        "repair_tasks": repair_tasks,
    }


def _select_goal_contract_task(
    store: PlanningSQLiteStore,
    *,
    task_id: str | None,
) -> SupervisorTaskSummaryRecord | None:
    if task_id is None:
        return _read_or_report(store.next_ready_afk_task)
    tasks = _read_or_report(
        lambda: tuple(task for task in store.list_supervisor_tasks() if task.task_id == task_id)
    )
    if tasks is None:
        return None
    if not tasks:
        return None
    return tasks[0]


def _build_task_upsert_record(
    store: PlanningSQLiteStore,
    *,
    task_id: str,
    plan_id: str,
    title: str,
    goal: str,
    task_type: str,
    status: str,
    scope: dict[str, Any] | None,
    out_of_scope: dict[str, Any] | None,
    acceptance_criteria: list[str] | None,
    verification_commands: list[str] | None,
    allowed_paths: list[str] | None,
    blocked_by: list[str] | None,
    worker_backend: str | None,
    review_required: bool | None,
    replace: bool,
) -> SupervisorTaskRecord:
    existing = None if replace else _find_task(store, task_id)
    return SupervisorTaskRecord(
        task_id=task_id,
        plan_id=plan_id,
        title=title,
        goal=goal,
        task_type=task_type,
        status=status,
        scope=_preserve_or_default(scope, existing.scope if existing else {}, {}),
        out_of_scope=_preserve_or_default(
            out_of_scope,
            existing.out_of_scope if existing else {},
            {},
        ),
        acceptance_criteria=_preserve_or_default(
            acceptance_criteria,
            existing.acceptance_criteria if existing else [],
            [],
        ),
        verification_commands=_preserve_or_default(
            verification_commands,
            existing.verification_commands if existing else [],
            [],
        ),
        allowed_paths=_preserve_or_default(
            allowed_paths,
            existing.allowed_paths if existing else [],
            [],
        ),
        blocked_by=_preserve_or_default(blocked_by, existing.blocked_by if existing else [], []),
        worker_backend=_preserve_or_default(
            worker_backend,
            existing.worker_backend if existing else "codex_exec",
            "codex_exec",
        ),
        review_required=_preserve_or_default(
            review_required,
            existing.review_required if existing else True,
            True,
        ),
    )


def _build_worker_run_upsert_record(
    store: PlanningSQLiteStore,
    *,
    worker_run_id: str,
    task_id: str,
    backend: str,
    status: str,
    worktree_path: str | None,
    prompt_path: str | None,
    jsonl_path: str | None,
    result_path: str | None,
    result_id: str | None,
    started_at: str | None,
    completed_at: str | None,
    failure_class: str | None,
    metadata: dict[str, Any] | None,
    replace: bool,
) -> WorkerRunRecord:
    existing = None if replace else _find_worker_run(store, worker_run_id)
    return WorkerRunRecord(
        worker_run_id=worker_run_id,
        task_id=task_id,
        backend=backend,
        status=status,
        worktree_path=_preserve_or_default(
            worktree_path,
            existing.worktree_path if existing else None,
            None,
        ),
        prompt_path=_preserve_or_default(
            prompt_path,
            existing.prompt_path if existing else None,
            None,
        ),
        jsonl_path=_preserve_or_default(
            jsonl_path, existing.jsonl_path if existing else None, None
        ),
        result_path=_preserve_or_default(
            result_path,
            existing.result_path if existing else None,
            None,
        ),
        result_id=_preserve_or_default(
            result_id,
            existing.result_id if existing else None,
            None,
        ),
        started_at=_preserve_or_default(
            started_at, existing.started_at if existing else None, None
        ),
        completed_at=_preserve_or_default(
            completed_at,
            existing.completed_at if existing else None,
            None,
        ),
        failure_class=_preserve_or_default(
            failure_class,
            existing.failure_class if existing else None,
            None,
        ),
        metadata=_preserve_or_default(metadata, existing.metadata if existing else {}, {}),
    )


def _find_task(
    store: PlanningSQLiteStore,
    task_id: str,
) -> SupervisorTaskSummaryRecord | None:
    tasks = store.list_supervisor_tasks()
    return next((task for task in tasks if task.task_id == task_id), None)


def _find_worker_run(
    store: PlanningSQLiteStore,
    worker_run_id: str,
) -> WorkerRunRecord | None:
    runs = store.list_worker_runs()
    return next((run for run in runs if run.worker_run_id == worker_run_id), None)


def _preserve_or_default[T](new_value: T | None, existing_value: T, default_value: T) -> T:
    if new_value is not None:
        return new_value
    if existing_value is not None:
        return existing_value
    return default_value


def _json_object_arg(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        msg = f"Expected JSON object: {exc.msg}"
        raise argparse.ArgumentTypeError(msg) from exc
    if not isinstance(parsed, dict):
        msg = "Expected JSON object"
        raise argparse.ArgumentTypeError(msg)
    return cast(dict[str, Any], parsed)


def _print_mutation_result(label: str, identifier: str, record: object, as_json: bool) -> None:
    if as_json:
        _print_json(record)
        return
    print(f"Recorded {label}: {identifier}")


def _print_task_detail(task: SupervisorTaskSummaryRecord) -> None:
    print(f"task_id: {task.task_id}")
    print(f"title: {task.title}")
    print(f"status: {task.status}")
    print(f"type: {task.task_type}")
    print(f"plan: {task.plan_id} ({task.plan_status}, priority={task.plan_priority})")
    print(f"plan_title: {task.plan_title}")
    print(f"goal: {task.goal}")
    print(f"worker_backend: {task.worker_backend}")
    print(f"review_required: {task.review_required}")
    _print_json_section("scope", task.scope)
    _print_json_section("out_of_scope", task.out_of_scope)
    _print_json_list("acceptance_criteria", task.acceptance_criteria)
    _print_json_list("blocked_by", task.blocked_by)
    _print_json_list("allowed_paths", task.allowed_paths)
    _print_json_list("verification", task.verification_commands)


def _print_story_loop_status(status: object) -> None:
    status_json = _to_jsonable(status)
    if not isinstance(status_json, dict):
        _print_json(status)
        return
    queue_state = status_json.get("queue_state")
    if queue_state:
        print(f"queue_state: {queue_state}")
    current_task_id = status_json.get("current_task_id")
    if current_task_id:
        print(f"current_task_id: {current_task_id}")
    current_running_task_id = status_json.get("current_running_task_id")
    if current_running_task_id:
        print(f"current_running_task_id: {current_running_task_id}")
    current_hitl_task_id = status_json.get("current_hitl_task_id")
    if current_hitl_task_id:
        print(f"current_hitl_task_id: {current_hitl_task_id}")
    current_afk_task = status_json.get("current_afk_task")
    if isinstance(current_afk_task, dict):
        print(f"current_afk_task: {current_afk_task['task_id']}")
    else:
        print("current_afk_task: none")
    current_task = status_json.get("current_task")
    if isinstance(current_task, dict):
        print(f"current_task: {current_task['task_id']}")
    else:
        print("current_task: none")
    print("plans:")
    plans = status_json.get("plans", [])
    if not plans:
        print("- none")
        return
    if not isinstance(plans, list):
        _print_json(status)
        return
    for plan in plans:
        if not isinstance(plan, dict):
            continue
        print(f"- {plan['plan_id']}\t{plan['state']}\tpriority={plan['priority']}\t{plan['title']}")
        print(f"  summary: {plan['summary']}")
        if plan.get("current_task_id"):
            print(f"  current_task_id: {plan['current_task_id']}")
        if plan.get("running_task_ids"):
            print(f"  running_task_ids: {', '.join(plan['running_task_ids'])}")
        if plan.get("blocked_task_ids"):
            print(f"  blocked_task_ids: {', '.join(plan['blocked_task_ids'])}")
        if plan.get("hitl_task_ids"):
            print(f"  hitl_task_ids: {', '.join(plan['hitl_task_ids'])}")
        if plan.get("pending_criterion_ids"):
            print(f"  pending_criterion_ids: {', '.join(plan['pending_criterion_ids'])}")


def _print_json_list(label: str, values: Sequence[object]) -> None:
    print(f"{label}:")
    if not values:
        print("- none")
        return
    for value in values:
        print(f"- {value}")


def _print_json_section(label: str, value: object) -> None:
    print(f"{label}:")
    print(json.dumps(_to_jsonable(value), indent=2, sort_keys=True))


def _print_project_registry_entries(entries: Sequence[ProjectRegistryEntry]) -> None:
    if not entries:
        print("No projects found.")
        return
    for entry in entries:
        print(
            f"{entry.project_id}\t{entry.status}\t{entry.adapter_type}\t"
            f"trust={entry.trust_policy}\troot={entry.root_path}"
        )
        if entry.facts is not None:
            source_documents = ", ".join(entry.facts.source_documents) or "none"
            verification = ", ".join(entry.facts.verification_commands) or "none"
            print(f"  source_documents: {source_documents}")
            print(f"  verification_commands: {verification}")
            print(f"  candidate_tasks: {len(entry.facts.candidate_tasks)}")
            for finding in entry.facts.adapter_findings:
                print(f"  adapter_finding: {finding}")
        if entry.failure_reason:
            print(f"  failure: {entry.failure_reason}")


def _supervisor_task_record_from_project_task_seed(seed: ProjectTaskSeed) -> SupervisorTaskRecord:
    return SupervisorTaskRecord(
        task_id=seed.task_id,
        plan_id=seed.plan_id,
        title=seed.title,
        goal=seed.goal,
        task_type=seed.task_type,
        status=seed.status,
        scope=dict(seed.scope),
        out_of_scope=dict(seed.out_of_scope),
        acceptance_criteria=list(seed.acceptance_criteria),
        verification_commands=list(seed.verification_commands),
        allowed_paths=list(seed.allowed_paths),
        blocked_by=list(seed.blocked_by),
        worker_backend=seed.worker_backend,
        review_required=seed.review_required,
    )


def _upsert_seeded_task(store: PlanningSQLiteStore, record: SupervisorTaskRecord) -> None:
    store.upsert_supervisor_task(record, validate_current_queue_contract=True)


def _print_project_task_seed_result(
    entry: ProjectRegistryEntry,
    task_seeds: Sequence[ProjectTaskSeed],
    *,
    applied: bool,
) -> None:
    action = "Applied" if applied else "Dry-run"
    print(f"{action} project task seeds for {entry.project_id}:")
    for seed in task_seeds:
        print(f"- {seed.task_id}\t{seed.status}\t{seed.task_type}\t{seed.title}")


def _print_spawned_project_recommendation(
    recommendation: SpawnedProjectRecommendation,
) -> None:
    print(f"project: {recommendation.project_name}")
    print(f"tiers: {', '.join(recommendation.tiers)}")
    _print_json_list("required_files", recommendation.required_files)
    _print_json_list("verification_commands", recommendation.verification_commands)
    print(f"planning_guidance: {recommendation.planning_guidance}")
    print(f"first_task_guidance: {recommendation.first_task_guidance}")
    print(f"classification_reason: {recommendation.classification_reason}")
    _print_json_list("warnings", recommendation.warnings)


def _print_spawned_project_proposal(proposal: SpawnedProjectScaffoldProposal) -> None:
    print(f"project: {proposal.project_name}")
    print(f"writes_files: {proposal.writes_files}")
    print(f"tiers: {', '.join(proposal.recommendation.tiers)}")
    print("file_actions:")
    for action in proposal.file_actions:
        print(f"- {action.path}\t{action.action}\t{action.tier}\t{action.purpose}")
    _print_json_list("planning_actions", proposal.planning_actions)
    _print_json_list("source_lock_actions", proposal.source_lock_actions)
    _print_json_list("insight_actions", proposal.insight_actions)
    _print_json_list("skill_actions", proposal.skill_actions)
    _print_json_list("source_study_actions", proposal.source_study_actions)
    print(f"first_task: {proposal.first_task.title}")


def _print_spawned_project_apply_result(result: SpawnedProjectScaffoldApplyResult) -> None:
    print(f"project: {result.project_name}")
    print(f"root: {result.project_root}")
    print(f"writes_files: {result.writes_files}")
    _print_json_list("created_files", result.created_files)
    _print_json_list("existing_files", result.existing_files)
    if result.planning_db_path:
        print(f"planning_db: {result.planning_db_path}")
    _print_json_list("verification_commands", result.verification_commands)


def _print_release_readiness_report(report: ReleaseReadinessReport) -> None:
    print(f"repo_root: {report.repo_root}")
    print(f"target_commit: {report.target_commit}")
    print(f"release_ready: {report.ready}")
    print(f"passing_checks: {report.passing_checks}")
    print(f"gap_checks: {report.gap_checks}")
    print("checks:")
    for check in report.checks:
        print(f"- {check.section}\t{check.status}\t{check.name}")
        for evidence in check.evidence:
            print(f"  evidence: {evidence}")
        if check.next_action:
            print(f"  next_action: {check.next_action}")


def _print_factory_loop_demo_report(report: FactoryLoopDemoReport) -> None:
    print(f"success: {report.success}")
    print(f"project_name: {report.project_name}")
    print(f"release_evidence: {report.release_evidence}")
    print(f"cleanup_performed: {report.cleanup_performed}")
    print(f"workspace_retained: {report.workspace_retained}")
    print(f"completed_stages: {report.completed_stages}")
    print("stages:")
    for stage in report.stages:
        print(f"- {stage.name}\t{stage.status}")
        for evidence in stage.evidence:
            print(f"  evidence: {evidence}")


def _add_spawned_project_brief_arguments(command_parser: argparse.ArgumentParser) -> None:
    command_parser.add_argument("--name", required=True)
    command_parser.add_argument(
        "--complexity",
        choices=sorted(PROJECT_COMPLEXITIES),
        default="standard",
    )
    command_parser.add_argument(
        "--trust-policy",
        choices=sorted(TRUST_POLICIES),
        default="local_trusted",
    )
    command_parser.add_argument("--production-intended", action="store_true", default=False)
    command_parser.add_argument("--public-or-shared", action="store_true", default=False)
    command_parser.add_argument("--unattended-workers", action="store_true", default=False)
    command_parser.add_argument("--durable-queue", action="store_true", default=False)
    command_parser.add_argument("--protected-docs", action="store_true", default=False)
    command_parser.add_argument("--durable-learning", action="store_true", default=False)
    command_parser.add_argument("--repo-local-skills", action="store_true", default=False)
    command_parser.add_argument("--source-study", action="store_true", default=False)
    command_parser.add_argument("--json", action="store_true", default=False)


def _spawned_project_brief_from_args(args: argparse.Namespace) -> SpawnedProjectBrief:
    return SpawnedProjectBrief(
        name=args.name,
        complexity=args.complexity,
        production_intended=args.production_intended,
        public_or_shared=args.public_or_shared,
        unattended_workers=args.unattended_workers,
        durable_queue=args.durable_queue,
        protected_docs=args.protected_docs,
        durable_learning=args.durable_learning,
        repo_local_skills=args.repo_local_skills,
        source_study=args.source_study,
        trust_policy=args.trust_policy,
    )


def _print_json(value: object) -> None:
    print(json.dumps(_to_jsonable(value), indent=2, sort_keys=True, default=str))


def _print_cleanup_plan(plan: CleanupPlan) -> None:
    print(f"workspace_root: {plan.workspace_root}")
    print("selected:")
    if not plan.selected_entries:
        print("- none")
    for entry in plan.selected_entries:
        print(
            f"- {entry.repo_relative_path}\t{entry.runtime_kind}\t"
            f"worker_run_id={entry.worker_run_id}\treason={entry.reason}\t"
            f"operation={entry.operation}"
        )
    print("skipped:")
    if not plan.skipped_entries:
        print("- none")
    for entry in plan.skipped_entries:
        print(
            f"- {entry.repo_relative_path}\t{entry.runtime_kind or 'unsupported'}\t"
            f"worker_run_id={entry.worker_run_id or 'none'}\t"
            f"skip_reason={entry.skip_reason}"
        )


def _print_review_result_ingestion(output: dict[str, object]) -> None:
    review_result = cast(dict[str, object], output["review_result"])
    progress = cast(PlanProgressRecord, output["progress"])
    artifact_links = cast(tuple[PlanArtifactLinkRecord, ...], output["artifact_links"])
    repair_tasks = cast(dict[str, object], output["repair_tasks"])
    print(
        f"review_result: {review_result['review_id']} "
        f"({review_result['mode']} for {review_result['target']})"
    )
    print(f"progress: {progress.progress_id}")
    print("artifact_links:")
    for link in artifact_links:
        print(f"- {link.artifact_id}\t{link.relationship}")
    print("repair_tasks:")
    print(f"requested: {repair_tasks['requested']}")
    created_task_ids = cast(tuple[str, ...], repair_tasks["created_task_ids"])
    existing_task_ids = cast(tuple[str, ...], repair_tasks["existing_task_ids"])
    skipped_findings = cast(tuple[object, ...], repair_tasks["skipped_findings"])
    print("created:")
    if created_task_ids:
        for task_id in created_task_ids:
            print(f"- {task_id}")
    else:
        print("- none")
    print("existing:")
    if existing_task_ids:
        for task_id in existing_task_ids:
            print(f"- {task_id}")
    else:
        print("- none")
    print("skipped:")
    if skipped_findings:
        for skipped in skipped_findings:
            skipped_json = _to_jsonable(skipped)
            if isinstance(skipped_json, dict):
                print(
                    f"- {skipped_json['finding_id']}\t{skipped_json['status']}\t"
                    f"{skipped_json['reason']}"
                )
    else:
        print("- none")


def _print_live_review_run_result(result: LiveReviewRunResult) -> None:
    print(f"review_run: {result.review_id}")
    print(f"task_id: {result.task_id}")
    print(f"status: {result.status}")
    if result.progress_id is not None:
        print(f"progress: {result.progress_id}")
    if result.result_path is not None:
        print(f"result_path: {result.result_path}")
    if result.failure_class is not None:
        print(f"failure_class: {result.failure_class}")
    print("created_repair_tasks:")
    if result.created_repair_task_ids:
        for task_id in result.created_repair_task_ids:
            print(f"- {task_id}")
    else:
        print("- none")
    print("existing_repair_tasks:")
    if result.existing_repair_task_ids:
        for task_id in result.existing_repair_task_ids:
            print(f"- {task_id}")
    else:
        print("- none")
    print("skipped_findings:")
    if result.skipped_finding_ids:
        for finding_id in result.skipped_finding_ids:
            print(f"- {finding_id}")
    else:
        print("- none")


def _print_applied_insight_update(update: AppliedInsightUpdate) -> None:
    action = "updated" if update.changed else "unchanged"
    print(f"insight_update: {action}")
    print(f"target_path: {update.target_path}")
    print(f"anchor: {update.anchor}")


def _print_insight_record(record: InsightRecord) -> None:
    print(f"claim: {record.claim}")
    print(f"confidence: {record.confidence}")
    print("evidence:")
    for evidence in record.evidence:
        print(f"- {evidence}")
    print(f"scope: {record.scope}")
    print("supersedes:")
    if record.supersedes:
        for superseded in record.supersedes:
            print(f"- {superseded}")
    else:
        print("- none")
    print(f"next_action: {record.next_action}")


def _print_skill_promotion_proposal(proposal: SkillPromotionProposal) -> None:
    print(f"skill_name: {proposal.skill_name}")
    print(f"motivation: {proposal.motivation}")
    print("provenance:")
    for provenance in proposal.provenance:
        print(f"- {provenance}")
    print(f"rollback_plan: {proposal.rollback_plan}")
    print("changed_paths:")
    for changed_path in proposal.changed_paths:
        print(f"- {changed_path}")
    print("golden_evals:")
    for evidence in proposal.golden_evals:
        reviewer = evidence.reviewer or "none"
        automated = evidence.automated_verdict_rationale or "none"
        print(f"- {evidence.task_id}: {evidence.status}")
        print(f"  task_name: {evidence.task_name}")
        print(f"  baseline_summary: {evidence.baseline_summary}")
        print(f"  candidate_summary: {evidence.candidate_summary}")
        print(f"  reviewer: {reviewer}")
        print(f"  automated_verdict_rationale: {automated}")


def _print_codex_state_inventory(inventory: CodexStateInventory) -> None:
    print(f"codex_home: {inventory.codex_home}")
    print(f"observed_at: {inventory.observed_at}")
    print("databases:")
    for database in inventory.databases:
        print(f"- {database.relative_path}: {database.status}")
        if database.failure_class:
            print(f"  failure_class: {database.failure_class}")
        if database.failure_reason:
            print(f"  failure_reason: {database.failure_reason}")
        if database.tables:
            print("  tables:")
            for table in database.tables:
                source_kinds = ", ".join(table.source_kinds)
                print(f"  - {table.source_table}\trows={table.row_count}\t{source_kinds}")
        else:
            print("  tables: none")


def _print_codex_state_observation_report(report: CodexStateObservationReport) -> None:
    print(f"codex_home: {report.codex_home}")
    print(f"observed_at: {report.observed_at}")
    print(f"linked_plan_id: {report.linked_plan_id or 'none'}")
    print(f"linked_task_id: {report.linked_task_id or 'none'}")
    print("observations:")
    if not report.observations:
        print("- none")
    for observation in report.observations:
        print(
            f"- {observation.source_id}\t{observation.source_kind}\t"
            f"hash={observation.raw_snapshot_hash}"
        )
        print(f"  summary: {observation.summary}")
    print("findings:")
    if not report.findings:
        print("- none")
    for finding in report.findings:
        print(f"- {finding.source_id}\t{finding.failure_class}")
        print(f"  summary: {finding.summary}")


def _print_codex_state_reconciliation_dry_run(
    report: CodexStateReconciliationDryRunReport,
) -> None:
    print(f"codex_home: {report.codex_home}")
    print(f"observed_at: {report.observed_at}")
    print(f"linked_plan_id: {report.linked_plan_id or 'none'}")
    print(f"linked_task_id: {report.linked_task_id or 'none'}")
    print("observations:")
    if not report.observations:
        print("- none")
    for observation in report.observations:
        print(f"- {observation.source_id}\t{observation.source_kind}")
    print("proposals:")
    if not report.proposals:
        print("- none")
    for proposal in report.proposals:
        print(
            f"- {proposal.proposal_id}\t{proposal.action_type}\t"
            f"{proposal.source_id}\t{proposal.action_status}"
        )
        print(f"  summary: {proposal.summary}")
    print("findings:")
    if not report.findings:
        print("- none")
    for finding in report.findings:
        print(f"- {finding.finding_type}\t{finding.source_id}\t{finding.failure_class}")
        print(f"  summary: {finding.summary}")


def _print_codex_state_reconciliation_apply_report(
    report: CodexStateReconciliationApplyReport,
) -> None:
    print(f"codex_home: {report.codex_home}")
    print(f"observed_at: {report.observed_at}")
    print("approved_proposal_ids:")
    if not report.approved_proposal_ids:
        print("- none")
    for proposal_id in report.approved_proposal_ids:
        print(f"- {proposal_id}")
    print("applied:")
    if not report.applied:
        print("- none")
    for applied in report.applied:
        print(f"- {applied.proposal_id}\t{applied.action_type}\t{applied.action_status}")
        print(f"  progress_id: {applied.progress_id}")
        print(f"  artifact_id: {applied.artifact_id}")
    print("skipped:")
    if not report.skipped:
        print("- none")
    for skipped in report.skipped:
        print(f"- {skipped.proposal_id}\t{skipped.action_type}\t{skipped.skip_reason}")
    print("findings:")
    if not report.findings:
        print("- none")
    for finding in report.findings:
        print(f"- {finding.finding_type}\t{finding.source_id}\t{finding.failure_class}")
        print(f"  summary: {finding.summary}")


def _print_codex_automation_bridge_dry_run(
    report: CodexAutomationBridgeDryRunReport,
) -> None:
    print(f"workspace_root: {report.workspace_root}")
    print(f"observed_at: {report.observed_at}")
    print(f"source_plan_id: {report.source_plan_id or 'none'}")
    print(f"source_task_id: {report.source_task_id or 'none'}")
    print("proposals:")
    if not report.proposals:
        print("- none")
    for proposal in report.proposals:
        print(f"- {proposal.proposal_id}\t{proposal.kind}\t{proposal.name}")
        print(f"  action_status: {proposal.action_status}")
        print(f"  rrule: {proposal.rrule}")
        print(f"  cwds: {', '.join(proposal.cwds) if proposal.cwds else 'none'}")
        print(f"  summary: {proposal.summary}")
    print("findings:")
    if not report.findings:
        print("- none")
    for finding in report.findings:
        print(f"- {finding.finding_type}\t{finding.source_id}\t{finding.failure_class}")
        print(f"  summary: {finding.summary}")


def _to_jsonable(value: object) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        dataclass_value = cast(Any, value)
        return {
            field.name: _to_jsonable(getattr(dataclass_value, field.name))
            for field in fields(dataclass_value)
        }
    if isinstance(value, tuple | list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    return value


def _build_plan_summary_entry(
    snapshot: PlanningSummarySnapshot,
    plan: PlanRecord,
) -> dict[str, object]:
    tasks = tuple(task for task in snapshot.tasks if task.plan_id == plan.plan_id)
    task_ids = {task.task_id for task in tasks}
    return {
        "plan": plan,
        "milestones": tuple(
            milestone for milestone in snapshot.milestones if milestone.plan_id == plan.plan_id
        ),
        "acceptance_criteria": tuple(
            criterion for criterion in snapshot.criteria if criterion.plan_id == plan.plan_id
        ),
        "decisions": tuple(
            decision for decision in snapshot.decisions if decision.plan_id == plan.plan_id
        ),
        "progress": tuple(
            progress for progress in snapshot.progress if progress.plan_id == plan.plan_id
        ),
        "tasks": tasks,
        "commit_links": tuple(
            commit_link
            for commit_link in snapshot.commit_links
            if commit_link.plan_id == plan.plan_id
        ),
        "artifact_links": tuple(
            artifact_link
            for artifact_link in snapshot.artifact_links
            if artifact_link.plan_id == plan.plan_id
        ),
        "worker_runs": tuple(run for run in snapshot.worker_runs if run.task_id in task_ids),
    }


def _print_plan_summary(summary: dict[str, object]) -> None:
    plan = cast(PlanRecord, summary["plan"])
    print(f"{plan.plan_id}\t{plan.status}\tpriority={plan.priority}\t{plan.title}")
    print("milestones:")
    for milestone in cast(tuple[PlanMilestoneRecord, ...], summary["milestones"]):
        print(f"- {milestone.milestone_id}\t{milestone.status}\t{milestone.title}")
    print("acceptance_criteria:")
    for criterion in cast(
        tuple[PlanAcceptanceCriterionRecord, ...],
        summary["acceptance_criteria"],
    ):
        print(f"- {criterion.criterion_id}\t{criterion.status}\t{criterion.description}")
    print("decisions:")
    for decision in cast(tuple[PlanDecisionRecord, ...], summary["decisions"]):
        print(f"- {decision.decision_id}\t{decision.decision}")
    print("progress:")
    for progress in cast(tuple[PlanProgressRecord, ...], summary["progress"]):
        print(f"- {progress.progress_id}\t{progress.event_type}\t{progress.summary}")
    print("tasks:")
    for task in cast(tuple[SupervisorTaskSummaryRecord, ...], summary["tasks"]):
        print(f"- {task.task_id}\t{task.status}\t{task.task_type}\t{task.title}")
    print("")


def seed_bootstrap_plan(store: PlanningSQLiteStore) -> None:
    """Seed the bootstrap plan if it is not already present."""

    existing_plans = {plan.plan_id: plan for plan in store.list_plans()}
    bootstrap_plan = existing_plans.get("plan-bootstrap-supervisor")
    bootstrap_plan = PlanRecord(
        plan_id="plan-bootstrap-supervisor",
        slug="bootstrap-supervisor",
        title="Bootstrap Codex Supervisor",
        goal=(
            "Create the Python-first supervisor repo with source-of-truth docs, "
            "planning SQLite, source locks, insights, skills, source clones, and handoff."
        ),
        status=bootstrap_plan.status if bootstrap_plan else "active",
        priority=100,
        owner_agent="codex",
        non_goals={
            "full_runtime": "Do not implement the complete worker orchestration runtime yet.",
            "source_vendoring": "Do not vendor cloned source repositories.",
        },
        context={
            "patterns": [
                "nlp-stock-prediction planning SQLite",
                "codex-subagent-testing source locks",
                "tech-resume insights wiki",
                "observe-safety source-of-truth validation",
            ],
            "repo_root": "<repo-root>",
        },
        superseded_by_plan_id=bootstrap_plan.superseded_by_plan_id if bootstrap_plan else None,
    )
    store.upsert_plan(bootstrap_plan)
    with suppress(sqlite3.IntegrityError):
        store.add_plan_decision(
            PlanDecisionRecord(
                decision_id="decision-bootstrap-python-first",
                plan_id="plan-bootstrap-supervisor",
                decision="Build the supervisor core primarily in Python.",
                rationale=(
                    "Python gives strong cross-platform filesystem, SQLite, subprocess, "
                    "and test support."
                ),
            )
        )
    with suppress(sqlite3.IntegrityError):
        store.add_plan_progress(
            PlanProgressRecord(
                progress_id="progress-bootstrap-created",
                plan_id="plan-bootstrap-supervisor",
                event_type="started",
                summary="Bootstrap repository created and initial source-of-truth documents added.",
            )
        )
    existing_tasks = {task.task_id: task for task in store.list_supervisor_tasks()}
    existing_bootstrap_task = existing_tasks.get("task-bootstrap-orient-and-plan")
    if bootstrap_plan.status == "active":
        store.upsert_supervisor_task(
            SupervisorTaskRecord(
                task_id="task-bootstrap-orient-and-plan",
                plan_id="plan-bootstrap-supervisor",
                title="Orient and continue bootstrap implementation",
                goal=(
                    "Read the source-of-truth docs, inspect planning SQLite, and continue the "
                    "highest-priority bootstrap work with verification and handoff updates."
                ),
                task_type="AFK",
                status=existing_bootstrap_task.status if existing_bootstrap_task else "ready",
                scope={
                    "read_first": [
                        "README.md",
                        "AGENTS.md",
                        "PLANS.md",
                        "ROADMAP.md",
                        "HANDOFF.md",
                    ],
                    "workflow": "Use typed planning helpers and update durable state.",
                },
                out_of_scope={
                    "source_clones": "Do not vendor ignored source clones.",
                    "codex_databases": "Do not write directly to local Codex internal databases.",
                },
                acceptance_criteria=[
                    "Fresh thread can discover this task with story-loop-status.",
                    "Implementation work follows the active source-of-truth docs.",
                    "Default verification passes before handoff.",
                ],
                verification_commands=["uv run --no-sync python -B scripts/verify.py"],
                allowed_paths=[
                    "src/**",
                    "tests/**",
                    "scripts/**",
                    "plans/planning.sqlite3",
                    "README.md",
                    "AGENTS.md",
                    "PLANS.md",
                    "ROADMAP.md",
                    "HANDOFF.md",
                ],
            ),
            validate_current_queue_contract=True,
        )


def _task_claimability_reason(
    task: SupervisorTaskSummaryRecord,
    all_tasks: tuple[SupervisorTaskSummaryRecord, ...],
    worker_runs: tuple[WorkerRunRecord, ...],
) -> str:
    reasons: list[str] = []
    if task.plan_status != "active":
        reasons.append(f"plan-{task.plan_status}")
    if task.task_type != "AFK":
        reasons.append("hitl")
    blockers = unresolved_task_blockers(task, all_tasks)
    if blockers:
        reasons.append("blocked-by=" + ",".join(blockers))
    if task.task_type == "AFK":
        missing_fields = missing_execution_contract_fields(task)
        if missing_fields:
            reasons.append("missing=" + ",".join(missing_fields))
    if has_nonterminal_worker_run(task.task_id, worker_runs):
        reasons.append("worker-run-active")
    return ";".join(reasons) if reasons else "unblocked"


if __name__ == "__main__":
    raise SystemExit(main())
