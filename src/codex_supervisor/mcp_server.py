"""MCP tool registry and dispatcher."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

from codex_supervisor.paths import default_planning_database_path, find_repo_root
from codex_supervisor.planning import (
    CLAIM_WORKER_RUN_STATUSES,
    CRITERION_STATUSES,
    MILESTONE_STATUSES,
    PLAN_STATUSES,
    TASK_STATUSES,
    TASK_TYPES,
    WORKER_RUN_STATUSES,
    PlanAcceptanceCriterionRecord,
    PlanArtifactLinkRecord,
    PlanDecisionRecord,
    PlanMilestoneRecord,
    PlanningSQLiteStore,
    PlanProgressRecord,
    PlanRecord,
    SupervisorTaskRecord,
    SupervisorTaskSummaryRecord,
    WorkerRunRecord,
    open_existing_planning_database,
)
from codex_supervisor.projects import discover_projects
from codex_supervisor.queue_selection import (
    select_next_executable_afk_task,
    story_loop_status_required_message,
)
from codex_supervisor.review_loop import validate_review_result_payload
from codex_supervisor.review_persistence import record_review_result
from codex_supervisor.review_repairs import (
    DEFAULT_REPAIR_VERIFICATION_COMMANDS,
    apply_repair_task_plan,
    plan_repair_tasks_from_review_result,
)
from codex_supervisor.runtime_preflight import build_runtime_preflight_report
from codex_supervisor.story_loop import (
    advance_story_loop_once,
    build_story_loop_status,
    poll_story_loop_run_async,
    record_story_loop_progress,
    run_live_story_loop_once,
    start_story_loop_run_async,
)
from codex_supervisor.task_compiler import apply_compiled_tasks, compile_tasks_from_plan
from codex_supervisor.worker_result_ingestion import ingest_worker_result_path

JsonObject = dict[str, Any]
McpHandler = Callable[[JsonObject, "McpServerContext"], Any]


@dataclass(frozen=True)
class McpToolDefinition:
    """Thin MCP tool definition compatible with JSON-schema-style inputs."""

    name: str
    description: str
    input_schema: JsonObject
    read_only: bool = True

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }
        if self.read_only:
            payload["annotations"] = {"readOnlyHint": True}
        return payload


@dataclass(frozen=True)
class McpServerContext:
    """Runtime context for in-process MCP tool dispatch."""

    repo_root: Path | None = None
    planning_path: Path | None = None
    project_roots: tuple[Path, ...] = ()
    trust_policy: str = "local_trusted"
    enabled: bool = True
    mutations_enabled: bool = True

    def resolved_repo_root(self) -> Path:
        return (self.repo_root or find_repo_root()).resolve()

    def resolved_planning_path(self) -> Path:
        if self.planning_path is not None:
            return self.planning_path.resolve()
        return default_planning_database_path(self.resolved_repo_root())

    def resolved_project_roots(self) -> tuple[Path, ...]:
        if self.project_roots:
            return tuple(path.resolve() for path in self.project_roots)
        return (self.resolved_repo_root(),)


class McpDispatchError(ValueError):
    """Tool dispatch error rendered into a structured MCP error envelope."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def list_mcp_tools(*, context: McpServerContext | None = None) -> tuple[JsonObject, ...]:
    """Return the MCP tools exposed by this server context."""

    dispatch_context = context or McpServerContext()
    if not dispatch_context.enabled:
        return ()
    return tuple(
        tool.to_payload()
        for tool in TOOL_DEFINITIONS.values()
        if tool.read_only or dispatch_context.mutations_enabled
    )


def dispatch_mcp_tool(
    tool_name: str,
    arguments: object | None = None,
    *,
    context: McpServerContext | None = None,
) -> JsonObject:
    """Dispatch one MCP tool and return a normalized result envelope."""

    dispatch_context = context or McpServerContext()
    if not dispatch_context.enabled:
        return _error_result(tool_name, "mcp_disabled", "MCP dispatch is disabled.")
    definition = TOOL_DEFINITIONS.get(tool_name)
    handler = TOOL_HANDLERS.get(tool_name)
    if definition is None or handler is None:
        return _error_result(tool_name, "unknown_tool", f"Unknown MCP tool: {tool_name}")
    if not definition.read_only and not dispatch_context.mutations_enabled:
        return _error_result(
            tool_name,
            "mcp_mutations_disabled",
            "MCP mutations are disabled for this server context.",
        )
    try:
        validated_arguments = _validate_arguments(definition, arguments)
        data = handler(validated_arguments, dispatch_context)
    except McpDispatchError as exc:
        return _error_result(tool_name, exc.code, exc.message)
    except (OSError, sqlite3.Error, ValueError) as exc:
        return _error_result(tool_name, "read_failed", str(exc))
    return {
        "ok": True,
        "tool": tool_name,
        "data": _to_jsonable(data),
    }


def _handle_project_list(arguments: JsonObject, context: McpServerContext) -> tuple[object, ...]:
    root_paths = arguments.get("root_paths")
    trust_policy = str(arguments.get("trust_policy") or context.trust_policy)
    roots = (
        tuple(_project_root_from_argument(path, context) for path in root_paths)
        if isinstance(root_paths, list)
        else context.resolved_project_roots()
    )
    _require_project_roots_in_scope(roots, context.resolved_project_roots())
    entries = discover_projects(roots, trust_policy=trust_policy)
    return tuple(_redacted_project_entry(entry) for entry in entries)


def _handle_story_loop_status(arguments: JsonObject, context: McpServerContext) -> object:
    store = _open_store(context)
    plan_id = _optional_string(arguments.get("plan_id"))
    if plan_id is not None:
        _require_plan_visible(store, plan_id=plan_id, include_all=bool(arguments.get("all")))
    return build_story_loop_status(
        store,
        active_only=not bool(arguments.get("all")),
        plan_id=plan_id,
    )


def _handle_plan_list(arguments: JsonObject, context: McpServerContext) -> tuple[object, ...]:
    store = _open_store(context)
    return store.list_plans(status=_optional_string(arguments.get("status")))


def _handle_runtime_preflight(arguments: JsonObject, context: McpServerContext) -> object:
    supervisor_backend = str(arguments.get("supervisor_backend") or "mcp")
    supplied_mcp_tools = tuple(
        item for item in arguments.get("mcp_tools", ()) if isinstance(item, str) and item.strip()
    )
    live_mcp_tools: tuple[str, ...] = (
        tuple(
            tool["name"]
            for tool in list_mcp_tools(context=context)
            if isinstance(tool.get("name"), str)
        )
        if supervisor_backend == "mcp"
        else ()
    )
    mcp_startup_diagnostic = _optional_string(arguments.get("mcp_startup_diagnostic"))
    if supervisor_backend == "mcp" and live_mcp_tools:
        mcp_startup_diagnostic = None
    return build_runtime_preflight_report(
        repo_root=context.resolved_repo_root(),
        planning_path=context.resolved_planning_path(),
        full_afk=bool(arguments.get("full_afk", False)),
        plugin_invocation=bool(arguments.get("plugin_invocation", False)),
        plugin_full_afk=bool(arguments.get("plugin_full_afk", False)),
        supervisor_backend=supervisor_backend,
        mcp_tools=tuple(dict.fromkeys((*supplied_mcp_tools, *live_mcp_tools))),
        cli_available=bool(arguments.get("cli_available", True)),
        worker_execution=str(arguments.get("worker_execution") or "codex_exec"),
        native_goal_mode=bool(arguments.get("native_goal_mode", False)),
        supervisor_task_id=_optional_string(arguments.get("supervisor_task_id")),
        goal_contract_linked=bool(arguments.get("goal_contract_linked", False)),
        story_loop_status_checked=bool(arguments.get("story_loop_status_checked", False)),
        task_current_requested=bool(arguments.get("task_current_requested", False)),
        task_next_afk_requested=bool(arguments.get("task_next_afk_requested", False)),
        scaffold_tier=str(arguments.get("scaffold_tier") or "supervisor_managed"),
        database_mode=str(arguments.get("database_mode") or "persistent_mongodb"),
        evidence_mode=str(arguments.get("evidence_mode") or "strict_jsonl"),
        mutation_policy=str(arguments.get("mutation_policy") or "allowed"),
        setup_mutations=tuple(
            item
            for item in arguments.get("setup_mutations", ())
            if isinstance(item, str) and item.strip()
        ),
        allow_setup_mutations=bool(arguments.get("allow_setup_mutations", False)),
        mcp_startup_diagnostic=mcp_startup_diagnostic,
        preflight_surface="live_mcp",
    )


