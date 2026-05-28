"""Worker integration over the compact attempt/evidence path."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codex_supervisor.attempt_store import AttemptStore, TaskRecord
from codex_supervisor.policy import AssurancePolicy, policy_for_assurance
from codex_supervisor.small_interface import AttemptTransitionResult, attempt_transition


@dataclass(frozen=True)
class WorkerResult:
    """Normalized result returned by a worker executor."""

    status: str
    summary: str
    checks: tuple[str, ...]
    artifacts: tuple[str, ...]
    acceptance_results: dict[str, bool]
    risks: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()
    next_actions: tuple[str, ...] = ()
    review_evidence: tuple[str, ...] = ()
    raw_output: str = ""


@dataclass(frozen=True)
class WorkerRunResult:
    """Persisted worker attempt result."""

    prompt: str
    transition: AttemptTransitionResult
    worker_result: WorkerResult


@dataclass(frozen=True)
class LiveWorkerVerificationPlan:
    """Bounded live-worker verification description."""

    task_id: str
    timeout_seconds: int
    command: tuple[str, ...]
    required_evidence: tuple[str, ...]


class FakeCodexWorker:
    """Deterministic worker used to prove the worker contract."""

    def __init__(self, result: WorkerResult | None = None) -> None:
        self.result = result

    def execute(
        self,
        *,
        prompt: str,
        task: TaskRecord,
        policy: AssurancePolicy,
    ) -> WorkerResult:
        if self.result is not None:
            return self.result
        checks = ("fake-worker: policy prompt inspected",)
        artifacts = ("worker-output: fake result",)
        risks = (
            ("fake-worker: live Codex execution still needs bounded verification",)
            if policy.level.value == "high"
            else ()
        )
        return WorkerResult(
            status="succeeded",
            summary=f"Fake Codex worker satisfied {task.task_id}.",
            checks=checks,
            artifacts=artifacts,
            acceptance_results=dict.fromkeys(task.acceptance_criteria, True),
            risks=risks,
            raw_output=prompt,
        )


def build_worker_prompt(task: TaskRecord) -> str:
    """Build a policy-aware prompt for a fresh-context Codex worker."""

    policy = policy_for_assurance(task.assurance)
    criteria = "\n".join(f"- {criterion}" for criterion in task.acceptance_criteria)
    evidence = _policy_evidence_lines(policy)
    return "\n".join(
        (
            "TaskIntent",
            f"task_id: {task.task_id}",
            f"title: {task.title}",
            f"intent: {task.intent}",
            f"assurance: {policy.level.value}",
            "",
            "Acceptance Criteria",
            criteria or "- none",
            "",
            "Required Evidence",
            evidence,
            "",
            "Return a structured worker result with summary, checks, artifacts, risks, "
            "and acceptance results.",
        )
    )


def run_fake_worker_attempt(
    database_path: Path,
    *,
    task_id: str,
    attempt_id: str | None = None,
    worker: FakeCodexWorker | None = None,
) -> WorkerRunResult:
    """Run a deterministic fake Codex worker as a compact attempt."""

    store = AttemptStore(database_path)
    task = store.read_task(task_id)
    policy = policy_for_assurance(task.assurance)
    prompt = build_worker_prompt(task)
    worker = worker or FakeCodexWorker()

    running = attempt_transition(
        database_path,
        task_id=task_id,
        attempt_id=attempt_id,
        executor="codex",
        status="running",
        summary="Fake Codex worker running.",
    )
    try:
        worker_result = worker.execute(prompt=prompt, task=task, policy=policy)
    except Exception as exc:
        worker_result = _blocked_worker_result(
            summary=f"Worker execution failed: {exc}",
            detail=f"worker-exception: {exc.__class__.__name__}",
        )
    if worker_result.status not in {"succeeded", "failed", "blocked"}:
        worker_result = _blocked_worker_result(
            summary=f"Worker returned invalid status: {worker_result.status}",
            detail=f"worker-invalid-status: {worker_result.status}",
        )
    transition = attempt_transition(
        database_path,
        task_id=task_id,
        attempt_id=str(running.attempt["attempt_id"]),
        executor="codex",
        status=worker_result.status,
        summary=worker_result.summary,
        checks=worker_result.checks,
        artifacts=worker_result.artifacts,
        acceptance_results=worker_result.acceptance_results,
        risks=worker_result.risks,
        gaps=worker_result.gaps,
        next_actions=worker_result.next_actions,
        review_evidence=worker_result.review_evidence,
    )
    return WorkerRunResult(
        prompt=prompt,
        transition=transition,
        worker_result=worker_result,
    )


def _blocked_worker_result(*, summary: str, detail: str) -> WorkerResult:
    return WorkerResult(
        status="blocked",
        summary=summary,
        checks=(detail,),
        artifacts=("worker-output: blocked before valid result",),
        acceptance_results={},
        risks=("Worker attempt did not produce valid acceptance evidence.",),
    )


def build_live_worker_verification_plan(
    task: TaskRecord,
    *,
    timeout_seconds: int = 120,
) -> LiveWorkerVerificationPlan:
    """Describe the bounded live verification path without launching Codex."""

    return LiveWorkerVerificationPlan(
        task_id=task.task_id,
        timeout_seconds=timeout_seconds,
        command=(
            "codex",
            "exec",
            "--json",
            "--",
            "run compact worker attempt for task",
            task.task_id,
        ),
        required_evidence=(
            "resolved Codex executable",
            "bounded timeout",
            "worker prompt",
            "worker result",
            "evidence bundle",
            "acceptance evaluation",
        ),
    )


def _policy_evidence_lines(policy: AssurancePolicy) -> str:
    lines = ["- summary"]
    if policy.require_focused_checks:
        lines.append("- focused checks")
    if policy.require_strict_checks:
        lines.append("- strict checks")
    if policy.require_artifacts:
        lines.append("- artifacts")
    if policy.require_acceptance_results:
        lines.append("- acceptance results")
    if policy.require_risk_or_gap_notes:
        lines.append("- risks or gaps")
    if policy.require_risk_notes:
        lines.append("- risk notes")
    if policy.require_next_action:
        lines.append("- next action")
    if policy.require_review_when_requested:
        lines.append("- review evidence when review is the risk control")
    return "\n".join(lines)
