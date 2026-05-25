from __future__ import annotations

from pathlib import Path

import pytest

from codex_supervisor.planning import SupervisorTaskRecord
from codex_supervisor.worker_launches import prepare_worker_launch_request
from codex_supervisor.worktree_artifacts import WorktreeArtifactError


def test_prepare_worker_launch_request_uses_layout_paths_without_touching_files(tmp_path):
    task = _task_record()

    preparation = prepare_worker_launch_request(
        task,
        worker_run_id="worker-run-stage7b-worker-launch-preparation-20260524",
        repo_root=tmp_path,
        result_schema_path="schemas/worker-result.schema.json",
        prompt="Do the slice.",
        rendered_goal_contract="Goal Contract",
        sandbox_mode="workspace-write",
        approval_policy="never",
        codex_home="C:/codex-home",
        codex_config_path="C:/codex-home/config.toml",
        model="gpt-test",
        reasoning_effort="medium",
        native_goal_mode=False,
        ignore_user_config=True,
        environment={"CODEX_HOME": "C:/codex-home"},
        metadata={"execution_mode": "inline_supervised_non_live"},
    )

    layout = preparation.layout
    request = preparation.request
    assert layout.worktree_path == (
        "worktrees/worker-run-stage7b-worker-launch-preparation-20260524"
    )
    assert request.worker_run_id == "worker-run-stage7b-worker-launch-preparation-20260524"
    assert request.task_id == "task-stage7b-worker-launch-preparation"
    assert request.repo_root == tmp_path
    assert request.worktree_path == tmp_path / layout.worktree_path
    assert request.result_path == layout.raw_result_path
    assert request.prompt_path == layout.prompt_path
    assert request.jsonl_path == layout.jsonl_path
    assert request.stdout_path == layout.stdout_path
    assert request.stderr_path == layout.stderr_path
    assert request.final_message_path == layout.final_message_path
    assert request.diff_summary_path == layout.diff_summary_path
    assert request.allowed_paths == tuple(task.allowed_paths)
    assert request.verification_commands == tuple(task.verification_commands)
    assert request.acceptance_criteria == tuple(task.acceptance_criteria)
    assert request.codex_home == "C:/codex-home"
    assert request.ignore_user_config is True
    assert request.environment == {"CODEX_HOME": "C:/codex-home"}
    assert not (tmp_path / "worktrees").exists()
    assert not (tmp_path / "runs").exists()
    assert not (tmp_path / "artifacts").exists()


def test_prepare_worker_launch_request_exposes_worker_run_metadata():
    task = _task_record()

    preparation = prepare_worker_launch_request(
        task,
        worker_run_id="worker-run-stage7b-worker-launch-preparation-20260524",
        repo_root=Path("C:/repo"),
        result_schema_path="schemas/worker-result.schema.json",
        prompt="Do the slice.",
        rendered_goal_contract="Goal Contract",
        sandbox_mode="workspace-write",
        approval_policy="never",
    )

    metadata = preparation.worker_run_metadata
    assert metadata["backend"] == "codex_exec"
    assert metadata["task_id"] == "task-stage7b-worker-launch-preparation"
    assert metadata["worker_run_id"] == "worker-run-stage7b-worker-launch-preparation-20260524"
    assert metadata["launch_preparation"] == {
        "mode": "non_live_request_preparation",
        "result_schema_path": "schemas/worker-result.schema.json",
        "sandbox_mode": "workspace-write",
        "approval_policy": "never",
        "native_goal_mode": False,
        "ignore_user_config": False,
    }
    assert metadata["raw_evidence_paths"] == preparation.layout.raw_evidence_paths()
    assert metadata["raw_result_path"] == preparation.layout.raw_result_path
    assert preparation.worker_run_fields() == {
        "worktree_path": preparation.layout.worktree_path,
        "prompt_path": preparation.layout.prompt_path,
        "jsonl_path": preparation.layout.jsonl_path,
        "metadata": metadata,
    }
    assert preparation.request.metadata["raw_evidence_paths"] == metadata["raw_evidence_paths"]


def test_prepare_worker_launch_request_rejects_unsafe_worker_run_id(tmp_path):
    with pytest.raises(WorktreeArtifactError):
        prepare_worker_launch_request(
            _task_record(),
            worker_run_id="../worker-run",
            repo_root=tmp_path,
            result_schema_path="schemas/worker-result.schema.json",
            prompt="Do the slice.",
            rendered_goal_contract="Goal Contract",
            sandbox_mode="workspace-write",
            approval_policy="never",
        )


def _task_record() -> SupervisorTaskRecord:
    return SupervisorTaskRecord(
        task_id="task-stage7b-worker-launch-preparation",
        plan_id="plan-stage7-worktree-artifact-management",
        title="Implement Stage 7B worker launch preparation",
        goal="Prepare a worker launch request.",
        task_type="AFK",
        status="running",
        acceptance_criteria=[
            "Worker launch preparation builds WorkerLaunchRequest.",
            "Worker-run metadata exposes raw evidence paths.",
        ],
        verification_commands=[
            "uv run --no-sync python -B -m pytest tests/test_worker_launches.py -q "
            "-p no:cacheprovider"
        ],
        allowed_paths=[
            "src/codex_supervisor/worker_launches.py",
            "tests/test_worker_launches.py",
        ],
        blocked_by=["task-stage7a-worktree-layout-guards"],
        worker_backend="codex_exec",
        review_required=True,
    )
