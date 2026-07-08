"""Read-only queue recovery projection for Goal Mode."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from codex_supervisor.attempt_store import ActivePlanWorkState, AttemptStore, TaskRecord
from codex_supervisor.attempts import (
    AttemptEvidence,
    RunAttempt,
    RunAttemptStatus,
)
from codex_supervisor.evidence_codec import (
    LAUNCH_PACKET_SHA256_CHECK_PREFIX,
    PROCESS_EXIT_CHECK_PREFIX,
    VERIFIER_INTENT_SHA256_CHECK_PREFIX,
    check_suffix,
    has_check_prefix,
)
from codex_supervisor.evidence_digest import parse_evidence_digest
from codex_supervisor.projections import TerminalEvent, project_plan, read_current_terminal
from codex_supervisor.work_graph import (
    LineageRelation,
    TaskGraphNode,
    final_proof_state,
    latest_recovery_node,
    lineage_to_dicts,
    suggested_lineage_targets,
)


@dataclass(frozen=True)
class QueueNextResult:
    """Result for the single queue inspection command."""

    plan: dict[str, object] | None
    task: dict[str, object] | None
    active_attempt: dict[str, object] | None
    latest_evidence: dict[str, object] | None
    latest_acceptance: dict[str, object] | None
    recovery_state: dict[str, object]
    next_transition: str


def queue_next_projection(database_path: Path) -> QueueNextResult:
    """Inspect the next task and project compact Goal Mode recovery state."""

    store = AttemptStore(database_path, read_only=True)
    queued = store.read_next_task()
    if queued is None:
        active_plan = store.read_active_plan_without_open_task()
        if active_plan is not None:
            latest_task = _latest_recovery_task(active_plan)
            latest_evidence = (
                store.read_latest_evidence(latest_task.task_id) if latest_task else None
            )
            terminal_event = (
                _read_current_terminal_event(database_path, latest_task.task_id)
                if latest_task
                else None
            )
            latest_acceptance = _terminal_acceptance_to_dict(terminal_event)
            return QueueNextResult(
                plan=_active_plan_to_dict(active_plan),
                task=None,
                active_attempt=None,
                latest_evidence=_evidence_to_dict(latest_evidence)
                if latest_evidence
                else None,
                latest_acceptance=latest_acceptance,
                recovery_state=_recovery_state(
                    database_path,
                    plan=active_plan,
                    plan_status=None,
                    task=None,
                    latest_task=latest_task,
                    active_attempt=None,
                    latest_evidence=latest_evidence,
                    latest_acceptance=latest_acceptance,
                ),
                next_transition=_active_plan_without_open_task_transition(
                    database_path,
                    active_plan,
                ),
            )
        return QueueNextResult(
            plan=None,
            task=None,
            active_attempt=None,
            latest_evidence=None,
            latest_acceptance=None,
            recovery_state=_recovery_state(
                database_path,
                plan=None,
                plan_status=None,
                task=None,
                latest_task=None,
                active_attempt=None,
                latest_evidence=None,
                latest_acceptance=None,
            ),
            next_transition="none",
        )

    task = queued.task
    active_attempt = store.read_active_attempt(task.task_id)
    latest_evidence = store.read_latest_evidence(task.task_id)
    terminal_event = _read_current_terminal_event(database_path, task.task_id)
    latest_acceptance = _terminal_acceptance_to_dict(terminal_event)
    return QueueNextResult(
        plan={
            "plan_id": queued.plan_id,
            "title": queued.plan_title,
            "status": queued.plan_status,
            "priority": queued.priority,
        },
        task=_task_to_dict(task),
        active_attempt=_attempt_to_dict(active_attempt) if active_attempt else None,
        latest_evidence=_evidence_to_dict(latest_evidence) if latest_evidence else None,
        latest_acceptance=latest_acceptance,
        recovery_state=_recovery_state(
            database_path,
            plan=None,
            plan_status=queued.plan_status,
            task=task,
            latest_task=task,
            active_attempt=active_attempt,
            latest_evidence=latest_evidence,
            latest_acceptance=latest_acceptance,
        ),
        next_transition=_next_transition(task, active_attempt),
    )


def _task_to_dict(task: TaskRecord) -> dict[str, object]:
    return {
        "task_id": task.task_id,
        "plan_id": task.plan_id,
        "title": task.title,
        "status": task.status,
        "assurance": task.assurance,
        "intent": task.intent,
        "acceptance_criteria": list(task.acceptance_criteria),
        "lineage": lineage_to_dicts(_graph_lineage(task.lineage)),
        "review_required": task.review_required,
    }


def _active_plan_to_dict(plan: ActivePlanWorkState) -> dict[str, object]:
    return {
        "plan_id": plan.plan_id,
        "title": plan.plan_title,
        "status": plan.plan_status,
        "priority": plan.priority,
    }


def _attempt_to_dict(attempt: RunAttempt) -> dict[str, object]:
    return {
        "attempt_id": attempt.attempt_id,
        "task_id": attempt.task_id,
        "executor": attempt.executor,
        "status": attempt.status.value,
        "summary": attempt.summary,
        "started_at": attempt.started_at,
        "finished_at": attempt.finished_at,
    }


def _evidence_to_dict(evidence: AttemptEvidence) -> dict[str, object]:
    return {
        "bundle_id": evidence.bundle_id,
        "task_id": evidence.task_id,
        "attempt_id": evidence.attempt_id,
        "assurance": evidence.assurance,
        "summary": evidence.summary,
        "checks": list(evidence.checks),
        "artifacts": list(evidence.artifacts),
        "created_at": evidence.created_at,
        "digest": parse_evidence_digest(evidence.checks),
    }


def _recovery_state(
    database_path: Path,
    *,
    plan: ActivePlanWorkState | None,
    plan_status: str | None,
    task: TaskRecord | None,
    latest_task: TaskRecord | None,
    active_attempt: RunAttempt | None,
    latest_evidence: AttemptEvidence | None,
    latest_acceptance: Mapping[str, object] | None,
) -> dict[str, object]:
    liveness = _liveness_state(database_path, active_attempt)
    packet_hashes = _packet_hashes(latest_evidence)
    git_summary = _git_summary(database_path)
    active_plan_id = _active_plan_id(plan=plan, task=task)
    lineage_task = task or latest_task
    return {
        "active_plan_id": active_plan_id,
        "active_plan_status": plan.plan_status if plan else plan_status,
        "active_task_id": task.task_id if task else None,
        "latest_task": _task_to_dict(latest_task) if latest_task else None,
        "latest_task_id": latest_task.task_id if latest_task else None,
        "latest_task_status": latest_task.status if latest_task else None,
        "active_attempt_id": active_attempt.attempt_id if active_attempt else None,
        "liveness": liveness,
        "latest_evidence_bundle_id": (
            latest_evidence.bundle_id if latest_evidence else None
        ),
        "latest_acceptance_decision_id": (
            latest_acceptance.get("decision_id") if latest_acceptance else None
        ),
        "latest_evidence_digest": (
            parse_evidence_digest(latest_evidence.checks) if latest_evidence else None
        ),
        "launch_packet_sha256": packet_hashes["launch_packet_sha256"],
        "verifier_intent_sha256": packet_hashes["verifier_intent_sha256"],
        "lineage": lineage_to_dicts(_graph_lineage(lineage_task.lineage))
        if lineage_task
        else [],
        "suggested_lineage_targets": list(
            _suggested_lineage_targets(database_path, plan)
        ),
        "final_proof": final_proof_state(_graph_node(task or latest_task)),
        "git_summary": git_summary,
        "warning_flags": list(
            _warning_flags(
                active_attempt=active_attempt,
                latest_evidence=latest_evidence,
                latest_acceptance=latest_acceptance,
                liveness=liveness,
                git_summary=git_summary,
            )
        ),
    }


def _active_plan_id(
    *,
    plan: ActivePlanWorkState | None,
    task: TaskRecord | None,
) -> str | None:
    if plan is not None:
        return plan.plan_id
    if task is not None:
        return task.plan_id
    return None


def _latest_recovery_task(plan: ActivePlanWorkState) -> TaskRecord | None:
    node = latest_recovery_node(_graph_nodes(plan.tasks))
    if node is None:
        return None
    for task in plan.tasks:
        if task.task_id == node.task_id:
            return task
    return None


def _packet_hashes(evidence: AttemptEvidence | None) -> dict[str, str | None]:
    checks = evidence.checks if evidence else ()
    return {
        "launch_packet_sha256": check_suffix(checks, LAUNCH_PACKET_SHA256_CHECK_PREFIX),
        "verifier_intent_sha256": check_suffix(checks, VERIFIER_INTENT_SHA256_CHECK_PREFIX),
    }


def _liveness_state(
    database_path: Path,
    active_attempt: RunAttempt | None,
) -> dict[str, object]:
    if active_attempt is None:
        return _empty_liveness_state(path=None)
    candidates = _candidate_liveness_paths(database_path, active_attempt.attempt_id)
    for path in candidates:
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _empty_liveness_state(path=path, error="could not read liveness")
        last_observed_at = _string_or_none(payload.get("last_output_at")) or _string_or_none(
            payload.get("started_at")
        )
        return {
            "available": True,
            "path": str(path),
            "state": _string_or_none(payload.get("state")),
            "pid": payload.get("pid") if isinstance(payload.get("pid"), int) else None,
            "started_at": _string_or_none(payload.get("started_at")),
            "last_output_at": _string_or_none(payload.get("last_output_at")),
            "ended_at": _string_or_none(payload.get("ended_at")),
            "age_seconds": _age_seconds(last_observed_at),
            "error": None,
        }
    return _empty_liveness_state(path=candidates[0] if candidates else None)


def _empty_liveness_state(path: Path | None, error: str | None = None) -> dict[str, object]:
    return {
        "available": False,
        "path": str(path) if path else None,
        "state": None,
        "pid": None,
        "started_at": None,
        "last_output_at": None,
        "ended_at": None,
        "age_seconds": None,
        "error": error,
    }


def _candidate_liveness_paths(database_path: Path, attempt_id: str) -> tuple[Path, ...]:
    workspace = _workspace_root(database_path)
    supervisor_dir = (
        database_path.resolve().parent
        if database_path.resolve().parent.name == ".codex-supervisor"
        else workspace / ".codex-supervisor"
    )
    return (supervisor_dir / "evidence" / f"{attempt_id}-liveness.json",)


def _workspace_root(database_path: Path) -> Path:
    resolved = database_path.resolve()
    parent = resolved.parent
    if parent.name in {".codex-supervisor", "plans"}:
        return parent.parent
    return parent


def _git_summary(database_path: Path) -> dict[str, object]:
    workspace = _workspace_root(database_path)
    inside = _run_git(workspace, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return {
            "workspace": str(workspace),
            "is_repository": False,
            "head": None,
            "dirty": False,
            "changed_count": 0,
            "changed_paths": [],
            "error": _git_error(inside),
        }
    head = _run_git(workspace, "rev-parse", "--short", "HEAD")
    status = _run_git(workspace, "status", "--short", "--untracked-files=all")
    changed_paths = (
        tuple(_git_status_path(line) for line in status.stdout.splitlines() if line.strip())
        if status.returncode == 0
        else ()
    )
    return {
        "workspace": str(workspace),
        "is_repository": True,
        "head": head.stdout.strip() if head.returncode == 0 else None,
        "dirty": bool(changed_paths),
        "changed_count": len(changed_paths),
        "changed_paths": list(changed_paths[:20]),
        "error": None if status.returncode == 0 else _git_error(status),
    }


def _run_git(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        return subprocess.run(
            ("git", "--no-optional-locks", "-C", str(workspace), *args),
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            env=env,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(
            ("git", "--no-optional-locks", "-C", str(workspace), *args),
            returncode=1,
            stdout="",
            stderr=str(exc),
        )


def _git_error(completed: subprocess.CompletedProcess[str]) -> str:
    return completed.stderr.strip() or completed.stdout.strip() or "git command failed"


def _git_status_path(line: str) -> str:
    return line[3:].strip() if len(line) > 3 else line.strip()


def _warning_flags(
    *,
    active_attempt: RunAttempt | None,
    latest_evidence: AttemptEvidence | None,
    latest_acceptance: Mapping[str, object] | None,
    liveness: Mapping[str, object],
    git_summary: Mapping[str, object],
) -> tuple[str, ...]:
    flags: list[str] = []
    if (
        active_attempt is not None
        and active_attempt.status is RunAttemptStatus.RUNNING
        and not liveness.get("available")
    ):
        flags.append("running_attempt_liveness_missing")
    if latest_evidence is not None and latest_acceptance is None:
        flags.append("latest_acceptance_missing")
    if (
        latest_evidence is not None
        and latest_acceptance is not None
        and latest_acceptance.get("bundle_id") != latest_evidence.bundle_id
    ):
        flags.append("latest_acceptance_not_latest_evidence")
    if latest_evidence is not None and _looks_like_attempt_run_evidence(latest_evidence):
        if check_suffix(latest_evidence.checks, LAUNCH_PACKET_SHA256_CHECK_PREFIX) is None:
            flags.append("latest_evidence_launch_packet_missing")
        if not _has_launch_metadata_artifacts(latest_evidence):
            flags.append("latest_evidence_launch_metadata_missing")
    if git_summary.get("dirty"):
        flags.append("git_dirty")
    if git_summary.get("error") and git_summary.get("is_repository"):
        flags.append("git_status_error")
    return tuple(flags)


def _looks_like_attempt_run_evidence(evidence: AttemptEvidence) -> bool:
    return has_check_prefix(evidence.checks, PROCESS_EXIT_CHECK_PREFIX)


def _has_launch_metadata_artifacts(evidence: AttemptEvidence) -> bool:
    return any(artifact.endswith("-assignment.json") for artifact in evidence.artifacts) and any(
        artifact.endswith("-command.json") for artifact in evidence.artifacts
    )


def _read_current_terminal_event(
    database_path: Path,
    task_id: str,
) -> TerminalEvent | None:
    with sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True) as connection:
        return read_current_terminal(connection, task_id)


def _terminal_acceptance_to_dict(
    event: TerminalEvent | None,
) -> dict[str, object] | None:
    if event is None:
        return None
    return {
        "decision_id": event.decision_id,
        "task_id": event.task_id,
        "attempt_id": event.attempt_id,
        "bundle_id": event.bundle_id,
        "actor": event.acceptance_actor,
        "result": event.acceptance_result,
        "rationale": event.acceptance_rationale,
        "evaluation": dict(event.acceptance_evaluation),
        "created_at": event.decision_created_at,
    }


def _age_seconds(timestamp: str | None) -> int | None:
    parsed = _parse_timestamp(timestamp)
    if parsed is None:
        return None
    age = datetime.now(UTC) - parsed
    return max(0, int(age.total_seconds()))


def _parse_timestamp(timestamp: str | None) -> datetime | None:
    if timestamp is None:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _next_transition(
    task: TaskRecord,
    attempt: RunAttempt | None,
) -> str:
    if task.status == "ready":
        return "attempt-transition --status running"
    if task.status == "blocked":
        return f"task-create --lineage repair_of={task.task_id}"
    if attempt is not None:
        return "attempt-transition --status succeeded|failed|blocked"
    return "none"


def _active_plan_without_open_task_transition(
    database_path: Path,
    plan: ActivePlanWorkState,
) -> str:
    targets = _suggested_lineage_targets(database_path, plan)
    if not targets:
        return "active plan has no open task; suggested next: task-create"
    target_id = str(targets[0]["task_id"])
    suggestions = (
        f"task-create --lineage review_of={target_id}",
        f"task-create --lineage repair_of={target_id}",
        f"task-create --lineage shipping_proof_of={target_id}",
    )
    return "active plan has no open task; suggested next: " + " | ".join(suggestions)


def _suggested_lineage_targets(
    database_path: Path,
    plan: ActivePlanWorkState | None,
) -> tuple[dict[str, object], ...]:
    if plan is None:
        return ()
    recovered_blockers = _recovered_blocker_ids(database_path, plan.plan_id)
    tasks = tuple(task for task in plan.tasks if task.task_id not in recovered_blockers)
    return suggested_lineage_targets(_graph_nodes(tasks))


def _recovered_blocker_ids(database_path: Path, plan_id: str) -> frozenset[str]:
    with sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True) as connection:
        try:
            projection = project_plan(connection, plan_id)
        except LookupError:
            return frozenset()
    return frozenset(projection.recovered_blocker_ids)


def _graph_nodes(tasks: tuple[TaskRecord, ...]) -> tuple[TaskGraphNode, ...]:
    return tuple(_graph_node(task) for task in tasks if task is not None)


def _graph_node(task: TaskRecord | None) -> TaskGraphNode | None:
    if task is None:
        return None
    return TaskGraphNode(
        task_id=task.task_id,
        status=task.status,
        lineage=_graph_lineage(task.lineage),
    )


def _graph_lineage(lineage: tuple[object, ...]) -> tuple[LineageRelation, ...]:
    relations: list[LineageRelation] = []
    for item in lineage:
        relation = getattr(item, "relation", None)
        task_id = getattr(item, "task_id", None)
        if isinstance(relation, str) and isinstance(task_id, str):
            relations.append(LineageRelation(relation=relation, task_id=task_id))
    return tuple(relations)
