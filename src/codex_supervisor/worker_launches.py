"""Worker launch request preparation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_supervisor.planning import SupervisorTaskRecord, SupervisorTaskSummaryRecord
from codex_supervisor.worker_backends import WorkerLaunchRequest
from codex_supervisor.worktree_artifacts import WorktreeRunLayout, build_worktree_run_layout

JsonObject = dict[str, Any]
TaskRecord = SupervisorTaskRecord | SupervisorTaskSummaryRecord


@dataclass(frozen=True)
class WorkerLaunchPreparation:
    """Prepared launch request plus worker-run metadata."""

    layout: WorktreeRunLayout
    request: WorkerLaunchRequest
    worker_run_metadata: JsonObject

    def worker_run_fields(self) -> JsonObject:
        """Return fields suitable for worker-run creation or claim metadata."""

        return {
            "worktree_path": self.layout.worktree_path,
            "prompt_path": self.layout.prompt_path,
            "jsonl_path": self.layout.jsonl_path,
            "metadata": self.worker_run_metadata,
        }


def prepare_worker_launch_request(
    task: TaskRecord,
    *,
    worker_run_id: str,
    repo_root: Path,
    result_schema_path: str,
    prompt: str,
    rendered_goal_contract: str,
    sandbox_mode: str,
    approval_policy: str,
    codex_home: str | None = None,
    codex_config_path: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    service_tier: str | None = None,
    native_goal_mode: bool = False,
    ignore_user_config: bool = False,
    allow_degraded_jsonl: bool = False,
    environment: dict[str, str] | None = None,
    metadata: JsonObject | None = None,
) -> WorkerLaunchPreparation:
    """Prepare a WorkerLaunchRequest without touching the filesystem."""

    layout = build_worktree_run_layout(task.task_id, worker_run_id)
    worker_run_metadata = _worker_run_metadata(
        task,
        layout=layout,
        result_schema_path=result_schema_path,
        sandbox_mode=sandbox_mode,
        approval_policy=approval_policy,
        native_goal_mode=native_goal_mode,
        ignore_user_config=ignore_user_config,
        allow_degraded_jsonl=allow_degraded_jsonl,
        extra_metadata=metadata or {},
    )
    request_metadata = {
        **worker_run_metadata,
        "codex_home": codex_home,
        "codex_config_path": codex_config_path,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "service_tier": service_tier,
    }
    request = WorkerLaunchRequest(
        worker_run_id=worker_run_id,
        task_id=task.task_id,
        repo_root=repo_root,
        worktree_path=repo_root / layout.worktree_path,
        result_path=layout.raw_result_path,
        prompt_path=layout.prompt_path,
        jsonl_path=layout.jsonl_path,
        stdout_path=layout.stdout_path,
        stderr_path=layout.stderr_path,
        final_message_path=layout.final_message_path,
        diff_summary_path=layout.diff_summary_path,
        result_schema_path=result_schema_path,
        prompt=prompt,
        rendered_goal_contract=rendered_goal_contract,
        sandbox_mode=sandbox_mode,
        approval_policy=approval_policy,
        allowed_paths=tuple(task.allowed_paths),
        verification_commands=tuple(task.verification_commands),
        acceptance_criteria=tuple(task.acceptance_criteria),
        codex_home=codex_home,
        codex_config_path=codex_config_path,
        model=model,
        reasoning_effort=reasoning_effort,
        service_tier=service_tier,
        native_goal_mode=native_goal_mode,
        ignore_user_config=ignore_user_config,
        allow_degraded_jsonl=allow_degraded_jsonl,
        environment=environment or {},
        metadata=request_metadata,
    )
    return WorkerLaunchPreparation(
        layout=layout,
        request=request,
        worker_run_metadata=worker_run_metadata,
    )


def _worker_run_metadata(
    task: TaskRecord,
    *,
    layout: WorktreeRunLayout,
    result_schema_path: str,
    sandbox_mode: str,
    approval_policy: str,
    native_goal_mode: bool,
    ignore_user_config: bool,
    allow_degraded_jsonl: bool,
    extra_metadata: JsonObject,
) -> JsonObject:
    return {
        **extra_metadata,
        "backend": task.worker_backend,
        "task_id": task.task_id,
        "worker_run_id": layout.worker_run_id,
        "launch_preparation": {
            "mode": "worker_launch_request_preparation",
            "result_schema_path": result_schema_path,
            "sandbox_mode": sandbox_mode,
            "approval_policy": approval_policy,
            "native_goal_mode": native_goal_mode,
            "ignore_user_config": ignore_user_config,
            "jsonl_required": not allow_degraded_jsonl,
        },
        "worktree_path": layout.worktree_path,
        "raw_result_path": layout.raw_result_path,
        "raw_evidence_paths": layout.raw_evidence_paths(),
    }
