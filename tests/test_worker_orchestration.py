from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_supervisor.planning import SupervisorTaskRecord
from codex_supervisor.worker_backends import (
    CodexExecBackend,
    CommandExecutionResult,
    WorkerLaunchRequest,
    WorkerLaunchResult,
)
from codex_supervisor.worker_orchestration import orchestrate_worker_launch
from codex_supervisor.worktree_artifacts import WorktreeArtifactError


class BackendSpy:
    def __init__(self, backend: CodexExecBackend) -> None:
        self.backend = backend
        self.requests: list[WorkerLaunchRequest] = []

    def run(self, request: WorkerLaunchRequest) -> WorkerLaunchResult:
        self.requests.append(request)
        return self.backend.run(request)


def test_orchestrate_worker_launch_runs_prepared_codex_backend_and_accepts_allowed_diff(
    tmp_path: Path,
) -> None:
    calls: list[tuple[tuple[str, ...], Path, dict[str, str]]] = []

    def runner(
        argv: tuple[str, ...],
        cwd: Path,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        calls.append((argv, cwd, environment))
        if argv == ("C:/Tools/codex.exe", "--version"):
            return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")
        _write_backend_success(
            tmp_path,
            worker_run_id="worker-run-stage7c-worker-orchestration-20260524",
            changed_file="src/codex_supervisor/worker_orchestration.py",
        )
        return CommandExecutionResult(exit_code=0, stdout='{"event":"done"}\n')

    backend = BackendSpy(
        CodexExecBackend(
            codex_executable="C:/Tools/codex.exe",
            command_runner=runner,
            launch_enabled=True,
        )
    )

    result = orchestrate_worker_launch(
        _task_record(),
        backend=backend,
        worker_run_id="worker-run-stage7c-worker-orchestration-20260524",
        repo_root=tmp_path,
        result_schema_path=(
            "runs/worker-run-stage7c-worker-orchestration-20260524/worker-result.schema.json"
        ),
        prompt="Do the slice.",
        rendered_goal_contract="Goal Contract",
        sandbox_mode="workspace-write",
        approval_policy="never",
        environment={"CODEX_HOME": "C:/codex-home"},
    )

    assert len(backend.requests) == 1
    request = backend.requests[0]
    assert request == result.preparation.request
    assert request.worktree_path == (
        tmp_path / "worktrees" / "worker-run-stage7c-worker-orchestration-20260524"
    )
    assert calls[0] == (
        ("C:/Tools/codex.exe", "--version"),
        request.worktree_path,
        {"CODEX_HOME": "C:/codex-home"},
    )
    assert calls[1][0][1:4] == ("exec", "--json", "--output-schema")
    assert result.launch_result.status == "completed"
    assert result.launch_result.result_path == (
        "artifacts/worker-run-stage7c-worker-orchestration-20260524/worker-result.raw.json"
    )
    assert result.changed_files == ("src/codex_supervisor/worker_orchestration.py",)
    assert result.changed_files_source == "diff_summary"
    assert result.changed_path_violations == ()
    assert result.launch_result.changed_files == result.changed_files
    assert result.launch_result.metadata["changed_path_validation"]["source"] == "diff_summary"
    assert (
        tmp_path
        / "worktrees"
        / "worker-run-stage7c-worker-orchestration-20260524"
        / "src"
        / "codex_supervisor"
        / "worker_orchestration.py"
    ).exists()


def test_orchestrate_worker_launch_rejects_completed_result_with_out_of_scope_diff(
    tmp_path: Path,
) -> None:
    def runner(
        argv: tuple[str, ...],
        cwd: Path,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        if argv == ("C:/Tools/codex.exe", "--version"):
            return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")
        _write_backend_success(
            tmp_path,
            worker_run_id="worker-run-stage7c-worker-orchestration-20260524",
            changed_file="README.md",
        )
        return CommandExecutionResult(exit_code=0, stdout='{"event":"done"}\n')

    result = orchestrate_worker_launch(
        _task_record(),
        backend=CodexExecBackend(
            codex_executable="C:/Tools/codex.exe",
            command_runner=runner,
            launch_enabled=True,
        ),
        worker_run_id="worker-run-stage7c-worker-orchestration-20260524",
        repo_root=tmp_path,
        result_schema_path=(
            "runs/worker-run-stage7c-worker-orchestration-20260524/worker-result.schema.json"
        ),
        prompt="Do the slice.",
        rendered_goal_contract="Goal Contract",
        sandbox_mode="workspace-write",
        approval_policy="never",
    )

    assert result.launch_result.status == "failed"
    assert result.launch_result.result_path is None
    assert result.launch_result.exit_code == 1
    assert result.launch_result.failure_class == "changed_paths_out_of_scope"
    assert result.changed_files == ("README.md",)
    assert result.changed_path_violations[0].path == "README.md"
    assert result.changed_path_violations[0].reason == "outside_allowed_paths"
    assert result.launch_result.metadata["changed_path_violations"] == [
        {"path": "README.md", "reason": "outside_allowed_paths"}
    ]


def test_orchestrate_worker_launch_preserves_backend_failure_class_and_reports_violations(
    tmp_path: Path,
) -> None:
    def runner(
        argv: tuple[str, ...],
        cwd: Path,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        if argv == ("C:/Tools/codex.exe", "--version"):
            return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")
        _write_diff_summary(
            tmp_path,
            worker_run_id="worker-run-stage7c-worker-orchestration-20260524",
            changed_file="README.md",
        )
        return CommandExecutionResult(exit_code=42, stdout="partial\n", stderr="boom\n")

    result = orchestrate_worker_launch(
        _task_record(),
        backend=CodexExecBackend(
            codex_executable="C:/Tools/codex.exe",
            command_runner=runner,
            launch_enabled=True,
        ),
        worker_run_id="worker-run-stage7c-worker-orchestration-20260524",
        repo_root=tmp_path,
        result_schema_path=(
            "runs/worker-run-stage7c-worker-orchestration-20260524/worker-result.schema.json"
        ),
        prompt="Do the slice.",
        rendered_goal_contract="Goal Contract",
        sandbox_mode="workspace-write",
        approval_policy="never",
    )

    assert result.launch_result.status == "failed"
    assert result.launch_result.exit_code == 42
    assert result.launch_result.failure_class == "codex_exec_failed"
    assert result.changed_files == ("README.md",)
    assert result.launch_result.changed_files == ("README.md",)
    assert result.launch_result.metadata["changed_path_violations"] == [
        {"path": "README.md", "reason": "outside_allowed_paths"}
    ]


def test_orchestrate_worker_launch_uses_git_worktree_changed_files_when_required(
    tmp_path: Path,
) -> None:
    def runner(
        argv: tuple[str, ...],
        cwd: Path,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        if argv == ("C:/Tools/codex.exe", "--version"):
            return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")
        _write_backend_success(
            tmp_path,
            worker_run_id="worker-run-stage7c-worker-orchestration-20260524",
            changed_file="README.md",
        )
        return CommandExecutionResult(exit_code=0, stdout='{"event":"done"}\n')

    git_calls: list[tuple[str, ...]] = []

    def git_runner(
        argv: tuple[str, ...],
        cwd: Path,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        git_calls.append(argv)
        assert environment == {"GIT_OPTIONAL_LOCKS": "0"}
        if argv == ("git", "rev-parse", "--abbrev-ref", "HEAD"):
            return CommandExecutionResult(exit_code=0, stdout="HEAD\n")
        if argv == ("git", "rev-parse", "base-sha"):
            return CommandExecutionResult(exit_code=0, stdout="base-sha\n")
        if argv == ("git", "rev-parse", "HEAD"):
            return CommandExecutionResult(exit_code=0, stdout="head-sha\n")
        if argv == ("git", "status", "--porcelain=v1"):
            return CommandExecutionResult(
                exit_code=0,
                stdout=" M src/codex_supervisor/worker_orchestration.py\n",
            )
        if argv == ("git", "diff", "--name-only", "base-sha...head-sha"):
            return CommandExecutionResult(exit_code=0, stdout="")
        raise AssertionError(f"unexpected git argv: {argv}")

    result = orchestrate_worker_launch(
        _task_record(),
        backend=CodexExecBackend(
            codex_executable="C:/Tools/codex.exe",
            command_runner=runner,
            launch_enabled=True,
        ),
        worker_run_id="worker-run-stage7c-worker-orchestration-20260524",
        repo_root=tmp_path,
        result_schema_path=(
            "runs/worker-run-stage7c-worker-orchestration-20260524/worker-result.schema.json"
        ),
        prompt="Do the slice.",
        rendered_goal_contract="Goal Contract",
        sandbox_mode="workspace-write",
        approval_policy="never",
        require_git_changed_files=True,
        git_command_runner=git_runner,
        git_base_ref="base-sha",
    )

    assert result.launch_result.status == "completed"
    assert result.changed_files == ("src/codex_supervisor/worker_orchestration.py",)
    assert result.changed_files_source == "git_worktree"
    assert result.worktree_state is not None
    assert result.launch_result.metadata["changed_path_validation"]["source"] == "git_worktree"
    assert result.launch_result.metadata["worktree_state"]["commands"][0]["cwd"] == (
        "worktrees/worker-run-stage7c-worker-orchestration-20260524"
    )
    assert len(git_calls) == 5


def test_orchestrate_worker_launch_rejects_worker_result_git_mismatch(
    tmp_path: Path,
) -> None:
    def runner(
        argv: tuple[str, ...],
        cwd: Path,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        if argv == ("C:/Tools/codex.exe", "--version"):
            return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")
        _write_backend_success(
            tmp_path,
            worker_run_id="worker-run-stage7c-worker-orchestration-20260524",
            changed_file="src/codex_supervisor/worker_orchestration.py",
        )
        return CommandExecutionResult(exit_code=0, stdout='{"event":"done"}\n')

    def git_runner(
        argv: tuple[str, ...],
        cwd: Path,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        if argv == ("git", "rev-parse", "--abbrev-ref", "HEAD"):
            return CommandExecutionResult(exit_code=0, stdout="HEAD\n")
        if argv == ("git", "rev-parse", "base-sha"):
            return CommandExecutionResult(exit_code=0, stdout="base-sha\n")
        if argv == ("git", "rev-parse", "HEAD"):
            return CommandExecutionResult(exit_code=0, stdout="head-sha\n")
        if argv == ("git", "status", "--porcelain=v1"):
            return CommandExecutionResult(
                exit_code=0, stdout=" M tests/test_worker_orchestration.py\n"
            )
        if argv == ("git", "diff", "--name-only", "base-sha...head-sha"):
            return CommandExecutionResult(exit_code=0, stdout="")
        raise AssertionError(f"unexpected git argv: {argv}")

    result = orchestrate_worker_launch(
        _task_record(),
        backend=CodexExecBackend(
            codex_executable="C:/Tools/codex.exe",
            command_runner=runner,
            launch_enabled=True,
        ),
        worker_run_id="worker-run-stage7c-worker-orchestration-20260524",
        repo_root=tmp_path,
        result_schema_path=(
            "runs/worker-run-stage7c-worker-orchestration-20260524/worker-result.schema.json"
        ),
        prompt="Do the slice.",
        rendered_goal_contract="Goal Contract",
        sandbox_mode="workspace-write",
        approval_policy="never",
        require_git_changed_files=True,
        git_command_runner=git_runner,
        git_base_ref="base-sha",
    )

    assert result.launch_result.status == "failed"
    assert result.launch_result.failure_class == "changed_files_mismatch"
    assert result.launch_result.metadata["changed_files_mismatch"] == {
        "git_detected_files": ["tests/test_worker_orchestration.py"],
        "worker_result_changed_files": ["src/codex_supervisor/worker_orchestration.py"],
    }


def test_orchestrate_worker_launch_blocks_completed_run_without_git_state(
    tmp_path: Path,
) -> None:
    def runner(
        argv: tuple[str, ...],
        cwd: Path,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        if argv == ("C:/Tools/codex.exe", "--version"):
            return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")
        _write_backend_success(
            tmp_path,
            worker_run_id="worker-run-stage7c-worker-orchestration-20260524",
            changed_file="src/codex_supervisor/worker_orchestration.py",
        )
        return CommandExecutionResult(exit_code=0, stdout='{"event":"done"}\n')

    def git_runner(
        argv: tuple[str, ...],
        cwd: Path,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        return CommandExecutionResult(exit_code=1, stderr="not a worktree\n")

    result = orchestrate_worker_launch(
        _task_record(),
        backend=CodexExecBackend(
            codex_executable="C:/Tools/codex.exe",
            command_runner=runner,
            launch_enabled=True,
        ),
        worker_run_id="worker-run-stage7c-worker-orchestration-20260524",
        repo_root=tmp_path,
        result_schema_path=(
            "runs/worker-run-stage7c-worker-orchestration-20260524/worker-result.schema.json"
        ),
        prompt="Do the slice.",
        rendered_goal_contract="Goal Contract",
        sandbox_mode="workspace-write",
        approval_policy="never",
        require_git_changed_files=True,
        git_command_runner=git_runner,
    )

    assert result.launch_result.status == "failed"
    assert result.launch_result.result_path is None
    assert result.launch_result.failure_class == "worktree_state_unavailable"
    assert result.changed_files_source == "git_worktree_failed"
    assert result.launch_result.metadata["worktree_state"]["failure_class"] == (
        "worktree_state_failed"
    )


def test_orchestrate_worker_launch_rejects_unsafe_worker_run_id(tmp_path: Path) -> None:
    with pytest.raises(WorktreeArtifactError):
        orchestrate_worker_launch(
            _task_record(),
            backend=CodexExecBackend(codex_executable="C:/Tools/codex.exe"),
            worker_run_id="../worker-run",
            repo_root=tmp_path,
            result_schema_path=(
                "runs/worker-run-stage7c-worker-orchestration-20260524/worker-result.schema.json"
            ),
            prompt="Do the slice.",
            rendered_goal_contract="Goal Contract",
            sandbox_mode="workspace-write",
            approval_policy="never",
        )


def _write_backend_success(tmp_path: Path, *, worker_run_id: str, changed_file: str) -> None:
    result_changed_file = "src/codex_supervisor/worker_orchestration.py"
    changed_path = tmp_path / "worktrees" / worker_run_id / result_changed_file
    changed_path.parent.mkdir(parents=True, exist_ok=True)
    changed_path.write_text("print('ok')\n", encoding="utf-8")
    result_file = tmp_path / "artifacts" / worker_run_id / "worker-result.raw.json"
    result_file.parent.mkdir(parents=True)
    payload = {
        "worker_run_id": worker_run_id,
        "status": "completed",
        "summary": "Worker completed.",
        "changed_files": [result_changed_file],
        "tests_run": [
            {
                "command": (
                    "uv run --no-sync python -B -m pytest tests/test_worker_orchestration.py "
                    "-q -p no:cacheprovider"
                ),
                "exit_code": 0,
                "summary": "passed",
            }
        ],
        "acceptance_results": {
            "Orchestration uses prepare_worker_launch_request and calls the injected backend.": {
                "status": "passed",
                "evidence": "Injected backend was called.",
            },
            "Diff-summary changed files are parsed and validated.": {
                "status": "passed",
                "evidence": "Changed files were parsed.",
            },
        },
        "risks": [],
        "follow_up_tasks": [],
        "artifacts": [f"artifacts/{worker_run_id}/worker-result.raw.json"],
        "completion_notes": "Ready.",
    }
    result_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    final_file = tmp_path / "runs" / worker_run_id / "final-message.txt"
    final_file.parent.mkdir(parents=True, exist_ok=True)
    final_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (tmp_path / "runs" / worker_run_id / "events.jsonl").write_text(
        '{"event":"assistant.step"}\n',
        encoding="utf-8",
    )
    _write_diff_summary(tmp_path, worker_run_id=worker_run_id, changed_file=changed_file)


def _write_diff_summary(tmp_path: Path, *, worker_run_id: str, changed_file: str) -> None:
    diff_summary = tmp_path / "runs" / worker_run_id / "diff-summary.txt"
    diff_summary.parent.mkdir(parents=True, exist_ok=True)
    diff_summary.write_text(f"{changed_file}\n", encoding="utf-8")


def _task_record() -> SupervisorTaskRecord:
    return SupervisorTaskRecord(
        task_id="task-stage7c-worker-orchestration",
        plan_id="plan-stage7-worktree-artifact-management",
        title="Implement Stage 7C worker orchestration guard",
        goal="Prepare and run a worker backend with changed-path gates.",
        task_type="AFK",
        status="running",
        acceptance_criteria=[
            "Orchestration uses prepare_worker_launch_request and calls the injected backend.",
            "Diff-summary changed files are parsed and validated.",
        ],
        verification_commands=[
            "uv run --no-sync python -B -m pytest tests/test_worker_orchestration.py -q "
            "-p no:cacheprovider"
        ],
        allowed_paths=[
            "src/codex_supervisor/worker_orchestration.py",
            "tests/test_worker_orchestration.py",
        ],
        blocked_by=["task-stage7b-worker-launch-preparation"],
        worker_backend="codex_exec",
        review_required=True,
    )
