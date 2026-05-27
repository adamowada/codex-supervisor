"""Supervisor runtime preflight and execution-mode ledger."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codex_supervisor.operation_registry import (
    FULL_AFK_MCP_SURFACE,
    required_mcp_tool_names,
)
from codex_supervisor.paths import default_planning_database_path

JsonObject = dict[str, Any]

REQUIRED_SUPERVISOR_MCP_TOOLS = required_mcp_tool_names(FULL_AFK_MCP_SURFACE)


@dataclass(frozen=True)
class RuntimePreflightIssue:
    code: str
    severity: str
    message: str
    next_action: str


@dataclass(frozen=True)
class ExecutionModeLedger:
    entrypoint: str
    required_surface: str
    decision_source: str
    supervisor_backend: str
    planning_state: str
    worker_execution: str
    goal_contract: str
    project_scaffold: str
    database_mode: str
    evidence_mode: str
    mutation_policy: str
    queue_discovery: str
    setup_policy: str
    mcp_tools_state: str


@dataclass(frozen=True)
class RuntimePreflightReport:
    ok: bool
    status: str
    ledger: ExecutionModeLedger
    issues: tuple[RuntimePreflightIssue, ...] = ()
    diagnostics: JsonObject = field(default_factory=dict)


def build_runtime_preflight_report(
    *,
    repo_root: Path,
    planning_path: Path | None = None,
    full_afk: bool = False,
    plugin_invocation: bool = False,
    plugin_full_afk: bool = False,
    supervisor_backend: str = "mcp",
    mcp_tools: tuple[str, ...] = (),
    cli_available: bool = True,
    worker_execution: str = "codex_exec",
    native_goal_mode: bool = False,
    supervisor_task_id: str | None = None,
    goal_contract_linked: bool = False,
    story_loop_status_checked: bool = False,
    task_current_requested: bool = False,
    task_next_afk_requested: bool = False,
    scaffold_tier: str = "supervisor_managed",
    database_mode: str = "persistent_mongodb",
    evidence_mode: str = "strict_jsonl",
    mutation_policy: str = "allowed",
    setup_mutations: tuple[str, ...] = (),
    allow_setup_mutations: bool = False,
    mcp_startup_diagnostic: str | None = None,
    preflight_surface: str = "live_mcp",
) -> RuntimePreflightReport:
    """Build a fail-closed preflight report for supervised Desktop/AFK work."""

    effective_planning_path = planning_path or default_planning_database_path(repo_root)
    planning_exists = effective_planning_path.exists()
    tool_aliases = {
        original: normalized
        for original, normalized in (
            (tool, _normalize_mcp_tool_name(tool)) for tool in mcp_tools if tool.strip()
        )
        if original != normalized
    }
    tool_set = {_normalize_mcp_tool_name(tool) for tool in mcp_tools if tool.strip()}
    missing_mcp_tools = tuple(sorted(REQUIRED_SUPERVISOR_MCP_TOOLS - tool_set))
    plugin_full_afk_entrypoint = plugin_full_afk or (plugin_invocation and full_afk)
    entrypoint = (
        "desktop_plugin"
        if plugin_invocation or plugin_full_afk
        else "cli"
        if preflight_surface == "cli_diagnostic"
        else "api"
    )
    required_surface = "live_mcp" if plugin_full_afk_entrypoint else supervisor_backend
    decision_source = preflight_surface if preflight_surface else "unknown"
    issues: list[RuntimePreflightIssue] = []

    if mcp_startup_diagnostic:
        issues.append(
            RuntimePreflightIssue(
                code="mcp_startup_failed",
                severity="blocked",
                message=mcp_startup_diagnostic,
                next_action=(
                    "Repair the plugin MCP startup path before treating this as a supervisor run."
                ),
            )
        )

    if plugin_invocation and supervisor_backend in {"unavailable", "skill_only"}:
        issues.append(
            RuntimePreflightIssue(
                code="supervisor_backend_unavailable",
                severity="blocked",
                message=(
                    "The codex-supervisor skill is loaded but no supervisor backend is attached."
                ),
                next_action=("Expose live MCP tools before starting plugin-supervised work."),
            )
        )

    if plugin_full_afk_entrypoint and preflight_surface != "live_mcp":
        issues.append(
            RuntimePreflightIssue(
                code="cli_diagnostic_not_plugin_full_afk_authority",
                severity="blocked",
                message=(
                    "Desktop plugin full-AFK readiness must be approved by a live MCP canary in "
                    "the current Desktop session; CLI preflight is diagnostic only."
                ),
                next_action=(
                    "Call codex_supervisor.runtime_preflight through MCP, or repair MCP startup "
                    "before launching plugin full-AFK work."
                ),
            )
        )

    if plugin_full_afk_entrypoint and supervisor_backend != "mcp":
        issues.append(
            RuntimePreflightIssue(
                code="live_mcp_required_for_plugin_full_afk",
                severity="blocked",
                message="Desktop plugin full-AFK requires the live MCP supervisor backend.",
                next_action=(
                    "Repair or expose the MCP server; do not substitute CLI or current-thread "
                    "execution for plugin full-AFK."
                ),
            )
        )

    if plugin_invocation and not mcp_tools and not cli_available:
        issues.append(
            RuntimePreflightIssue(
                code="mcp_and_cli_unavailable",
                severity="blocked",
                message="Neither supervisor MCP tools nor CLI diagnostics are available.",
                next_action=(
                    "Run setup repair or continue explicitly as plain Codex outside supervisor "
                    "mode."
                ),
            )
        )

    if (supervisor_backend == "mcp" or plugin_full_afk_entrypoint) and missing_mcp_tools:
        issues.append(
            RuntimePreflightIssue(
                code="mcp_tools_missing",
                severity="blocked",
                message="Supervisor MCP is missing required tools: " + ", ".join(missing_mcp_tools),
                next_action="Fix MCP startup/tool registration before launching full-AFK work.",
            )
        )

    if full_afk and not planning_exists:
        issues.append(
            RuntimePreflightIssue(
                code="planning_db_missing",
                severity="blocked",
                message=(
                    "Full-AFK supervision requires plans/planning.sqlite3 before implementation."
                ),
                next_action="Create or select a supervisor-managed project scaffold first.",
            )
        )

    if full_afk and worker_execution == "current_thread":
        issues.append(
            RuntimePreflightIssue(
                code="current_thread_fallback_blocked",
                severity="blocked",
                message=(
                    "Current-thread implementation is not a valid full-AFK worker execution mode."
                ),
                next_action="Launch through the worker backend or record a blocker/HITL task.",
            )
        )

    if native_goal_mode and (not supervisor_task_id or not goal_contract_linked):
        issues.append(
            RuntimePreflightIssue(
                code="native_goal_unlinked",
                severity="blocked",
                message=(
                    "Native Goal Mode is allowed only when linked to a supervisor task and Goal "
                    "Contract."
                ),
                next_action=(
                    "Render/link the supervisor Goal Contract before enabling native Goals."
                ),
            )
        )

    if plugin_full_afk and scaffold_tier != "supervisor_managed":
        issues.append(
            RuntimePreflightIssue(
                code="plugin_full_afk_requires_supervisor_scaffold",
                severity="blocked",
                message="Plugin full-AFK requests must use the supervisor-managed scaffold tier.",
                next_action="Run spawned-project bootstrap with supervisor-managed planning state.",
            )
        )

    if full_afk and database_mode in {"memory_mongodb", "memory_database", "in_memory"}:
        issues.append(
            RuntimePreflightIssue(
                code="memory_database_fallback_forbidden",
                severity="blocked",
                message="Memory database fallback cannot satisfy supervised full-AFK acceptance.",
                next_action=(
                    "Use the requested persistent database or explicitly downgrade outside "
                    "supervisor mode."
                ),
            )
        )

    if full_afk and evidence_mode != "strict_jsonl":
        issues.append(
            RuntimePreflightIssue(
                code="degraded_evidence_blocked",
                severity="blocked",
                message="Full-AFK supervision requires strict evidence capture.",
                next_action="Disable degraded evidence mode or record the run as blocked.",
            )
        )

    next_afk_selector_requested = task_current_requested or task_next_afk_requested

    if next_afk_selector_requested and not story_loop_status_checked:
        issues.append(
            RuntimePreflightIssue(
                code="story_loop_status_required",
                severity="blocked",
                message=(
                    "task-next-afk and legacy task-current may only be used after "
                    "story-loop-status has established queue state."
                ),
                next_action=(
                    "Run story-loop-status first, then call task-next-afk as the AFK selector."
                ),
            )
        )

    if setup_mutations and not allow_setup_mutations:
        issues.append(
            RuntimePreflightIssue(
                code="setup_mutation_requires_approval",
                severity="blocked",
                message="Setup mutations require explicit approval: " + ", ".join(setup_mutations),
                next_action=(
                    "Ask before editing PATH, installing host tools, starting Docker, or "
                    "mutating CODEX_HOME."
                ),
            )
        )

    ledger = ExecutionModeLedger(
        entrypoint=entrypoint,
        required_surface=required_surface,
        decision_source=decision_source,
        supervisor_backend=supervisor_backend,
        planning_state="existing" if planning_exists else "unavailable",
        worker_execution=worker_execution,
        goal_contract=_goal_contract_mode(
            native_goal_mode=native_goal_mode,
            supervisor_task_id=supervisor_task_id,
            goal_contract_linked=goal_contract_linked,
        ),
        project_scaffold=scaffold_tier,
        database_mode=database_mode,
        evidence_mode=evidence_mode,
        mutation_policy=mutation_policy,
        queue_discovery=(
            "story_loop_status_then_task_next_afk"
            if story_loop_status_checked and next_afk_selector_requested
            else "task_next_afk_without_story_loop_status"
            if task_next_afk_requested
            else "task_current_without_story_loop_status"
            if task_current_requested
            else "not_requested"
        ),
        setup_policy="approved" if allow_setup_mutations else "approval_required",
        mcp_tools_state="complete" if not missing_mcp_tools else "missing",
    )
    diagnostics: JsonObject = {
        "repo_root": _display_path(repo_root),
        "planning_path": _display_path(effective_planning_path),
        "plugin_invocation": plugin_invocation,
        "full_afk": full_afk,
        "plugin_full_afk": plugin_full_afk,
        "cli_available": cli_available,
        "preflight_surface": preflight_surface,
        "missing_mcp_tools": list(missing_mcp_tools),
        "normalized_mcp_tools": sorted(tool_set),
        "mcp_tool_aliases": dict(sorted(tool_aliases.items())),
        "setup_mutations": list(setup_mutations),
    }
    if mcp_startup_diagnostic:
        diagnostics["mcp_startup_diagnostic"] = mcp_startup_diagnostic
    return RuntimePreflightReport(
        ok=not issues,
        status="passed" if not issues else "blocked",
        ledger=ledger,
        issues=tuple(issues),
        diagnostics=diagnostics,
    )


def _normalize_mcp_tool_name(tool_name: str) -> str:
    value = tool_name.strip()
    for prefix in ("mcp__codex_supervisor__.", "mcp__codex_supervisor__"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            if value.startswith("."):
                value = value[1:]
            break
    if value.startswith("codex_supervisor_") and "." not in value:
        return "codex_supervisor." + value.removeprefix("codex_supervisor_")
    return value


def _goal_contract_mode(
    *,
    native_goal_mode: bool,
    supervisor_task_id: str | None,
    goal_contract_linked: bool,
) -> str:
    if native_goal_mode and supervisor_task_id and goal_contract_linked:
        return "native_goal_linked_to_supervisor_contract"
    if native_goal_mode:
        return "native_goal_unlinked"
    if goal_contract_linked:
        return "prompt_rendered_linked_to_supervisor_contract"
    return "missing"


def _display_path(path: Path) -> str:
    resolved = path.resolve(strict=False)
    return f"<path:{resolved.name or '.'}>"
