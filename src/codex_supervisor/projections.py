"""Read-only projections over the compact planning ledger."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from codex_supervisor.attempts import parse_json_string_array
from codex_supervisor.work_graph import (
    COMPLETION_EXCEPTION_DECISIONS,
    VALID_TASK_LINEAGE_RELATIONS,
    parse_lineage_json,
)

OPEN_TASK_STATUSES = frozenset({"ready", "running"})
NONTERMINAL_ATTEMPT_STATUSES = frozenset({"planned", "running"})
TERMINAL_ATTEMPT_STATUSES = frozenset({"succeeded", "failed", "blocked"})
RECOVERY_RELATIONS = frozenset({"retry_of", "repair_of"})
COVERAGE_RELATIONS = frozenset({"retry_of", "repair_of", "review_of"})
ASSURANCE_RANK = {"low": 1, "medium": 2, "high": 3}


@dataclass(frozen=True)
class LineageEdge:
    """Resolved lineage edge from one task to another."""

    source_task_id: str
    source_plan_id: str
    relation: str
    target_task_id: str
    target_plan_id: str | None
    cross_plan: bool


@dataclass(frozen=True)
class TerminalEvent:
    """Joined terminal attempt, evidence bundle, and acceptance decision."""

    task_id: str
    attempt_id: str
    attempt_status: str
    finished_at: str | None
    bundle_id: str
    evidence_summary: str
    decision_id: str
    acceptance_actor: str
    acceptance_result: str
    acceptance_rationale: str
    acceptance_evaluation: dict[str, object]
    accepted: bool
    assurance: str
    checks: tuple[str, ...]
    artifacts: tuple[str, ...]
    evidence_created_at: str
    decision_created_at: str


@dataclass(frozen=True)
class FinalProofProjection:
    """Final-proof coverage derived from accepted shipping-proof tasks."""

    state: str
    task_id: str | None
    proves_task_ids: tuple[str, ...]
    accepted_at: str | None
    covered_task_ids: tuple[str, ...]
    uncovered_task_ids: tuple[str, ...]
    stale_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectionIssue:
    """Structured projection issue for downstream ACP/integrity surfaces."""

    code: str
    severity: str
    subject_type: str
    subject_id: str
    message: str


@dataclass(frozen=True)
class TaskProjection:
    """Task-level read model with durable facts and derived meaning."""

    task_id: str
    plan_id: str
    status: str
    assurance: str
    lineage: tuple[LineageEdge, ...]
    active_attempt_id: str | None
    terminal_event: TerminalEvent | None
    accepted_terminal: bool
    rejected_terminal: bool
    is_final_proof_task: bool


@dataclass(frozen=True)
class PlanProjection:
    """Plan-level read model used for queue, ACP, and status sync."""

    plan_id: str
    stored_status: str
    projected_status: str
    open_task_ids: tuple[str, ...]
    unresolved_blocker_ids: tuple[str, ...]
    recovered_blocker_ids: tuple[str, ...]
    has_completion_exception: bool
    durable_completion: bool
    final_proof: FinalProofProjection
    task_projections: tuple[TaskProjection, ...]
    issues: tuple[ProjectionIssue, ...]

    @property
    def sync_target_status(self) -> str | None:
        """Return the terminal stored plan status implied for active-plan sync."""

        if self.projected_status in {"blocked", "done"}:
            return self.projected_status
        return None


def project_plan(connection: sqlite3.Connection, plan_id: str) -> PlanProjection:
    """Return the read-side projection for one plan."""

    plan = _one(
        connection.execute(
            "select plan_id, status from plans where plan_id = ?",
            (plan_id,),
        )
    )
    if plan is None:
        raise LookupError(f"unknown plan {plan_id!r}")

    all_tasks = _all_task_rows(connection)
    plan_tasks = tuple(row for row in all_tasks if row["plan_id"] == plan_id)
    task_by_id = {row["task_id"]: row for row in all_tasks}
    task_ids = tuple(row["task_id"] for row in plan_tasks)
    terminal_events = _current_terminal_events(connection, task_ids)
    active_attempts = _active_attempt_ids(connection, task_ids)
    edges_by_source = _lineage_edges(plan_tasks, task_by_id)
    children_by_target: dict[str, list[LineageEdge]] = defaultdict(list)
    for edges in edges_by_source.values():
        for edge in edges:
            children_by_target[edge.target_task_id].append(edge)

    task_projections = tuple(
        TaskProjection(
            task_id=row["task_id"],
            plan_id=row["plan_id"],
            status=row["status"],
            assurance=row["assurance"],
            lineage=tuple(edges_by_source.get(row["task_id"], ())),
            active_attempt_id=active_attempts.get(row["task_id"]),
            terminal_event=terminal_events.get(row["task_id"]),
            accepted_terminal=_is_accepted_terminal(terminal_events.get(row["task_id"])),
            rejected_terminal=_is_rejected_terminal(terminal_events.get(row["task_id"])),
            is_final_proof_task=any(
                edge.relation == "shipping_proof_of"
                for edge in edges_by_source.get(row["task_id"], ())
            ),
        )
        for row in plan_tasks
    )
    task_projection_by_id = {task.task_id: task for task in task_projections}

    open_task_ids = tuple(
        task.task_id
        for task in task_projections
        if task.status in OPEN_TASK_STATUSES
        or task.active_attempt_id is not None
    )
    recovered_blocker_ids = tuple(
        task.task_id
        for task in task_projections
        if _is_blocker(task)
        and _blocker_recovery_sources(
            task,
            children_by_target=children_by_target,
            task_by_id=task_projection_by_id,
        )
    )
    recovered = set(recovered_blocker_ids)
    unresolved_blocker_ids = tuple(
        task.task_id
        for task in task_projections
        if _is_blocker(task) and task.task_id not in recovered
    )
    has_completion_exception = _has_completion_exception(connection, plan_id)
    final_proof = _final_proof_projection(
        plan_id=plan_id,
        tasks=task_projections,
        edges_by_source=edges_by_source,
        terminal_events=terminal_events,
    )
    durable_completion = has_completion_exception or (
        not unresolved_blocker_ids and final_proof.state == "current"
    )
    projected_status = _projected_status(
        stored_status=str(plan["status"]),
        open_task_ids=open_task_ids,
        unresolved_blocker_ids=unresolved_blocker_ids,
        has_completion_exception=has_completion_exception,
        final_proof=final_proof,
    )
    issues = _projection_issues(
        plan_id=plan_id,
        stored_status=str(plan["status"]),
        projected_status=projected_status,
        durable_completion=durable_completion,
    )

    return PlanProjection(
        plan_id=plan_id,
        stored_status=str(plan["status"]),
        projected_status=projected_status,
        open_task_ids=open_task_ids,
        unresolved_blocker_ids=unresolved_blocker_ids,
        recovered_blocker_ids=recovered_blocker_ids,
        has_completion_exception=has_completion_exception,
        durable_completion=durable_completion,
        final_proof=final_proof,
        task_projections=task_projections,
        issues=issues,
    )


def plan_has_projected_durable_completion(
    connection: sqlite3.Connection,
    plan_id: str,
) -> bool:
    """Return whether the projection considers the plan durably complete."""

    return project_plan(connection, plan_id).durable_completion


def read_current_terminal(
    connection: sqlite3.Connection,
    task_id: str,
) -> TerminalEvent | None:
    """Return the current joined terminal event for a task."""

    return _current_terminal_events(connection, (task_id,)).get(task_id)


def _projected_status(
    *,
    stored_status: str,
    open_task_ids: tuple[str, ...],
    unresolved_blocker_ids: tuple[str, ...],
    has_completion_exception: bool,
    final_proof: FinalProofProjection,
) -> str:
    if stored_status == "dropped":
        return "dropped"
    if open_task_ids:
        return "active"
    if unresolved_blocker_ids:
        return "blocked"
    if has_completion_exception or final_proof.state == "current":
        return "done"
    return "active"


def _all_task_rows(connection: sqlite3.Connection) -> tuple[dict[str, object], ...]:
    return _all(
        connection.execute(
            """select task_id, plan_id, status, assurance, lineage_json, created_at, updated_at
               from tasks
               order by updated_at desc, created_at desc, task_id"""
        )
    )


def _lineage_edges(
    source_tasks: Iterable[dict[str, object]],
    task_by_id: dict[str, dict[str, object]],
) -> dict[str, tuple[LineageEdge, ...]]:
    edges_by_source: dict[str, tuple[LineageEdge, ...]] = {}
    for source in source_tasks:
        source_task_id = str(source["task_id"])
        source_plan_id = str(source["plan_id"])
        edges: list[LineageEdge] = []
        for relation in parse_lineage_json(str(source["lineage_json"])):
            if relation.relation not in VALID_TASK_LINEAGE_RELATIONS:
                continue
            target = task_by_id.get(relation.task_id)
            target_plan_id = str(target["plan_id"]) if target is not None else None
            edges.append(
                LineageEdge(
                    source_task_id=source_task_id,
                    source_plan_id=source_plan_id,
                    relation=relation.relation,
                    target_task_id=relation.task_id,
                    target_plan_id=target_plan_id,
                    cross_plan=target_plan_id is not None and target_plan_id != source_plan_id,
                )
            )
        edges_by_source[source_task_id] = tuple(edges)
    return edges_by_source


def _current_terminal_events(
    connection: sqlite3.Connection,
    task_ids: tuple[str, ...],
) -> dict[str, TerminalEvent]:
    if not task_ids:
        return {}
    placeholders = ", ".join("?" for _ in task_ids)
    rows = _all(
        connection.execute(
            f"""select *
                from (
                    select attempts.task_id,
                           attempts.attempt_id,
                           attempts.status as attempt_status,
                           attempts.finished_at,
                           evidence_bundles.bundle_id,
                           evidence_bundles.assurance,
                           evidence_bundles.summary as evidence_summary,
                           evidence_bundles.checks_json,
                           evidence_bundles.artifacts_json,
                           evidence_bundles.created_at as evidence_created_at,
                           acceptance_decisions.decision_id,
                           acceptance_decisions.actor as acceptance_actor,
                           acceptance_decisions.result as acceptance_result,
                           acceptance_decisions.rationale as acceptance_rationale,
                           acceptance_decisions.evaluation_json,
                           acceptance_decisions.created_at as decision_created_at,
                           row_number() over (
                               partition by attempts.task_id
                               order by attempts.finished_at desc,
                                        evidence_bundles.created_at desc,
                                        acceptance_decisions.created_at desc,
                                        attempts.rowid desc,
                                        evidence_bundles.rowid desc,
                                        acceptance_decisions.rowid desc
                           ) as rn
                    from attempts
                    join evidence_bundles
                      on evidence_bundles.attempt_id = attempts.attempt_id
                     and evidence_bundles.task_id = attempts.task_id
                    join acceptance_decisions
                      on acceptance_decisions.attempt_id = attempts.attempt_id
                     and acceptance_decisions.bundle_id = evidence_bundles.bundle_id
                     and acceptance_decisions.task_id = attempts.task_id
                    where attempts.status in ('succeeded', 'failed', 'blocked')
                      and attempts.task_id in ({placeholders})
                )
                where rn = 1""",
            task_ids,
        )
    )
    events: dict[str, TerminalEvent] = {}
    for row in rows:
        event = TerminalEvent(
            task_id=str(row["task_id"]),
            attempt_id=str(row["attempt_id"]),
            attempt_status=str(row["attempt_status"]),
            finished_at=row["finished_at"] if isinstance(row["finished_at"], str) else None,
            bundle_id=str(row["bundle_id"]),
            evidence_summary=str(row["evidence_summary"]),
            decision_id=str(row["decision_id"]),
            acceptance_actor=str(row["acceptance_actor"]),
            acceptance_result=str(row["acceptance_result"]),
            acceptance_rationale=str(row["acceptance_rationale"]),
            acceptance_evaluation=_json_object(str(row["evaluation_json"])),
            accepted=(
                row["attempt_status"] == "succeeded"
                and row["acceptance_result"] == "accepted"
            ),
            assurance=str(row["assurance"]),
            checks=parse_json_string_array(
                str(row["checks_json"]),
                field_name="checks_json",
            ),
            artifacts=parse_json_string_array(
                str(row["artifacts_json"]),
                field_name="artifacts_json",
            ),
            evidence_created_at=str(row["evidence_created_at"]),
            decision_created_at=str(row["decision_created_at"]),
        )
        events[event.task_id] = event
    return events


def _active_attempt_ids(
    connection: sqlite3.Connection,
    task_ids: tuple[str, ...],
) -> dict[str, str]:
    if not task_ids:
        return {}
    placeholders = ", ".join("?" for _ in task_ids)
    rows = _all(
        connection.execute(
            f"""select task_id, attempt_id
                from attempts
                where status in ('planned', 'running')
                  and task_id in ({placeholders})""",
            task_ids,
        )
    )
    return {str(row["task_id"]): str(row["attempt_id"]) for row in rows}


def _is_accepted_terminal(event: TerminalEvent | None) -> bool:
    return event is not None and event.accepted


def _is_rejected_terminal(event: TerminalEvent | None) -> bool:
    return event is not None and event.acceptance_result == "rejected"


def _is_blocker(task: TaskProjection) -> bool:
    if task.status == "blocked":
        return True
    return task.status != "done" and task.rejected_terminal


def _blocker_recovery_sources(
    task: TaskProjection,
    *,
    children_by_target: dict[str, list[LineageEdge]],
    task_by_id: dict[str, TaskProjection],
) -> tuple[str, ...]:
    recovered_by: list[str] = []
    visited: set[str] = set()
    stack = list(children_by_target.get(task.task_id, ()))
    while stack:
        edge = stack.pop()
        if edge.source_task_id in visited:
            continue
        visited.add(edge.source_task_id)
        source = task_by_id.get(edge.source_task_id)
        if source is None or edge.cross_plan:
            continue
        if edge.relation in RECOVERY_RELATIONS:
            if _coverage_edge_is_accepted(edge, source=source, target=task):
                recovered_by.append(edge.source_task_id)
            stack.extend(children_by_target.get(edge.source_task_id, ()))
    return tuple(recovered_by)


def _coverage_edge_is_accepted(
    edge: LineageEdge,
    *,
    source: TaskProjection,
    target: TaskProjection,
) -> bool:
    return (
        not edge.cross_plan
        and source.accepted_terminal
        and _assurance_covers(source.assurance, target.assurance)
    )


def _assurance_covers(source: str, target: str) -> bool:
    return ASSURANCE_RANK.get(source, 0) >= ASSURANCE_RANK.get(target, 0)


def _has_completion_exception(connection: sqlite3.Connection, plan_id: str) -> bool:
    placeholders = ", ".join("?" for _ in COMPLETION_EXCEPTION_DECISIONS)
    return (
        connection.execute(
            f"""select 1
                from decisions
                where plan_id = ?
                  and decision in ({placeholders})
                limit 1""",
            (plan_id, *sorted(COMPLETION_EXCEPTION_DECISIONS)),
        ).fetchone()
        is not None
    )


def _final_proof_projection(
    *,
    plan_id: str,
    tasks: tuple[TaskProjection, ...],
    edges_by_source: dict[str, tuple[LineageEdge, ...]],
    terminal_events: dict[str, TerminalEvent],
) -> FinalProofProjection:
    task_by_id = {task.task_id: task for task in tasks}
    coverage_neighbors = _coverage_neighbors(tasks, edges_by_source, task_by_id)
    required_task_ids = {
        task.task_id
        for task in tasks
        if task.status != "dropped"
    }
    best: FinalProofProjection | None = None
    for proof in tasks:
        if not proof.accepted_terminal or proof.assurance != "high":
            continue
        proof_targets = tuple(
            edge.target_task_id
            for edge in edges_by_source.get(proof.task_id, ())
            if edge.relation == "shipping_proof_of"
            and edge.target_plan_id == plan_id
        )
        if not proof_targets:
            continue
        covered = {proof.task_id}
        for target_id in proof_targets:
            covered.update(_reachable_coverage(target_id, coverage_neighbors))
        uncovered = tuple(sorted(required_task_ids - covered))
        event = terminal_events.get(proof.task_id)
        stale_reasons = _stale_proof_reasons(
            proof_event=event,
            covered_task_ids=covered,
            terminal_events=terminal_events,
        )
        state = "current" if not uncovered and not stale_reasons else "stale"
        candidate = FinalProofProjection(
            state=state,
            task_id=proof.task_id,
            proves_task_ids=proof_targets,
            accepted_at=event.decision_created_at if event else None,
            covered_task_ids=tuple(sorted(covered)),
            uncovered_task_ids=uncovered,
            stale_reasons=stale_reasons,
        )
        if best is None or (
            candidate.state == "current"
            and best.state != "current"
        ):
            best = candidate
    if best is not None:
        return best
    return FinalProofProjection(
        state="missing",
        task_id=None,
        proves_task_ids=(),
        accepted_at=None,
        covered_task_ids=(),
        uncovered_task_ids=tuple(sorted(required_task_ids)),
    )


def _coverage_neighbors(
    tasks: tuple[TaskProjection, ...],
    edges_by_source: dict[str, tuple[LineageEdge, ...]],
    task_by_id: dict[str, TaskProjection],
) -> dict[str, set[str]]:
    neighbors: dict[str, set[str]] = defaultdict(set)
    for source in tasks:
        for edge in edges_by_source.get(source.task_id, ()):
            if edge.relation not in COVERAGE_RELATIONS or edge.cross_plan:
                continue
            target = task_by_id.get(edge.target_task_id)
            if target is None:
                continue
            if not _coverage_edge_is_accepted(edge, source=source, target=target):
                continue
            neighbors[source.task_id].add(target.task_id)
            neighbors[target.task_id].add(source.task_id)
    return neighbors


def _reachable_coverage(
    start_task_id: str,
    neighbors: dict[str, set[str]],
) -> set[str]:
    reached: set[str] = set()
    stack = [start_task_id]
    while stack:
        task_id = stack.pop()
        if task_id in reached:
            continue
        reached.add(task_id)
        stack.extend(sorted(neighbors.get(task_id, ()), reverse=True))
    return reached


def _stale_proof_reasons(
    *,
    proof_event: TerminalEvent | None,
    covered_task_ids: set[str],
    terminal_events: dict[str, TerminalEvent],
) -> tuple[str, ...]:
    if proof_event is None:
        return ()
    proof_time = proof_event.decision_created_at
    for task_id in sorted(covered_task_ids):
        event = terminal_events.get(task_id)
        if event is None or task_id == proof_event.task_id:
            continue
        if event.decision_created_at > proof_time:
            return ("newer_terminal_event_after_proof",)
    return ()


def _projection_issues(
    *,
    plan_id: str,
    stored_status: str,
    projected_status: str,
    durable_completion: bool,
) -> tuple[ProjectionIssue, ...]:
    issues: list[ProjectionIssue] = []
    if stored_status == "blocked" and durable_completion:
        issues.append(
            ProjectionIssue(
                code="blocked_plan_has_durable_completion",
                severity="warning",
                subject_type="plan",
                subject_id=plan_id,
                message=f"blocked plan {plan_id} has projected durable completion",
            )
        )
    if stored_status == "done" and projected_status != "done":
        issues.append(
            ProjectionIssue(
                code="done_plan_without_projected_completion",
                severity="warning",
                subject_type="plan",
                subject_id=plan_id,
                message=f"done plan {plan_id} lacks projected durable completion",
            )
        )
    return tuple(issues)


def _one(cursor: sqlite3.Cursor) -> dict[str, object] | None:
    rows = _all(cursor)
    if not rows:
        return None
    return rows[0]


def _all(cursor: sqlite3.Cursor) -> tuple[dict[str, object], ...]:
    columns = tuple(column[0] for column in cursor.description)
    return tuple(dict(zip(columns, row, strict=True)) for row in cursor.fetchall())


def _json_object(raw_json: str) -> dict[str, object]:
    try:
        decoded = json.loads(raw_json)
    except json.JSONDecodeError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    return dict(decoded)