def _handle_task_current(arguments: JsonObject, context: McpServerContext) -> object | None:
    if arguments.get("story_loop_status_checked") is not True:
        raise McpDispatchError(
            "story_loop_status_required",
            story_loop_status_required_message("codex_supervisor.task_current"),
        )
    snapshot = _open_store(context).read_queue_snapshot()
    return select_next_executable_afk_task(snapshot.tasks, snapshot.worker_runs)


def _handle_task_next_afk(arguments: JsonObject, context: McpServerContext) -> object | None:
    if arguments.get("story_loop_status_checked") is not True:
        raise McpDispatchError(
            "story_loop_status_required",
            story_loop_status_required_message("codex_supervisor.task_next_afk"),
        )
    snapshot = _open_store(context).read_queue_snapshot()
    return select_next_executable_afk_task(snapshot.tasks, snapshot.worker_runs)


def _handle_task_show(arguments: JsonObject, context: McpServerContext) -> object:
    task_id = _required_string(arguments, "task_id")
    task = _find_task(_open_store(context), task_id)
    if task is None:
        raise McpDispatchError("not_found", f"No supervisor task found: {task_id}")
    return task


def _handle_worker_run_list(arguments: JsonObject, context: McpServerContext) -> tuple[object, ...]:
    task_id = _optional_string(arguments.get("task_id"))
    return _open_store(context).list_worker_runs(task_id=task_id)


def _handle_worker_run_show(arguments: JsonObject, context: McpServerContext) -> object:
    worker_run_id = _required_string(arguments, "worker_run_id")
    run = _find_worker_run(_open_store(context), worker_run_id)
    if run is None:
        raise McpDispatchError("not_found", f"No worker run found: {worker_run_id}")
    return run


def _handle_worker_run_event_list(
    arguments: JsonObject,
    context: McpServerContext,
) -> tuple[object, ...]:
    worker_run_id = _optional_string(arguments.get("worker_run_id"))
    return _open_store(context).list_worker_run_events(worker_run_id=worker_run_id)


def _handle_worker_result_list(
    arguments: JsonObject,
    context: McpServerContext,
) -> tuple[object, ...]:
    _reject_unexpected_arguments(arguments)
    return _open_store(context).list_worker_results()


def _handle_worker_result_show(arguments: JsonObject, context: McpServerContext) -> object:
    result_id = _required_string(arguments, "result_id")
    result = next(
        (
            candidate
            for candidate in _open_store(context).list_worker_results()
            if candidate.result_id == result_id
        ),
        None,
    )
    if result is None:
        raise McpDispatchError("not_found", f"No worker result found: {result_id}")
    return result


def _handle_plan_upsert(arguments: JsonObject, context: McpServerContext) -> object:
    store = _open_write_store(context)
    record = PlanRecord(
        plan_id=_required_string(arguments, "plan_id"),
        slug=_required_string(arguments, "slug"),
        title=_required_string(arguments, "title"),
        goal=_required_string(arguments, "goal"),
        status=_required_string(arguments, "status"),
        priority=_optional_integer(arguments.get("priority"), default=0),
        owner_agent=_optional_string(arguments.get("owner_agent")),
        non_goals=_optional_object(arguments.get("non_goals")),
        context=_optional_object(arguments.get("context")),
        superseded_by_plan_id=_optional_string(arguments.get("superseded_by_plan_id")),
    )
    store.upsert_plan(record)
    return _find_plan(store, record.plan_id) or record


def _handle_plan_status(arguments: JsonObject, context: McpServerContext) -> object:
    store = _open_write_store(context)
    plan_id = _required_string(arguments, "plan_id")
    store.update_plan_status(
        plan_id,
        _required_string(arguments, "status"),
        superseded_by_plan_id=_optional_string(arguments.get("superseded_by_plan_id")),
    )
    plan = _find_plan(store, plan_id)
    if plan is None:
        raise McpDispatchError("not_found", f"No plan found: {plan_id}")
    return plan


def _handle_milestone_upsert(arguments: JsonObject, context: McpServerContext) -> object:
    store = _open_write_store(context)
    record = PlanMilestoneRecord(
        milestone_id=_required_string(arguments, "milestone_id"),
        plan_id=_required_string(arguments, "plan_id"),
        title=_required_string(arguments, "title"),
        status=_required_string(arguments, "status"),
        sort_order=_optional_integer(arguments.get("sort_order"), default=0),
        details=_optional_object(arguments.get("details")),
    )
    store.upsert_plan_milestone(record)
    return record


def _handle_milestone_status(arguments: JsonObject, context: McpServerContext) -> object:
    store = _open_write_store(context)
    milestone_id = _required_string(arguments, "milestone_id")
    store.update_plan_milestone_status(milestone_id, _required_string(arguments, "status"))
    return _find_milestone(store, milestone_id)


def _handle_criterion_upsert(arguments: JsonObject, context: McpServerContext) -> object:
    store = _open_write_store(context)
    record = PlanAcceptanceCriterionRecord(
        criterion_id=_required_string(arguments, "criterion_id"),
        plan_id=_required_string(arguments, "plan_id"),
        description=_required_string(arguments, "description"),
        status=_required_string(arguments, "status"),
        verification_command=_optional_string(arguments.get("verification_command")),
    )
    store.upsert_plan_acceptance_criterion(record)
    return record


def _handle_criterion_status(arguments: JsonObject, context: McpServerContext) -> object:
    store = _open_write_store(context)
    criterion_id = _required_string(arguments, "criterion_id")
    store.update_plan_acceptance_criterion_status(
        criterion_id,
        _required_string(arguments, "status"),
    )
    return _find_criterion(store, criterion_id)


def _handle_decision_add(arguments: JsonObject, context: McpServerContext) -> object:
    store = _open_write_store(context)
    record = PlanDecisionRecord(
        decision_id=_required_string(arguments, "decision_id"),
        plan_id=_required_string(arguments, "plan_id"),
        decision=_required_string(arguments, "decision"),
        rationale=_required_string(arguments, "rationale"),
        alternatives_considered=_optional_string(arguments.get("alternatives_considered")),
        consequences=_optional_string(arguments.get("consequences")),
    )
    store.add_plan_decision(record)
    return record


