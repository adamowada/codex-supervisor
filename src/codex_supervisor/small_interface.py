"""Tiny public interface over the compact substrate model."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from codex_supervisor.attempt_store import (
    ActivePlanWorkState,
    AttemptStore,
    PlanRecord,
    TaskLineageRelation,
    TaskRecord,
)
from codex_supervisor.attempts import (
    AcceptanceDecision,
    AttemptEvidence,
    RunAttempt,
    RunAttemptStatus,
    normalize_attempt_status,
)
from codex_supervisor.evidence import EvidenceEnvelope
from codex_supervisor.evidence_digest import parse_evidence_digest
from codex_supervisor.policy import AcceptanceEvaluation
from codex_supervisor.terminal_transition import terminalize_attempt


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


@dataclass(frozen=True)
class TaskCreateResult:
    """Result for creating one durable task intent."""

    plan: dict[str, object]
    task: dict[str, object]


@dataclass(frozen=True)
class AttemptTransitionResult:
    """Result for the single attempt mutation command."""

    task: dict[str, object]
    attempt: dict[str, object]
    evidence: dict[str, object] | None
    acceptance: dict[str, object] | None
    task_status: str


def task_create(
    database_path: Path,
    *,
    plan_id: str,
    plan_title: str,
    plan_goal: str,
    title: str,
    intent: str,
    assurance: str,
    acceptance_criteria: tuple[str, ...],
    lineage: tuple[Mapping[str, str], ...] = (),
    task_id: str | None = None,
    priority: int = 100,
) -> TaskCreateResult:
    """Create one generic task intent in an active plan."""

    store = AttemptStore(database_path)
    plan = store.ensure_active_plan(
        plan_id=plan_id,
        title=plan_title,
        goal=plan_goal,
        priority=priority,
    )
    task = store.create_task(
        plan_id=plan_id,
        task_id=task_id,
        title=title,
        intent=intent,
        assurance=assurance,
        acceptance_criteria=acceptance_criteria,
        lineage=_lineage_from_mappings(lineage),
    )
    return TaskCreateResult(
        plan=_plan_to_dict(plan),
        task=_task_to_dict(task),
    )


def queue_next(database_path: Path) -> QueueNextResult:
    """Inspect the next task and its attempt/evidence state."""

    store = AttemptStore(database_path, read_only=True)
    queued = store.read_next_task()
    if queued is None:
        active_plan = store.read_active_plan_without_open_task()
        if active_plan is not None:
            latest_task = _latest_recovery_task(active_plan)
            latest_evidence = (
                store.read_latest_evidence(latest_task.task_id) if latest_task else None
            )
            latest_acceptance = (
                store.read_latest_acceptance(latest_task.task_id) if latest_task else None
            )
            return QueueNextResult(
                plan=_active_plan_to_dict(active_plan),
                task=None,
                active_attempt=None,
                latest_evidence=_evidence_to_dict(latest_evidence)
                if latest_evidence
                else None,
                latest_acceptance=_acceptance_to_dict(latest_acceptance)
                if latest_acceptance
                else None,
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
                next_transition=_active_plan_without_open_task_transition(active_plan),
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
    latest_acceptance = store.read_latest_acceptance(task.task_id)
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
        latest_acceptance=(
            _acceptance_to_dict(latest_acceptance) if latest_acceptance else None
        ),
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


def attempt_transition(
    database_path: Path,
    *,
    task_id: str,
    status: str,
    summary: str,
    executor: str = "manual",
    attempt_id: str | None = None,
    checks: tuple[str, ...] = (),
    artifacts: tuple[str, ...] = (),
    acceptance_results: dict[str, bool] | None = None,
    risks: tuple[str, ...] = (),
    gaps: tuple[str, ...] = (),
    next_actions: tuple[str, ...] = (),
    review_evidence: tuple[str, ...] = (),
) -> AttemptTransitionResult:
    """Perform one attempt transition and optional evidence/acceptance evaluation."""

    store = AttemptStore(database_path)
    task = store.read_task(task_id)
    target_status = normalize_attempt_status(status)

    if target_status is RunAttemptStatus.PLANNED:
        attempt = store.create_attempt(
            task_id=task_id,
            executor=executor,
            summary=summary,
            attempt_id=attempt_id,
        )
        return _transition_result(store, task, attempt, None, None)

    if target_status is RunAttemptStatus.RUNNING:
        attempt = _start_or_create_running_attempt(store, task_id, executor, summary, attempt_id)
        return _transition_result(store, task, attempt, None, None)

    terminal_attempt_id = _terminal_attempt_id(store, task_id, attempt_id)
    evidence = EvidenceEnvelope(
        checks=checks,
        acceptance_results=acceptance_results,
        risks=risks,
        gaps=gaps,
        next_actions=next_actions,
        review_evidence=review_evidence,
    )
    terminal = terminalize_attempt(
        store,
        task,
        attempt_id=terminal_attempt_id,
        status=target_status,
        summary=summary,
        artifacts=artifacts,
        evidence=evidence,
    )
    return _transition_result(store, task, terminal.attempt, terminal.evidence, terminal.evaluation)


def _start_or_create_running_attempt(
    store: AttemptStore,
    task_id: str,
    executor: str,
    summary: str,
    attempt_id: str | None,
) -> RunAttempt:
    if attempt_id is None:
        active = store.list_active_attempts(task_id)
        if active:
            return store.start_attempt(active[0].attempt_id, task_id=task_id, summary=summary)
        created = store.create_attempt(task_id=task_id, executor=executor, summary=summary)
        return store.start_attempt(created.attempt_id, task_id=task_id, summary=summary)
    try:
        return store.start_attempt(attempt_id, task_id=task_id, summary=summary)
    except LookupError:
        created = store.create_attempt(
            task_id=task_id,
            executor=executor,
            summary=summary,
            attempt_id=attempt_id,
        )
        return store.start_attempt(created.attempt_id, task_id=task_id, summary=summary)


def _terminal_attempt_id(
    store: AttemptStore,
    task_id: str,
    attempt_id: str | None,
) -> str:
    if attempt_id is None:
        active = store.list_active_attempts(task_id)
        if len(active) != 1:
            raise ValueError("terminal transitions require exactly one active attempt")
        return active[0].attempt_id
    attempt = store.read_attempt(attempt_id)
    if attempt.task_id != task_id:
        raise ValueError(
            f"attempt {attempt.attempt_id!r} belongs to task {attempt.task_id!r}, "
            f"not {task_id!r}"
        )
    return attempt.attempt_id


def _transition_result(
    store: AttemptStore,
    task: TaskRecord,
    attempt: RunAttempt,
    evidence: AttemptEvidence | None,
    evaluation: AcceptanceEvaluation | None,
) -> AttemptTransitionResult:
    current_task = store.read_task(task.task_id)
    return AttemptTransitionResult(
        task=_task_to_dict(current_task),
        attempt=_attempt_to_dict(attempt),
        evidence=_evidence_to_dict(evidence) if evidence else None,
        acceptance=_evaluation_to_dict(evaluation) if evaluation else None,
        task_status=current_task.status,
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
        "lineage": [
            {"relation": item.relation, "task_id": item.task_id}
            for item in task.lineage
        ],
    }


def _plan_to_dict(plan: PlanRecord) -> dict[str, object]:
    return {
        "plan_id": plan.plan_id,
        "title": plan.title,
        "status": plan.status,
        "priority": plan.priority,
        "goal": plan.goal,
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


def _acceptance_to_dict(decision: AcceptanceDecision) -> dict[str, object]:
    return {
        "decision_id": decision.decision_id,
        "task_id": decision.task_id,
        "attempt_id": decision.attempt_id,
        "bundle_id": decision.bundle_id,
        "actor": decision.actor,
        "result": decision.result,
        "rationale": decision.rationale,
        "evaluation": dict(decision.evaluation),
        "created_at": decision.created_at,
    }


def _evaluation_to_dict(evaluation: AcceptanceEvaluation) -> dict[str, object]:
    return {
        "accepted": evaluation.accepted,
        "assurance": evaluation.assurance.value,
        "missing_requirements": list(evaluation.missing_requirements),
        "failed_acceptance_criteria": list(evaluation.failed_acceptance_criteria),
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
    latest_acceptance: AcceptanceDecision | None,
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
            latest_acceptance.decision_id if latest_acceptance else None
        ),
        "latest_evidence_digest": (
            parse_evidence_digest(latest_evidence.checks) if latest_evidence else None
        ),
        "launch_packet_sha256": packet_hashes["launch_packet_sha256"],
        "verifier_intent_sha256": packet_hashes["verifier_intent_sha256"],
        "lineage": [
            {"relation": item.relation, "task_id": item.task_id}
            for item in lineage_task.lineage
        ]
        if lineage_task
        else [],
        "suggested_lineage_targets": _suggested_lineage_targets(plan),
        "final_proof": _final_proof_state(task or latest_task),
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


def _suggested_lineage_targets(
    plan: ActivePlanWorkState | None,
) -> list[dict[str, object]]:
    if plan is None:
        return []
    targets: list[dict[str, object]] = []
    for task in plan.tasks:
        relations = _suggested_relations_for_task(task)
        if not relations:
            continue
        targets.append(
            {
                "task_id": task.task_id,
                "status": task.status,
                "suggested_relations": list(relations),
                "lineage": [
                    {"relation": item.relation, "task_id": item.task_id}
                    for item in task.lineage
                ],
            }
        )
    return targets


def _latest_recovery_task(plan: ActivePlanWorkState) -> TaskRecord | None:
    for task in plan.tasks:
        if task.status != "dropped":
            return task
    return None


def _suggested_relations_for_task(task: TaskRecord) -> tuple[str, ...]:
    if task.status == "blocked":
        return ("repair_of",)
    if task.status == "done":
        return ("review_of", "repair_of", "shipping_proof_of")
    return ()


def _final_proof_state(task: TaskRecord | None) -> dict[str, object]:
    if task is None:
        return {"task_id": None, "proves_task_ids": [], "status": None}
    proves_task_ids = [
        item.task_id for item in task.lineage if item.relation == "shipping_proof_of"
    ]
    return {
        "task_id": task.task_id if proves_task_ids else None,
        "proves_task_ids": proves_task_ids,
        "status": task.status if proves_task_ids else None,
    }


def _packet_hashes(evidence: AttemptEvidence | None) -> dict[str, str | None]:
    return {
        "launch_packet_sha256": _check_suffix(evidence, "launch packet sha256: "),
        "verifier_intent_sha256": _check_suffix(evidence, "verifier intent sha256: "),
    }


def _check_suffix(evidence: AttemptEvidence | None, prefix: str) -> str | None:
    if evidence is None:
        return None
    for check in evidence.checks:
        if check.startswith(prefix):
            suffix = check.removeprefix(prefix).strip()
            return suffix or None
    return None


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
    if inside.returncode != 0:
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
    try:
        return subprocess.run(
            ("git", "-C", str(workspace), *args),
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(
            ("git", "-C", str(workspace), *args),
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
    latest_acceptance: AcceptanceDecision | None,
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
        and latest_acceptance.bundle_id != latest_evidence.bundle_id
    ):
        flags.append("latest_acceptance_not_latest_evidence")
    if latest_evidence is not None and _looks_like_attempt_run_evidence(latest_evidence):
        if _check_suffix(latest_evidence, "launch packet sha256: ") is None:
            flags.append("latest_evidence_launch_packet_missing")
        if not _has_launch_metadata_artifacts(latest_evidence):
            flags.append("latest_evidence_launch_metadata_missing")
    if git_summary.get("dirty"):
        flags.append("git_dirty")
    if git_summary.get("error") and git_summary.get("is_repository"):
        flags.append("git_status_error")
    return tuple(flags)


def _looks_like_attempt_run_evidence(evidence: AttemptEvidence) -> bool:
    return any(check.startswith("process exit code: ") for check in evidence.checks)


def _has_launch_metadata_artifacts(evidence: AttemptEvidence) -> bool:
    return any(artifact.endswith("-assignment.json") for artifact in evidence.artifacts) and any(
        artifact.endswith("-command.json") for artifact in evidence.artifacts
    )


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


def _lineage_from_mappings(
    lineage: tuple[Mapping[str, str], ...],
) -> tuple[TaskLineageRelation, ...]:
    records: list[TaskLineageRelation] = []
    for item in lineage:
        try:
            relation = item["relation"]
            task_id = item["task_id"]
        except KeyError as exc:
            raise ValueError("lineage entries require relation and task_id") from exc
        records.append(TaskLineageRelation(relation=relation, task_id=task_id))
    return tuple(records)


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


def _active_plan_without_open_task_transition(plan: ActivePlanWorkState) -> str:
    targets = _suggested_lineage_targets(plan)
    if not targets:
        return "active plan has no open task; suggested next: task-create"
    target_id = str(targets[0]["task_id"])
    suggestions = (
        f"task-create --lineage review_of={target_id}",
        f"task-create --lineage repair_of={target_id}",
        f"task-create --lineage shipping_proof_of={target_id}",
    )
    return "active plan has no open task; suggested next: " + " | ".join(suggestions)
