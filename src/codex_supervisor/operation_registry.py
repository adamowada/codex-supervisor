"""Canonical supervisor operation names across CLI, MCP, and plugin checks."""

from __future__ import annotations

from dataclasses import dataclass

FULL_AFK_MCP_SURFACE = "full_afk_mcp_surface"
PLUGIN_INSTALL_MCP_SURFACE = "plugin_install_mcp_surface"


@dataclass(frozen=True)
class SupervisorOperation:
    """One supervisor operation as exposed through one or more public surfaces."""

    name: str
    cli_command: str | None = None
    mcp_tool: str | None = None
    read_only: bool = True
    long_running: bool = False
    surface_groups: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()


def _mcp(name: str) -> str:
    return f"codex_supervisor.{name}"


OPERATIONS: tuple[SupervisorOperation, ...] = (
    SupervisorOperation(
        "artifact_link_add",
        "artifact-link-add",
        _mcp("artifact_link_add"),
        read_only=False,
        surface_groups=(PLUGIN_INSTALL_MCP_SURFACE,),
    ),
    SupervisorOperation("ci_run_record", "ci-run-record", read_only=False),
    SupervisorOperation("cleanup_plan", "cleanup-plan"),
    SupervisorOperation("codex_automation_apply", "codex-automation-apply", read_only=False),
    SupervisorOperation("codex_automation_dry_run", "codex-automation-dry-run"),
    SupervisorOperation("codex_state_inventory", "codex-state-inventory"),
    SupervisorOperation("codex_state_observations", "codex-state-observations"),
    SupervisorOperation(
        "codex_state_reconcile_apply", "codex-state-reconcile-apply", read_only=False
    ),
    SupervisorOperation("codex_state_reconcile_dry_run", "codex-state-reconcile-dry-run"),
    SupervisorOperation("commit_link_add", "commit-link-add", read_only=False),
    SupervisorOperation("commit_link_delete", "commit-link-delete", read_only=False),
    SupervisorOperation(
        "criterion_status", "criterion-status", _mcp("criterion_status"), read_only=False
    ),
    SupervisorOperation(
        "criterion_upsert", "criterion-upsert", _mcp("criterion_upsert"), read_only=False
    ),
    SupervisorOperation("decision_add", "decision-add", _mcp("decision_add"), read_only=False),
    SupervisorOperation("factory_loop_smoke", "factory-loop-smoke", long_running=True),
    SupervisorOperation(
        "github_pr_lifecycle", "github-pr-lifecycle", read_only=False, long_running=True
    ),
    SupervisorOperation("goal_contract_render", "goal-contract-render"),
    SupervisorOperation("insight_update", "insight-update", read_only=False),
    SupervisorOperation("insight_validate", "insight-validate"),
    SupervisorOperation("issue_comment_record", "issue-comment-record", read_only=False),
    SupervisorOperation(
        "milestone_status", "milestone-status", _mcp("milestone_status"), read_only=False
    ),
    SupervisorOperation(
        "milestone_upsert", "milestone-upsert", _mcp("milestone_upsert"), read_only=False
    ),
    SupervisorOperation("plan_init", "plan-init", read_only=False),
    SupervisorOperation("plan_list", "plan-list", _mcp("plan_list")),
    SupervisorOperation("plan_migrate_schema", "plan-migrate-schema", read_only=False),
    SupervisorOperation("plan_status", "plan-status", _mcp("plan_status"), read_only=False),
    SupervisorOperation("plan_summary", "plan-summary"),
    SupervisorOperation("plan_upsert", "plan-upsert", _mcp("plan_upsert"), read_only=False),
    SupervisorOperation("pr_evidence_record", "pr-evidence-record", read_only=False),
    SupervisorOperation(
        "progress_add",
        "progress-add",
        _mcp("progress_add"),
        read_only=False,
        surface_groups=(PLUGIN_INSTALL_MCP_SURFACE,),
    ),
    SupervisorOperation("project_list", "project-list", _mcp("project_list")),
    SupervisorOperation("project_seed_tasks", "project-seed-tasks", read_only=False),
    SupervisorOperation("release_evidence_refresh", "release-evidence-refresh", read_only=False),
    SupervisorOperation("release_readiness", "release-readiness"),
    SupervisorOperation(
        "review_result_ingest",
        "review-result-ingest",
        _mcp("review_result_ingest"),
        read_only=False,
        surface_groups=(PLUGIN_INSTALL_MCP_SURFACE,),
    ),
    SupervisorOperation("review_result_promote", "review-result-promote", read_only=False),
    SupervisorOperation("review_run_live", "review-run-live", read_only=False, long_running=True),
    SupervisorOperation(
        "runtime_preflight",
        "runtime-preflight",
        _mcp("runtime_preflight"),
        surface_groups=(FULL_AFK_MCP_SURFACE, PLUGIN_INSTALL_MCP_SURFACE),
    ),
    SupervisorOperation("skill_promotion_validate", "skill-promotion-validate"),
    SupervisorOperation("spawned_project_apply", "spawned-project-apply", read_only=False),
    SupervisorOperation("spawned_project_classify", "spawned-project-classify"),
    SupervisorOperation("spawned_project_propose", "spawned-project-propose"),
    SupervisorOperation(
        "story_loop_advance",
        "story-loop-advance",
        _mcp("story_loop_advance"),
        read_only=False,
        long_running=True,
    ),
    SupervisorOperation(
        "story_loop_record", "story-loop-record", _mcp("story_loop_record"), read_only=False
    ),
    SupervisorOperation(
        "story_loop_run_once",
        "story-loop-run-once",
        _mcp("story_loop_run_once"),
        read_only=False,
        long_running=True,
        surface_groups=(FULL_AFK_MCP_SURFACE, PLUGIN_INSTALL_MCP_SURFACE),
    ),
    SupervisorOperation(
        "story_loop_status",
        "story-loop-status",
        _mcp("story_loop_status"),
        surface_groups=(FULL_AFK_MCP_SURFACE, PLUGIN_INSTALL_MCP_SURFACE),
    ),
    SupervisorOperation(
        "task_claim",
        "task-claim",
        _mcp("task_claim"),
        read_only=False,
        surface_groups=(FULL_AFK_MCP_SURFACE, PLUGIN_INSTALL_MCP_SURFACE),
    ),
    SupervisorOperation("task_compile", "task-compile", _mcp("task_compile"), read_only=False),
    SupervisorOperation(
        "task_current",
        "task-current",
        _mcp("task_current"),
        surface_groups=(FULL_AFK_MCP_SURFACE,),
        aliases=("legacy_current_executable_afk_task", "task_next_afk"),
    ),
    SupervisorOperation(
        "task_next_afk",
        "task-next-afk",
        _mcp("task_next_afk"),
        surface_groups=(FULL_AFK_MCP_SURFACE,),
        aliases=("current_executable_afk_task",),
    ),
    SupervisorOperation("task_list", "task-list"),
    SupervisorOperation(
        "task_show", "task-show", _mcp("task_show"), surface_groups=(PLUGIN_INSTALL_MCP_SURFACE,)
    ),
    SupervisorOperation("task_status", "task-status", _mcp("task_status"), read_only=False),
    SupervisorOperation(
        "task_upsert",
        "task-upsert",
        _mcp("task_upsert"),
        read_only=False,
        surface_groups=(PLUGIN_INSTALL_MCP_SURFACE,),
    ),
    SupervisorOperation(
        "worker_result_ingest",
        "worker-result-ingest",
        _mcp("worker_result_ingest"),
        read_only=False,
        aliases=("worker-run-status --status completed --result-path",),
    ),
    SupervisorOperation("worker_result_list", "worker-result-list", _mcp("worker_result_list")),
    SupervisorOperation("worker_result_show", "worker-result-show", _mcp("worker_result_show")),
    SupervisorOperation("worker_run_event_list", mcp_tool=_mcp("worker_run_event_list")),
    SupervisorOperation("worker_run_list", "worker-run-list", _mcp("worker_run_list")),
    SupervisorOperation("worker_run_show", "worker-run-show", _mcp("worker_run_show")),
    SupervisorOperation(
        "worker_run_status", "worker-run-status", _mcp("worker_run_status"), read_only=False
    ),
    SupervisorOperation(
        "worker_run_upsert", "worker-run-upsert", _mcp("worker_run_upsert"), read_only=False
    ),
)

OPERATIONS_BY_NAME = {operation.name: operation for operation in OPERATIONS}
OPERATIONS_BY_CLI_COMMAND = {
    operation.cli_command: operation
    for operation in OPERATIONS
    if operation.cli_command is not None
}
OPERATIONS_BY_MCP_TOOL = {
    operation.mcp_tool: operation for operation in OPERATIONS if operation.mcp_tool is not None
}


def operation_by_name(name: str) -> SupervisorOperation:
    return OPERATIONS_BY_NAME[name]


def operation_by_cli_command(command: str) -> SupervisorOperation:
    return OPERATIONS_BY_CLI_COMMAND[command]


def operation_by_mcp_tool(tool_name: str) -> SupervisorOperation:
    return OPERATIONS_BY_MCP_TOOL[tool_name]


def cli_command_names() -> frozenset[str]:
    return frozenset(OPERATIONS_BY_CLI_COMMAND)


def mcp_tool_names() -> frozenset[str]:
    return frozenset(OPERATIONS_BY_MCP_TOOL)


def required_mcp_tool_names(surface_group: str) -> frozenset[str]:
    return frozenset(
        operation.mcp_tool
        for operation in OPERATIONS
        if operation.mcp_tool is not None and surface_group in operation.surface_groups
    )