def _handle_task_upsert(arguments: JsonObject, context: McpServerContext) -> object:
    store = _open_write_store(context)
    task_id = _required_string(arguments, "task_id")
    existing = _find_task(store, task_id)
    record = SupervisorTaskRecord(
        task_id=task_id,
        plan_id=_required_string_or_existing(arguments, "plan_id", existing, "plan_id"),
        title=_required_string_or_existing(arguments, "title", existing, "title"),
        goal=_required_string_or_existing(arguments, "goal", existing, "goal"),
        task_type=_required_string_or_existing(
            arguments,
            "task_type",
            existing,
            "task_type",
            default="AFK",
        ),
        status=_required_string_or_existing(
            arguments,
            "status",
            existing,
            "status",
            default="pending",
        ),
        scope=_object_or_existing(arguments, "scope", existing, "scope"),
        out_of_scope=_object_or_existing(arguments, "out_of_scope", existing, "out_of_scope"),
        acceptance_criteria=_string_array_or_existing(
            arguments,
            "acceptance_criteria",
            existing,
            "acceptance_criteria",
        ),
        verification_commands=_string_array_or_existing(
            arguments,
            "verification_commands",
            existing,
            "verification_commands",
        ),
        allowed_paths=_string_array_or_existing(
            arguments,
            "allowed_paths",
            existing,
            "allowed_paths",
        ),
        blocked_by=_string_array_or_existing(arguments, "blocked_by", existing, "blocked_by"),
        worker_backend=_required_string_or_existing(
            arguments,
            "worker_backend",
            existing,
            "worker_backend",
            default="codex_exec",
        ),
        review_required=_bool_or_existing(
            arguments,
            "review_required",
            existing,
            "review_required",
            default=True,
        ),
    )
    store.upsert_supervisor_task(record, validate_current_queue_contract=True)
    return _find_task(store, task_id) or record


def _handle_task_status(arguments: JsonObject, context: McpServerContext) -> object:
    store = _open_write_store(context)
    task_id = _required_string(arguments, "task_id")
    store.update_supervisor_task_status(task_id, _required_string(arguments, "status"))
    task = _find_task(store, task_id)
    if task is None:
        raise McpDispatchError("not_found", f"No supervisor task found: {task_id}")
    return task


def _handle_task_claim(arguments: JsonObject, context: McpServerContext) -> object:
    claim = _open_write_store(context).claim_next_ready_afk_task(
        worker_run_id=_required_string(arguments, "worker_run_id"),
        backend=_optional_string(arguments.get("backend")) or "codex_exec",
        task_id=_optional_string(arguments.get("task_id")),
        status=_optional_string(arguments.get("status")) or "running",
        worktree_path=_optional_string(arguments.get("worktree_path")),
        prompt_path=_optional_string(arguments.get("prompt_path")),
        jsonl_path=_optional_string(arguments.get("jsonl_path")),
        metadata=_optional_object(arguments.get("metadata")),
    )
    if claim is None:
        raise McpDispatchError("claim_conflict", "No matching ready AFK task could be claimed.")
    return claim


def _handle_task_compile(arguments: JsonObject, context: McpServerContext) -> object:
    store = _open_write_store(context) if bool(arguments.get("apply")) else _open_store(context)
    report = compile_tasks_from_plan(
        store,
        plan_id=_required_string(arguments, "plan_id"),
        allowed_paths=tuple(_optional_string_array(arguments.get("allowed_paths"))),
        verification_commands=tuple(_optional_string_array(arguments.get("verification_commands"))),
        status=_optional_string(arguments.get("status")) or "pending",
        worker_backend=_optional_string(arguments.get("worker_backend")) or "codex_exec",
        review_required=bool(arguments.get("review_required", True)),
    )
    if bool(arguments.get("apply")):
        report = apply_compiled_tasks(store, report)
    return report


def _handle_progress_add(arguments: JsonObject, context: McpServerContext) -> object:
    store = _open_write_store(context)
    record = PlanProgressRecord(
        progress_id=_required_string(arguments, "progress_id"),
        plan_id=_required_string(arguments, "plan_id"),
        event_type=_required_string(arguments, "event_type"),
        summary=_required_string(arguments, "summary"),
        details=_optional_string(arguments.get("details")),
        linked_artifact_id=_optional_string(arguments.get("linked_artifact_id")),
    )
    store.add_plan_progress(record)
    return record


def _handle_artifact_link_add(arguments: JsonObject, context: McpServerContext) -> object:
    store = _open_write_store(context)
    record = PlanArtifactLinkRecord(
        plan_id=_required_string(arguments, "plan_id"),
        artifact_id=_required_string(arguments, "artifact_id"),
        relationship=_required_string(arguments, "relationship"),
    )
    store.add_plan_artifact_link(record)
    return record


def _handle_story_loop_record(arguments: JsonObject, context: McpServerContext) -> object:
    return record_story_loop_progress(
        _open_write_store(context),
        progress_id=_required_string(arguments, "progress_id"),
        plan_id=_required_string(arguments, "plan_id"),
        event_type=_optional_string(arguments.get("event_type")) or "story-loop-iteration",
        summary=_required_string(arguments, "summary"),
        details=_optional_string(arguments.get("details")),
        artifact_ids=tuple(_optional_string_array(arguments.get("artifact_ids"))),
        artifact_relationship=(
            _optional_string(arguments.get("artifact_relationship")) or "story-loop-evidence"
        ),
        task_id=_optional_string(arguments.get("task_id")),
        worker_run_id=_optional_string(arguments.get("worker_run_id")),
        linked_artifact_id=_optional_string(arguments.get("linked_artifact_id")),
    )


def _handle_worker_run_upsert(arguments: JsonObject, context: McpServerContext) -> object:
    store = _open_write_store(context)
    worker_run_id = _required_string(arguments, "worker_run_id")
    existing = _find_worker_run(store, worker_run_id)
    record = WorkerRunRecord(
        worker_run_id=worker_run_id,
        task_id=_required_string_or_existing(arguments, "task_id", existing, "task_id"),
        backend=_required_string_or_existing(
            arguments,
            "backend",
            existing,
            "backend",
            default="codex_exec",
        ),
        status=_required_string_or_existing(
            arguments,
            "status",
            existing,
            "status",
            default="queued",
        ),
        worktree_path=_string_or_existing(arguments, "worktree_path", existing, "worktree_path"),
        prompt_path=_string_or_existing(arguments, "prompt_path", existing, "prompt_path"),
        jsonl_path=_string_or_existing(arguments, "jsonl_path", existing, "jsonl_path"),
        result_path=_string_or_existing(arguments, "result_path", existing, "result_path"),
        result_id=_string_or_existing(arguments, "result_id", existing, "result_id"),
        started_at=_string_or_existing(arguments, "started_at", existing, "started_at"),
        completed_at=_string_or_existing(arguments, "completed_at", existing, "completed_at"),
        failure_class=_string_or_existing(
            arguments,
            "failure_class",
            existing,
            "failure_class",
        ),
        metadata=_object_or_existing(arguments, "metadata", existing, "metadata"),
    )
    store.upsert_worker_run(record)
    return _find_worker_run(store, worker_run_id) or record


