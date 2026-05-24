"""Goal Contract rendering for supervisor tasks."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from codex_supervisor.planning import JsonObject, SupervisorTaskSummaryRecord

SOURCE_OF_TRUTH_DOCUMENTS = (
    "README.md",
    "AGENTS.md",
    "PLANS.md",
    "ARCHITECTURE.md",
    "CONTRACTS.md",
    "ROADMAP.md",
    "SOP.md",
    "TESTING.md",
    "DECISIONS.md",
    "ATTRIBUTIONS.md",
    "HANDOFF.md",
    "plans/planning.sqlite3",
)


@dataclass(frozen=True)
class GoalContract:
    """Worker-ready contract rendered from canonical planning state."""

    task_id: str
    plan_id: str
    title: str
    objective: str
    context_to_read_first: tuple[str, ...]
    in_scope: JsonObject
    out_of_scope: JsonObject
    constraints: JsonObject
    acceptance_criteria: tuple[str, ...]
    verification_surface: tuple[str, ...]
    stop_condition: str
    blocked_condition: str
    iteration_policy: str
    budget_or_status_limits: JsonObject
    record_updates: tuple[str, ...]
    execution_surface: JsonObject


def render_goal_contract(
    task: SupervisorTaskSummaryRecord,
    *,
    unresolved_blockers: tuple[str, ...] | None = None,
) -> GoalContract:
    """Render a deterministic Goal Contract from a supervisor task summary."""

    acceptance_criteria = _string_tuple(task.acceptance_criteria)
    verification = _string_tuple(task.verification_commands)
    allowed_paths = _string_tuple(task.allowed_paths)
    blocked_by = _string_tuple(
        task.blocked_by if unresolved_blockers is None else unresolved_blockers
    )

    in_scope = {
        "plan": {
            "plan_id": task.plan_id,
            "title": task.plan_title,
            "status": task.plan_status,
            "priority": task.plan_priority,
        },
        "task": {
            "task_id": task.task_id,
            "title": task.title,
            "status": task.status,
            "type": task.task_type,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        },
        "scope": _copy_json_object(task.scope),
    }
    constraints = {
        "allowed_paths": list(allowed_paths),
        "worker_backend": task.worker_backend,
        "review_required": task.review_required,
    }

    return GoalContract(
        task_id=task.task_id,
        plan_id=task.plan_id,
        title=task.title,
        objective=task.goal,
        context_to_read_first=SOURCE_OF_TRUTH_DOCUMENTS,
        in_scope=in_scope,
        out_of_scope=_copy_json_object(task.out_of_scope),
        constraints=constraints,
        acceptance_criteria=acceptance_criteria,
        verification_surface=verification,
        stop_condition=_stop_condition(task, acceptance_criteria, verification),
        blocked_condition=_blocked_condition(
            task,
            acceptance_criteria=acceptance_criteria,
            verification=verification,
            allowed_paths=allowed_paths,
            blocked_by=blocked_by,
        ),
        iteration_policy="Execute exactly one vertical slice, then record evidence and stop.",
        budget_or_status_limits={
            "plan_status_required": "active",
            "task_status_required": "ready",
            "task_type_required": "AFK",
            "allowed_paths": list(allowed_paths),
            "review_required": task.review_required,
        },
        record_updates=(
            "Record progress with story-loop-record or progress-add.",
            "Link changed artifacts with artifact-link-add or story-loop-record.",
            "Update task, criterion, milestone, and plan statuses through typed helpers or CLI.",
            "Report verification commands, changed artifacts, and residual risk in handoff.",
        ),
        execution_surface={
            "source_authority": {
                "durable_doctrine": "locked source-of-truth docs",
                "execution_order": "plans/planning.sqlite3",
                "handoff": "mutable snapshot; follow planning SQLite on current-task drift",
            },
            "native_goal_mode": {
                "authority": "Goal Contracts guide execution; planning SQLite remains canonical.",
                "preflight": [
                    "Check codex --version and intended CODEX_HOME.",
                    "If /goal is unavailable, ensure ${CODEX_HOME}/config.toml contains "
                    "[features] goals = true or run codex features enable goals only when "
                    "Goal Mode setup is in scope and writes to that Codex home are allowed. "
                    "In read-only mode, report the missing preflight and use the prompt-rendered "
                    "Goal Contract fallback. Restart or start a fresh Codex session only if the "
                    "running process does not pick up an allowed config change.",
                    "Do not write directly to ~/.codex/goals_1.sqlite.",
                ],
                "fallback": (
                    "If native Goals are unavailable, paste or render this Goal Contract into the "
                    "worker prompt."
                ),
            },
            "worker_backend": task.worker_backend,
        },
    )


def render_goal_contract_markdown(contract: GoalContract) -> str:
    """Render a Goal Contract as worker-readable Markdown."""

    sections = [
        "# Goal Contract",
        "",
        f"Task: `{contract.task_id}`",
        f"Plan: `{contract.plan_id}`",
        f"Title: {contract.title}",
        "",
        "## Objective",
        "",
        contract.objective,
        "",
        "## Context To Read First",
        "",
        _bullets(contract.context_to_read_first),
        "",
        "## In Scope",
        "",
        _json_block(contract.in_scope),
        "",
        "## Out Of Scope",
        "",
        _json_block(contract.out_of_scope),
        "",
        "## Constraints",
        "",
        _json_block(contract.constraints),
        "",
        "## Acceptance Criteria",
        "",
        _bullets(contract.acceptance_criteria),
        "",
        "## Verification Surface",
        "",
        _bullets(contract.verification_surface),
        "",
        "## Stop Condition",
        "",
        contract.stop_condition,
        "",
        "## Blocked Condition",
        "",
        contract.blocked_condition,
        "",
        "## Iteration Policy",
        "",
        contract.iteration_policy,
        "",
        "## Budget Or Status Limits",
        "",
        _json_block(contract.budget_or_status_limits),
        "",
        "## Record Updates",
        "",
        _bullets(contract.record_updates),
        "",
        "## Execution Surface",
        "",
        _json_block(contract.execution_surface),
    ]
    return "\n".join(sections)


def _stop_condition(
    task: SupervisorTaskSummaryRecord,
    acceptance_criteria: tuple[str, ...],
    verification: tuple[str, ...],
) -> str:
    criteria_text = "all acceptance criteria are satisfied"
    if not acceptance_criteria:
        criteria_text = "explicit acceptance criteria have been added and satisfied"
    verification_text = "all verification commands pass"
    if not verification:
        verification_text = "explicit verification commands have been added and pass"
    review_text = ""
    if task.review_required:
        review_text = " Required review findings must be fixed or explicitly accepted by HITL."
    return (
        f"Stop only when {criteria_text}, {verification_text}, planning SQLite records the "
        f"task progress/completion, and the handoff names changed artifacts and residual risk."
        f"{review_text}"
    )


def _blocked_condition(
    task: SupervisorTaskSummaryRecord,
    *,
    acceptance_criteria: tuple[str, ...],
    verification: tuple[str, ...],
    allowed_paths: tuple[str, ...],
    blocked_by: tuple[str, ...],
) -> str:
    blockers: list[str] = []
    if task.plan_status != "active":
        blockers.append(f"plan status is `{task.plan_status}`")
    if task.task_type != "AFK":
        blockers.append(f"task type is `{task.task_type}`")
    if task.status != "ready":
        blockers.append(f"task status is `{task.status}`")
    if blocked_by:
        blocked_dependencies = ", ".join(f"`{item}`" for item in blocked_by)
        blockers.append("blocked dependencies remain: " + blocked_dependencies)
    if not acceptance_criteria:
        blockers.append("acceptance criteria are missing")
    if not verification:
        blockers.append("verification commands are missing")
    if not allowed_paths:
        blockers.append("allowed paths are missing")

    if blockers:
        return (
            "Do not start autonomous implementation until these blockers are resolved: "
            + "; ".join(blockers)
            + "."
        )
    return (
        "Proceed unless the work requires out-of-scope edits, unsafe permissions, missing context, "
        "or a user decision; if blocked, record the blocker in planning SQLite and hand off to "
        "HITL."
    )


def _string_tuple(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(str(value) for value in values)


def _copy_json_object(value: JsonObject) -> JsonObject:
    return copy.deepcopy(value)


def _json_block(value: object) -> str:
    return "```json\n" + json.dumps(value, indent=2, sort_keys=True) + "\n```"


def _bullets(values: tuple[str, ...]) -> str:
    if not values:
        return "- none"
    return "\n".join(f"- {value}" for value in values)