def _handle_worker_run_status(arguments: JsonObject, context: McpServerContext) -> object:
    store = _open_write_store(context)
    worker_run_id = _required_string(arguments, "worker_run_id")
    store.update_worker_run_status(
        worker_run_id,
        _required_string(arguments, "status"),
        failure_class=_optional_string(arguments.get("failure_class")),
        completed_at=_optional_string(arguments.get("completed_at")),
        result_path=_optional_string(arguments.get("result_path")),
        result_id=_optional_string(arguments.get("result_id")),
    )
    run = _find_worker_run(store, worker_run_id)
    if run is None:
        raise McpDispatchError("not_found", f"No worker run found: {worker_run_id}")
    return run


def _handle_worker_result_ingest(arguments: JsonObject, context: McpServerContext) -> object:
    return ingest_worker_result_path(
        _open_write_store(context),
        _required_string(arguments, "worker_run_id"),
        _required_string(arguments, "result_path"),
    )


def _handle_story_loop_start(arguments: JsonObject, context: McpServerContext) -> object:
    planning_path, repo_root = _story_loop_paths_context(arguments, context)
    return start_story_loop_run_async(
        planning_path=planning_path,
        repo_root=repo_root,
        worker_run_id=_required_string(arguments, "worker_run_id"),
        result_schema_path=_optional_string(arguments.get("result_schema_path")),
        sandbox_mode=_optional_string(arguments.get("sandbox_mode")) or "workspace-write",
        approval_policy=_optional_string(arguments.get("approval_policy")) or "never",
        codex_executable=_optional_codex_executable(arguments),
        codex_home=_optional_string(arguments.get("codex_home")),
        codex_config_path=_optional_string(arguments.get("codex_config_path")),
        model=_optional_string(arguments.get("model")),
        reasoning_effort=_optional_string(arguments.get("reasoning_effort")),
        service_tier=_optional_string(arguments.get("service_tier")),
        native_goal_mode=bool(arguments.get("native_goal_mode", False)),
        ignore_user_config=bool(arguments.get("ignore_user_config", False)),
        allow_degraded_jsonl=bool(arguments.get("allow_degraded_jsonl", False)),
        environment=_string_object(arguments.get("environment")),
    )


def _handle_story_loop_poll(arguments: JsonObject, context: McpServerContext) -> object:
    planning_path, repo_root = _story_loop_paths_context(arguments, context)
    return poll_story_loop_run_async(
        planning_path=planning_path,
        repo_root=repo_root,
        worker_run_id=_required_string(arguments, "worker_run_id"),
        controller_pid=_optional_integer_or_none(arguments.get("controller_pid")),
        max_events=_optional_integer(arguments.get("max_events"), default=5),
    )


def _handle_story_loop_run_once(arguments: JsonObject, context: McpServerContext) -> object:
    store, repo_root = _story_loop_execution_context(arguments, context)
    return run_live_story_loop_once(
        store,
        repo_root=repo_root,
        worker_run_id=_required_string(arguments, "worker_run_id"),
        sandbox_mode=_optional_string(arguments.get("sandbox_mode")) or "workspace-write",
        approval_policy=_optional_string(arguments.get("approval_policy")) or "never",
        codex_executable=_optional_codex_executable(arguments),
        codex_home=_optional_string(arguments.get("codex_home")),
        codex_config_path=_optional_string(arguments.get("codex_config_path")),
        model=_optional_string(arguments.get("model")),
        reasoning_effort=_optional_string(arguments.get("reasoning_effort")),
        service_tier=_optional_string(arguments.get("service_tier")),
        native_goal_mode=bool(arguments.get("native_goal_mode", False)),
        ignore_user_config=bool(arguments.get("ignore_user_config", False)),
        allow_degraded_jsonl=bool(arguments.get("allow_degraded_jsonl", False)),
        environment=_string_object(arguments.get("environment")),
    )


def _handle_story_loop_advance(arguments: JsonObject, context: McpServerContext) -> object:
    store, repo_root = _story_loop_execution_context(arguments, context)
    return advance_story_loop_once(
        store,
        repo_root=repo_root,
        worker_run_id=_required_string(arguments, "worker_run_id"),
        sandbox_mode=_optional_string(arguments.get("sandbox_mode")) or "workspace-write",
        approval_policy=_optional_string(arguments.get("approval_policy")) or "never",
        codex_executable=_optional_codex_executable(arguments),
        codex_home=_optional_string(arguments.get("codex_home")),
        codex_config_path=_optional_string(arguments.get("codex_config_path")),
        model=_optional_string(arguments.get("model")),
        reasoning_effort=_optional_string(arguments.get("reasoning_effort")),
        service_tier=_optional_string(arguments.get("service_tier")),
        native_goal_mode=bool(arguments.get("native_goal_mode", False)),
        ignore_user_config=bool(arguments.get("ignore_user_config", False)),
        allow_degraded_jsonl=bool(arguments.get("allow_degraded_jsonl", False)),
        environment=_string_object(arguments.get("environment")),
    )


def _handle_review_result_ingest(arguments: JsonObject, context: McpServerContext) -> object:
    store = _open_write_store(context)
    repo_root = context.resolved_repo_root()
    result_path = _repo_relative_path_argument(
        _required_string(arguments, "review_result_path"),
        repo_root=repo_root,
    )
    try:
        payload = json.loads((repo_root / result_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise McpDispatchError("review_result_read_failed", str(exc)) from exc
    review_result = validate_review_result_payload(payload)
    artifact_id = _optional_string(arguments.get("review_result_artifact_id")) or result_path
    plan_id = _required_string(arguments, "plan_id")
    repair_plan = None
    if bool(arguments.get("create_repair_tasks", False)):
        repair_plan = plan_repair_tasks_from_review_result(
            store,
            plan_id=plan_id,
            review_result=review_result,
            source_task_id=_optional_string(arguments.get("source_task_id")),
            task_id_prefix=(
                _optional_string(arguments.get("repair_task_id_prefix")) or "task-review-repair"
            ),
            verification_commands=DEFAULT_REPAIR_VERIFICATION_COMMANDS,
        )
    persistence_record = record_review_result(
        store,
        plan_id=plan_id,
        progress_id=_required_string(arguments, "progress_id"),
        review_result=review_result,
        review_result_artifact_id=artifact_id,
        review_artifact_ids=tuple(_optional_string_array(arguments.get("review_artifact_ids"))),
    )
    repair_result = apply_repair_task_plan(store, repair_plan) if repair_plan is not None else None
    return {
        "review_result": review_result,
        "persistence": persistence_record,
        "repair_tasks": repair_result,
    }


def _open_store(context: McpServerContext) -> PlanningSQLiteStore:
    return open_existing_planning_database(context.resolved_planning_path(), read_only=True)


def _open_write_store(context: McpServerContext) -> PlanningSQLiteStore:
    return open_existing_planning_database(context.resolved_planning_path(), read_only=False)


def _story_loop_execution_context(
    arguments: JsonObject,
    context: McpServerContext,
) -> tuple[PlanningSQLiteStore, Path]:
    planning_path, repo_root = _story_loop_paths_context(arguments, context)
    return open_existing_planning_database(planning_path, read_only=False), repo_root


def _story_loop_paths_context(
    arguments: JsonObject,
    context: McpServerContext,
) -> tuple[Path, Path]:
    repo_root = (
        _optional_path_argument(
            arguments.get("repo_root"),
            base=context.resolved_repo_root(),
            field_name="repo_root",
        )
        or context.resolved_repo_root()
    )
    planning_path = (
        _optional_path_argument(
            arguments.get("planning_path"),
            base=repo_root,
            field_name="planning_path",
        )
        or context.resolved_planning_path()
    )
    return planning_path, repo_root


def _require_plan_visible(
    store: PlanningSQLiteStore,
    *,
    plan_id: str,
    include_all: bool,
) -> None:
    plan = next(
        (candidate for candidate in store.list_plans() if candidate.plan_id == plan_id),
        None,
    )
    if plan is None:
        raise McpDispatchError("not_found", f"No plan found: {plan_id}")
    if not include_all and plan.status not in {"active", "blocked"}:
        raise McpDispatchError(
            "historical_plan",
            f"Plan {plan_id} is {plan.status}; pass all=true to inspect historical plans.",
        )


def _find_plan(store: PlanningSQLiteStore, plan_id: str) -> PlanRecord | None:
    return next((plan for plan in store.list_plans() if plan.plan_id == plan_id), None)


def _find_milestone(
    store: PlanningSQLiteStore,
    milestone_id: str,
) -> PlanMilestoneRecord | None:
    return next(
        (
            milestone
            for milestone in store.list_plan_milestones()
            if milestone.milestone_id == milestone_id
        ),
        None,
    )


def _find_criterion(
    store: PlanningSQLiteStore,
    criterion_id: str,
) -> PlanAcceptanceCriterionRecord | None:
    return next(
        (
            criterion
            for criterion in store.list_plan_acceptance_criteria()
            if criterion.criterion_id == criterion_id
        ),
        None,
    )


def _find_task(
    store: PlanningSQLiteStore,
    task_id: str,
) -> SupervisorTaskSummaryRecord | None:
    return next((task for task in store.list_supervisor_tasks() if task.task_id == task_id), None)


def _find_worker_run(
    store: PlanningSQLiteStore,
    worker_run_id: str,
) -> WorkerRunRecord | None:
    return next(
        (run for run in store.list_worker_runs() if run.worker_run_id == worker_run_id),
        None,
    )


def _validate_arguments(definition: McpToolDefinition, arguments: object | None) -> JsonObject:
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise McpDispatchError("validation_error", "MCP tool arguments must be an object.")
    schema = definition.input_schema
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        properties = {}
    required = schema.get("required", ())
    required_names = tuple(str(name) for name in required) if isinstance(required, list) else ()
    if schema.get("additionalProperties") is False:
        unknown = sorted(set(arguments) - set(properties))
        if unknown:
            raise McpDispatchError(
                "validation_error",
                f"Unexpected MCP tool argument(s): {', '.join(unknown)}",
            )
    for required_name in required_names:
        property_schema = properties.get(required_name)
        if required_name not in arguments:
            raise McpDispatchError(
                "validation_error",
                f"Missing required MCP tool argument: {required_name}",
            )
        if (
            isinstance(property_schema, dict)
            and property_schema.get("type") == "string"
            and _optional_string(arguments.get(required_name)) is None
        ):
            raise McpDispatchError(
                "validation_error",
                f"Missing required MCP tool argument: {required_name}",
            )
    for key, value in arguments.items():
        property_schema = properties.get(key)
        if isinstance(property_schema, dict):
            _validate_argument_type(key, value, property_schema)
    return dict(arguments)


def _validate_argument_type(key: str, value: object, schema: Mapping[str, object]) -> None:
    expected_type = schema.get("type")
    if expected_type == "string" and not isinstance(value, str):
        raise McpDispatchError("validation_error", f"{key} must be a string.")
    if expected_type == "boolean" and not isinstance(value, bool):
        raise McpDispatchError("validation_error", f"{key} must be a boolean.")
    if expected_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        raise McpDispatchError("validation_error", f"{key} must be an integer.")
    if expected_type == "object" and not isinstance(value, dict):
        raise McpDispatchError("validation_error", f"{key} must be an object.")
    if expected_type == "array":
        if not isinstance(value, list):
            raise McpDispatchError("validation_error", f"{key} must be an array.")
        item_schema = schema.get("items")
        if (
            isinstance(item_schema, dict)
            and item_schema.get("type") == "string"
            and not all(isinstance(item, str) and item.strip() for item in value)
        ):
            raise McpDispatchError(
                "validation_error",
                f"{key} must contain only nonblank strings.",
            )
    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        allowed = ", ".join(str(item) for item in enum)
        raise McpDispatchError("validation_error", f"{key} must be one of: {allowed}.")


def _reject_unexpected_arguments(arguments: JsonObject) -> None:
    if arguments:
        names = ", ".join(sorted(arguments))
        raise McpDispatchError("validation_error", f"Unexpected MCP tool argument(s): {names}")


def _required_string(arguments: JsonObject, key: str) -> str:
    value = _optional_string(arguments.get(key))
    if value is None:
        raise McpDispatchError("validation_error", f"Missing required MCP tool argument: {key}")
    return value


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _optional_codex_executable(arguments: JsonObject) -> str | None:
    return _optional_string(arguments.get("codex_executable")) or _optional_string(
        arguments.get("codex_bin")
    )


def _optional_integer(value: object, *, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


def _optional_integer_or_none(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _optional_object(value: object) -> JsonObject:
    return dict(value) if isinstance(value, dict) else {}


def _optional_string_array(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def _string_object(value: object) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise McpDispatchError("validation_error", "environment must be an object.")
    values: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise McpDispatchError(
                "validation_error",
                "environment must contain only string keys and values.",
            )
        values[key] = item
    return values


def _string_or_existing(
    arguments: JsonObject,
    key: str,
    existing: object | None,
    existing_attribute: str,
    *,
    default: str | None = None,
) -> str | None:
    value = _optional_string(arguments.get(key))
    if value is not None:
        return value
    if existing is not None:
        existing_value = getattr(existing, existing_attribute)
        return str(existing_value) if existing_value is not None else None
    if default is not None:
        return default
    raise McpDispatchError("validation_error", f"Missing required MCP tool argument: {key}")


def _required_string_or_existing(
    arguments: JsonObject,
    key: str,
    existing: object | None,
    existing_attribute: str,
    *,
    default: str | None = None,
) -> str:
    value = _string_or_existing(
        arguments,
        key,
        existing,
        existing_attribute,
        default=default,
    )
    if value is None:
        raise McpDispatchError("validation_error", f"Missing required MCP tool argument: {key}")
    return value


def _object_or_existing(
    arguments: JsonObject,
    key: str,
    existing: object | None,
    existing_attribute: str,
) -> JsonObject:
    if key in arguments:
        return _optional_object(arguments.get(key))
    if existing is not None:
        value = getattr(existing, existing_attribute)
        return dict(value) if isinstance(value, dict) else {}
    return {}


def _string_array_or_existing(
    arguments: JsonObject,
    key: str,
    existing: object | None,
    existing_attribute: str,
) -> list[str]:
    if key in arguments:
        return list(_optional_string_array(arguments.get(key)))
    if existing is not None:
        return list(getattr(existing, existing_attribute))
    return []


def _bool_or_existing(
    arguments: JsonObject,
    key: str,
    existing: object | None,
    existing_attribute: str,
    *,
    default: bool,
) -> bool:
    if key in arguments:
        value = arguments.get(key)
        if isinstance(value, bool):
            return value
    if existing is not None:
        return bool(getattr(existing, existing_attribute))
    return default


def _project_root_from_argument(value: object, context: McpServerContext) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise McpDispatchError("validation_error", "root_paths entries must be nonblank strings.")
    path = Path(value)
    return path if path.is_absolute() else context.resolved_repo_root() / path


def _optional_path_argument(
    value: object,
    *,
    base: Path,
    field_name: str,
) -> Path | None:
    if value is None:
        return None
    string_value = _optional_string(value)
    if string_value is None:
        raise McpDispatchError("validation_error", f"{field_name} must be a nonblank string.")
    path = Path(string_value)
    if not path.is_absolute():
        path = base / path
    return path.resolve(strict=False)


def _require_project_roots_in_scope(
    roots: tuple[Path, ...],
    allowed_roots: tuple[Path, ...],
) -> None:
    resolved_allowed = tuple(root.resolve() for root in allowed_roots)
    for root in roots:
        resolved_root = root.resolve()
        root_is_allowed = any(
            _is_relative_to(resolved_root, allowed_root) for allowed_root in resolved_allowed
        )
        if not root_is_allowed:
            raise McpDispatchError(
                "out_of_scope_root",
                "project_list root_paths must stay within configured project roots.",
            )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _redacted_project_entry(entry: object) -> JsonObject:
    payload = _to_jsonable(entry)
    if not isinstance(payload, dict):
        return {}
    project_id = str(payload.get("project_id") or "project")
    raw_root = str(payload.get("root_path") or "")
    redacted_root = f"<project-root:{project_id}>"
    payload["root_path"] = redacted_root
    replacements = tuple(
        (value, redacted_root)
        for value in {
            raw_root,
            raw_root.replace("\\", "/"),
            str(Path(raw_root)) if raw_root else "",
        }
        if value
    )
    redacted = _replace_strings(payload, replacements)
    return redacted if isinstance(redacted, dict) else {}


def _replace_strings(value: object, replacements: tuple[tuple[str, str], ...]) -> Any:
    if isinstance(value, str):
        updated = value
        for needle, replacement in replacements:
            updated = updated.replace(needle, replacement)
        return updated
    if isinstance(value, list):
        return [_replace_strings(item, replacements) for item in value]
    if isinstance(value, dict):
        return {str(key): _replace_strings(item, replacements) for key, item in value.items()}
    return value


def _repo_relative_path_argument(value: str, *, repo_root: Path) -> str:
    windows_path = PureWindowsPath(value)
    if windows_path.drive or value.startswith(("/", "\\")):
        raise McpDispatchError("validation_error", "review_result_path must be repo-relative.")
    normalized = windows_path.as_posix()
    if any(part == ".." for part in normalized.split("/")):
        raise McpDispatchError("validation_error", "review_result_path must stay inside the repo.")
    try:
        resolved_path = (repo_root / normalized).resolve()
        relative = resolved_path.relative_to(repo_root.resolve()).as_posix()
    except (OSError, ValueError) as exc:
        raise McpDispatchError(
            "validation_error",
            "review_result_path must stay inside the repo.",
        ) from exc
    return relative


def _error_result(tool_name: str, code: str, message: str) -> JsonObject:
    return {
        "ok": False,
        "tool": tool_name,
        "error": {
            "code": code,
            "message": message,
        },
    }


def _to_jsonable(value: object) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _to_jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple | list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    return value


TOOL_DEFINITIONS: dict[str, McpToolDefinition] = {
    "codex_supervisor.project_list": McpToolDefinition(
        name="codex_supervisor.project_list",
        description="List supervised project roots and adapter facts.",
        input_schema={
            "type": "object",
            "properties": {
                "root_paths": {"type": "array", "items": {"type": "string"}},
                "trust_policy": {"type": "string"},
            },
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.story_loop_status": McpToolDefinition(
        name="codex_supervisor.story_loop_status",
        description="Report Story Loop queue state from canonical planning state.",
        input_schema={
            "type": "object",
            "properties": {
                "all": {"type": "boolean"},
                "plan_id": {"type": "string"},
            },
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.plan_list": McpToolDefinition(
        name="codex_supervisor.plan_list",
        description="List planning records, optionally filtered by plan status.",
        input_schema={
            "type": "object",
            "properties": {"status": {"type": "string", "enum": sorted(PLAN_STATUSES)}},
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.runtime_preflight": McpToolDefinition(
        name="codex_supervisor.runtime_preflight",
        description=(
            "Desktop full-AFK canary and runtime preflight: build a fail-closed "
            "codex_supervisor.runtime_preflight execution-mode ledger and verify the live "
            "Supervisor MCP tool surface."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "full_afk": {"type": "boolean"},
                "plugin_invocation": {"type": "boolean"},
                "plugin_full_afk": {"type": "boolean"},
                "supervisor_backend": {
                    "type": "string",
                    "enum": ["mcp", "cli", "unavailable", "skill_only"],
                },
                "mcp_tools": {"type": "array", "items": {"type": "string"}},
                "cli_available": {"type": "boolean"},
                "worker_execution": {
                    "type": "string",
                    "enum": ["codex_exec", "current_thread", "blocked", "manual"],
                },
                "native_goal_mode": {"type": "boolean"},
                "supervisor_task_id": {"type": "string"},
                "goal_contract_linked": {"type": "boolean"},
                "story_loop_status_checked": {"type": "boolean"},
                "task_current_requested": {"type": "boolean"},
                "task_next_afk_requested": {"type": "boolean"},
                "scaffold_tier": {
                    "type": "string",
                    "enum": ["supervisor_managed", "base", "prototype_light", "unknown"],
                },
                "database_mode": {
                    "type": "string",
                    "enum": ["persistent_mongodb", "memory_mongodb", "none", "unknown"],
                },
                "evidence_mode": {
                    "type": "string",
                    "enum": ["strict_jsonl", "degraded_jsonl", "missing"],
                },
                "mutation_policy": {"type": "string", "enum": ["allowed", "read_only"]},
                "setup_mutations": {"type": "array", "items": {"type": "string"}},
                "allow_setup_mutations": {"type": "boolean"},
                "mcp_startup_diagnostic": {"type": "string"},
            },
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.task_current": McpToolDefinition(
        name="codex_supervisor.task_current",
        description=(
            "Legacy alias for task_next_afk; return the next executable ready AFK task "
            "after story_loop_status."
        ),
        input_schema={
            "type": "object",
            "properties": {"story_loop_status_checked": {"type": "boolean"}},
            "required": ["story_loop_status_checked"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.task_next_afk": McpToolDefinition(
        name="codex_supervisor.task_next_afk",
        description="Return the next executable ready AFK task after story_loop_status.",
        input_schema={
            "type": "object",
            "properties": {"story_loop_status_checked": {"type": "boolean"}},
            "required": ["story_loop_status_checked"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.task_show": McpToolDefinition(
        name="codex_supervisor.task_show",
        description="Show one supervisor task by task_id.",
        input_schema={
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.worker_run_list": McpToolDefinition(
        name="codex_supervisor.worker_run_list",
        description="List worker runs, optionally filtered by task_id.",
        input_schema={
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.worker_run_show": McpToolDefinition(
        name="codex_supervisor.worker_run_show",
        description="Show one worker run by worker_run_id.",
        input_schema={
            "type": "object",
            "properties": {"worker_run_id": {"type": "string"}},
            "required": ["worker_run_id"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.worker_run_event_list": McpToolDefinition(
        name="codex_supervisor.worker_run_event_list",
        description="List append-only worker run events, optionally filtered by worker_run_id.",
        input_schema={
            "type": "object",
            "properties": {"worker_run_id": {"type": "string"}},
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.worker_result_list": McpToolDefinition(
        name="codex_supervisor.worker_result_list",
        description="List DB-backed worker result records.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    "codex_supervisor.worker_result_show": McpToolDefinition(
        name="codex_supervisor.worker_result_show",
        description="Show one DB-backed worker result by result_id.",
        input_schema={
            "type": "object",
            "properties": {"result_id": {"type": "string"}},
            "required": ["result_id"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.plan_upsert": McpToolDefinition(
        name="codex_supervisor.plan_upsert",
        description="Create or update one planning record.",
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "slug": {"type": "string"},
                "title": {"type": "string"},
                "goal": {"type": "string"},
                "status": {"type": "string", "enum": sorted(PLAN_STATUSES)},
                "priority": {"type": "integer"},
                "owner_agent": {"type": "string"},
                "non_goals": {"type": "object"},
                "context": {"type": "object"},
                "superseded_by_plan_id": {"type": "string"},
            },
            "required": ["plan_id", "slug", "title", "goal", "status"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.plan_status": McpToolDefinition(
        name="codex_supervisor.plan_status",
        description="Update one plan status.",
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "status": {"type": "string", "enum": sorted(PLAN_STATUSES)},
                "superseded_by_plan_id": {"type": "string"},
            },
            "required": ["plan_id", "status"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.milestone_upsert": McpToolDefinition(
        name="codex_supervisor.milestone_upsert",
        description="Create or update one plan milestone.",
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "milestone_id": {"type": "string"},
                "plan_id": {"type": "string"},
                "title": {"type": "string"},
                "status": {"type": "string", "enum": sorted(MILESTONE_STATUSES)},
                "sort_order": {"type": "integer"},
                "details": {"type": "object"},
            },
            "required": ["milestone_id", "plan_id", "title", "status"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.milestone_status": McpToolDefinition(
        name="codex_supervisor.milestone_status",
        description="Update one plan milestone status.",
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "milestone_id": {"type": "string"},
                "status": {"type": "string", "enum": sorted(MILESTONE_STATUSES)},
            },
            "required": ["milestone_id", "status"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.criterion_upsert": McpToolDefinition(
        name="codex_supervisor.criterion_upsert",
        description="Create or update one plan acceptance criterion.",
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "criterion_id": {"type": "string"},
                "plan_id": {"type": "string"},
                "description": {"type": "string"},
                "status": {"type": "string", "enum": sorted(CRITERION_STATUSES)},
                "verification_command": {"type": "string"},
            },
            "required": ["criterion_id", "plan_id", "description", "status"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.criterion_status": McpToolDefinition(
        name="codex_supervisor.criterion_status",
        description="Update one plan acceptance criterion status.",
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "criterion_id": {"type": "string"},
                "status": {"type": "string", "enum": sorted(CRITERION_STATUSES)},
            },
            "required": ["criterion_id", "status"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.decision_add": McpToolDefinition(
        name="codex_supervisor.decision_add",
        description="Record one plan decision.",
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "decision_id": {"type": "string"},
                "plan_id": {"type": "string"},
                "decision": {"type": "string"},
                "rationale": {"type": "string"},
                "alternatives_considered": {"type": "string"},
                "consequences": {"type": "string"},
            },
            "required": ["decision_id", "plan_id", "decision", "rationale"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.task_upsert": McpToolDefinition(
        name="codex_supervisor.task_upsert",
        description="Create or update one supervisor task.",
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "plan_id": {"type": "string"},
                "title": {"type": "string"},
                "goal": {"type": "string"},
                "task_type": {"type": "string", "enum": sorted(TASK_TYPES)},
                "status": {"type": "string", "enum": sorted(TASK_STATUSES)},
                "scope": {"type": "object"},
                "out_of_scope": {"type": "object"},
                "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
                "verification_commands": {"type": "array", "items": {"type": "string"}},
                "allowed_paths": {"type": "array", "items": {"type": "string"}},
                "blocked_by": {"type": "array", "items": {"type": "string"}},
                "worker_backend": {"type": "string"},
                "review_required": {"type": "boolean"},
            },
            "required": ["task_id", "plan_id", "title", "goal", "task_type", "status"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.task_status": McpToolDefinition(
        name="codex_supervisor.task_status",
        description="Update one supervisor task status.",
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "status": {"type": "string", "enum": sorted(TASK_STATUSES)},
            },
            "required": ["task_id", "status"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.task_claim": McpToolDefinition(
        name="codex_supervisor.task_claim",
        description="Atomically claim the current ready AFK task and create a worker run.",
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "worker_run_id": {"type": "string"},
                "task_id": {"type": "string"},
                "backend": {"type": "string"},
                "status": {"type": "string", "enum": sorted(CLAIM_WORKER_RUN_STATUSES)},
                "worktree_path": {"type": "string"},
                "prompt_path": {"type": "string"},
                "jsonl_path": {"type": "string"},
                "metadata": {"type": "object"},
            },
            "required": ["worker_run_id"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.task_compile": McpToolDefinition(
        name="codex_supervisor.task_compile",
        description="Compile open plan criteria or milestones into deterministic task drafts.",
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "allowed_paths": {"type": "array", "items": {"type": "string"}},
                "verification_commands": {"type": "array", "items": {"type": "string"}},
                "status": {"type": "string", "enum": sorted(TASK_STATUSES)},
                "worker_backend": {"type": "string"},
                "review_required": {"type": "boolean"},
                "apply": {"type": "boolean"},
            },
            "required": ["plan_id", "allowed_paths"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.progress_add": McpToolDefinition(
        name="codex_supervisor.progress_add",
        description="Record one plan progress event.",
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "progress_id": {"type": "string"},
                "plan_id": {"type": "string"},
                "event_type": {"type": "string"},
                "summary": {"type": "string"},
                "details": {"type": "string"},
                "linked_artifact_id": {"type": "string"},
            },
            "required": ["progress_id", "plan_id", "event_type", "summary"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.artifact_link_add": McpToolDefinition(
        name="codex_supervisor.artifact_link_add",
        description="Link one durable plan artifact.",
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "artifact_id": {"type": "string"},
                "relationship": {"type": "string"},
            },
            "required": ["plan_id", "artifact_id", "relationship"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.story_loop_record": McpToolDefinition(
        name="codex_supervisor.story_loop_record",
        description="Record one Story Loop progress event and artifact links.",
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "progress_id": {"type": "string"},
                "plan_id": {"type": "string"},
                "event_type": {"type": "string"},
                "summary": {"type": "string"},
                "details": {"type": "string"},
                "artifact_ids": {"type": "array", "items": {"type": "string"}},
                "artifact_relationship": {"type": "string"},
                "task_id": {"type": "string"},
                "worker_run_id": {"type": "string"},
                "linked_artifact_id": {"type": "string"},
            },
            "required": ["progress_id", "plan_id", "summary"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.worker_run_upsert": McpToolDefinition(
        name="codex_supervisor.worker_run_upsert",
        description="Create or update one worker run evidence record.",
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "worker_run_id": {"type": "string"},
                "task_id": {"type": "string"},
                "backend": {"type": "string"},
                "status": {"type": "string", "enum": sorted(WORKER_RUN_STATUSES)},
                "worktree_path": {"type": "string"},
                "prompt_path": {"type": "string"},
                "jsonl_path": {"type": "string"},
                "result_path": {"type": "string"},
                "result_id": {"type": "string"},
                "started_at": {"type": "string"},
                "completed_at": {"type": "string"},
                "failure_class": {"type": "string"},
                "metadata": {"type": "object"},
            },
            "required": ["worker_run_id", "task_id", "backend", "status"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.worker_run_status": McpToolDefinition(
        name="codex_supervisor.worker_run_status",
        description="Update one worker run status.",
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "worker_run_id": {"type": "string"},
                "status": {"type": "string", "enum": sorted(WORKER_RUN_STATUSES)},
                "failure_class": {"type": "string"},
                "completed_at": {"type": "string"},
                "result_path": {"type": "string"},
                "result_id": {"type": "string"},
            },
            "required": ["worker_run_id", "status"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.worker_result_ingest": McpToolDefinition(
        name="codex_supervisor.worker_result_ingest",
        description="Validate and ingest one Worker Result JSON for a worker run.",
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "worker_run_id": {"type": "string"},
                "result_path": {"type": "string"},
            },
            "required": ["worker_run_id", "result_path"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.story_loop_start": McpToolDefinition(
        name="codex_supervisor.story_loop_start",
        description=(
            "Start one ready AFK task through the live Story Loop controller and return "
            "immediately with poll metadata."
        ),
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "worker_run_id": {"type": "string"},
                "planning_path": {"type": "string"},
                "repo_root": {"type": "string"},
                "result_schema_path": {"type": "string"},
                "sandbox_mode": {"type": "string"},
                "approval_policy": {"type": "string"},
                "codex_executable": {"type": "string"},
                "codex_bin": {"type": "string"},
                "codex_home": {"type": "string"},
                "codex_config_path": {"type": "string"},
                "model": {"type": "string"},
                "reasoning_effort": {"type": "string"},
                "service_tier": {"type": "string"},
                "native_goal_mode": {"type": "boolean"},
                "ignore_user_config": {"type": "boolean"},
                "allow_degraded_jsonl": {"type": "boolean"},
                "environment": {"type": "object"},
            },
            "required": ["worker_run_id"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.story_loop_poll": McpToolDefinition(
        name="codex_supervisor.story_loop_poll",
        description="Poll one async Story Loop controller and worker run without relaunching it.",
        read_only=True,
        input_schema={
            "type": "object",
            "properties": {
                "worker_run_id": {"type": "string"},
                "planning_path": {"type": "string"},
                "repo_root": {"type": "string"},
                "controller_pid": {"type": "integer"},
                "max_events": {"type": "integer"},
            },
            "required": ["worker_run_id"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.story_loop_run_once": McpToolDefinition(
        name="codex_supervisor.story_loop_run_once",
        description="Run one ready AFK task through the production live Story Loop service.",
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "worker_run_id": {"type": "string"},
                "planning_path": {"type": "string"},
                "repo_root": {"type": "string"},
                "sandbox_mode": {"type": "string"},
                "approval_policy": {"type": "string"},
                "codex_executable": {"type": "string"},
                "codex_bin": {"type": "string"},
                "codex_home": {"type": "string"},
                "codex_config_path": {"type": "string"},
                "model": {"type": "string"},
                "reasoning_effort": {"type": "string"},
                "service_tier": {"type": "string"},
                "native_goal_mode": {"type": "boolean"},
                "ignore_user_config": {"type": "boolean"},
                "allow_degraded_jsonl": {"type": "boolean"},
                "environment": {"type": "object"},
            },
            "required": ["worker_run_id"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.story_loop_advance": McpToolDefinition(
        name="codex_supervisor.story_loop_advance",
        description="Advance the Story Loop state machine by exactly one transition.",
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "worker_run_id": {"type": "string"},
                "planning_path": {"type": "string"},
                "repo_root": {"type": "string"},
                "sandbox_mode": {"type": "string"},
                "approval_policy": {"type": "string"},
                "codex_executable": {"type": "string"},
                "codex_bin": {"type": "string"},
                "codex_home": {"type": "string"},
                "codex_config_path": {"type": "string"},
                "model": {"type": "string"},
                "reasoning_effort": {"type": "string"},
                "service_tier": {"type": "string"},
                "native_goal_mode": {"type": "boolean"},
                "ignore_user_config": {"type": "boolean"},
                "allow_degraded_jsonl": {"type": "boolean"},
                "environment": {"type": "object"},
            },
            "required": ["worker_run_id"],
            "additionalProperties": False,
        },
    ),
    "codex_supervisor.review_result_ingest": McpToolDefinition(
        name="codex_supervisor.review_result_ingest",
        description="Validate and persist one structured review result.",
        read_only=False,
        input_schema={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "progress_id": {"type": "string"},
                "review_result_path": {"type": "string"},
                "review_result_artifact_id": {"type": "string"},
                "review_artifact_ids": {"type": "array", "items": {"type": "string"}},
                "create_repair_tasks": {"type": "boolean"},
                "source_task_id": {"type": "string"},
                "repair_task_id_prefix": {"type": "string"},
            },
            "required": ["plan_id", "progress_id", "review_result_path"],
            "additionalProperties": False,
        },
    ),
}

TOOL_HANDLERS: dict[str, McpHandler] = {
    "codex_supervisor.project_list": _handle_project_list,
    "codex_supervisor.story_loop_status": _handle_story_loop_status,
    "codex_supervisor.plan_list": _handle_plan_list,
    "codex_supervisor.runtime_preflight": _handle_runtime_preflight,
    "codex_supervisor.task_current": _handle_task_current,
    "codex_supervisor.task_next_afk": _handle_task_next_afk,
    "codex_supervisor.task_show": _handle_task_show,
    "codex_supervisor.worker_run_list": _handle_worker_run_list,
    "codex_supervisor.worker_run_show": _handle_worker_run_show,
    "codex_supervisor.worker_run_event_list": _handle_worker_run_event_list,
    "codex_supervisor.worker_result_list": _handle_worker_result_list,
    "codex_supervisor.worker_result_show": _handle_worker_result_show,
    "codex_supervisor.plan_upsert": _handle_plan_upsert,
    "codex_supervisor.plan_status": _handle_plan_status,
    "codex_supervisor.milestone_upsert": _handle_milestone_upsert,
    "codex_supervisor.milestone_status": _handle_milestone_status,
    "codex_supervisor.criterion_upsert": _handle_criterion_upsert,
    "codex_supervisor.criterion_status": _handle_criterion_status,
    "codex_supervisor.decision_add": _handle_decision_add,
    "codex_supervisor.task_upsert": _handle_task_upsert,
    "codex_supervisor.task_status": _handle_task_status,
    "codex_supervisor.task_claim": _handle_task_claim,
    "codex_supervisor.task_compile": _handle_task_compile,
    "codex_supervisor.progress_add": _handle_progress_add,
    "codex_supervisor.artifact_link_add": _handle_artifact_link_add,
    "codex_supervisor.story_loop_record": _handle_story_loop_record,
    "codex_supervisor.worker_run_upsert": _handle_worker_run_upsert,
    "codex_supervisor.worker_run_status": _handle_worker_run_status,
    "codex_supervisor.worker_result_ingest": _handle_worker_result_ingest,
    "codex_supervisor.story_loop_start": _handle_story_loop_start,
    "codex_supervisor.story_loop_poll": _handle_story_loop_poll,
    "codex_supervisor.story_loop_run_once": _handle_story_loop_run_once,
    "codex_supervisor.story_loop_advance": _handle_story_loop_advance,
    "codex_supervisor.review_result_ingest": _handle_review_result_ingest,
}
