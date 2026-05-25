from __future__ import annotations

import json

from codex_supervisor.worker_backends import (
    CodexExecBackend,
    CommandExecutionResult,
    FakeWorkerBackend,
    WorkerLaunchRequest,
)


def test_fake_worker_backend_emits_contract_compatible_result(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "worker.py").write_text("print('ok')\n", encoding="utf-8")
    request = WorkerLaunchRequest(
        worker_run_id="run-worker",
        task_id="task-worker",
        repo_root=tmp_path,
        worktree_path=tmp_path,
        result_path="artifacts/run-worker/worker-result.raw.json",
        prompt_path="runs/run-worker/prompt.md",
        jsonl_path="runs/run-worker/events.jsonl",
        stdout_path="runs/run-worker/stdout.txt",
        stderr_path="runs/run-worker/stderr.txt",
        final_message_path="runs/run-worker/final-message.txt",
        diff_summary_path="runs/run-worker/diff-summary.txt",
        result_schema_path="schemas/worker-result.schema.json",
        prompt="Do the slice.",
        rendered_goal_contract="Goal Contract",
        sandbox_mode="workspace-write",
        approval_policy="never",
        allowed_paths=("src/**",),
        verification_commands=("python -B -m pytest -p no:cacheprovider",),
        acceptance_criteria=("Criterion passes.",),
    )

    result = FakeWorkerBackend(changed_files=("src/worker.py",)).run(request)

    assert result.status == "completed"
    assert result.result_path == "artifacts/run-worker/worker-result.raw.json"
    assert result.prompt_path == "runs/run-worker/prompt.md"
    assert result.stdout_path == "runs/run-worker/stdout.txt"
    assert result.stderr_path == "runs/run-worker/stderr.txt"
    assert result.final_message_path == "runs/run-worker/final-message.txt"
    assert result.diff_summary_path == "runs/run-worker/diff-summary.txt"
    payload_path = tmp_path / "artifacts" / "run-worker" / "worker-result.raw.json"
    payload = json.loads(payload_path.read_text())
    assert payload["worker_run_id"] == "run-worker"
    assert payload["changed_files"] == ["src/worker.py"]
    assert payload["acceptance_results"]["Criterion passes."]["status"] == "passed"
    assert (tmp_path / "runs" / "run-worker" / "prompt.md").read_text() == "Do the slice."
    assert (tmp_path / "runs" / "run-worker" / "events.jsonl").exists()
    assert (tmp_path / "runs" / "run-worker" / "stdout.txt").read_text() == (
        "Fake worker completed the requested slice.\n"
    )
    assert (tmp_path / "runs" / "run-worker" / "stderr.txt").read_text() == ""
    assert (tmp_path / "runs" / "run-worker" / "diff-summary.txt").read_text() == (
        "src/worker.py\n"
    )


def test_fake_worker_backend_can_return_failure_without_result_file(tmp_path):
    request = WorkerLaunchRequest(
        worker_run_id="run-worker",
        task_id="task-worker",
        repo_root=tmp_path,
        worktree_path=tmp_path,
        result_path="artifacts/run-worker/worker-result.raw.json",
        prompt_path="runs/run-worker/prompt.md",
        jsonl_path="runs/run-worker/events.jsonl",
        stdout_path="runs/run-worker/stdout.txt",
        stderr_path="runs/run-worker/stderr.txt",
        final_message_path="runs/run-worker/final-message.txt",
        diff_summary_path="runs/run-worker/diff-summary.txt",
        result_schema_path="schemas/worker-result.schema.json",
        prompt="Do the slice.",
        rendered_goal_contract="Goal Contract",
        sandbox_mode="workspace-write",
        approval_policy="never",
        allowed_paths=("src/**",),
        verification_commands=("python -B -m pytest -p no:cacheprovider",),
        acceptance_criteria=("Criterion passes.",),
    )

    result = FakeWorkerBackend(
        changed_files=(),
        failure_class="codex_cli_unavailable",
    ).run(request)

    assert result.status == "failed"
    assert result.failure_class == "codex_cli_unavailable"
    assert result.prompt_path == "runs/run-worker/prompt.md"
    assert result.jsonl_path == "runs/run-worker/events.jsonl"
    assert result.stdout_path == "runs/run-worker/stdout.txt"
    assert result.stderr_path == "runs/run-worker/stderr.txt"
    assert result.final_message_path == "runs/run-worker/final-message.txt"
    assert result.diff_summary_path == "runs/run-worker/diff-summary.txt"
    assert not (tmp_path / "artifacts" / "run-worker" / "worker-result.raw.json").exists()
    assert (tmp_path / "runs" / "run-worker" / "prompt.md").read_text() == "Do the slice."
    assert (tmp_path / "runs" / "run-worker" / "stderr.txt").read_text() == (
        "Fake worker failed: codex_cli_unavailable\n"
    )
    assert "fake.failed" in (tmp_path / "runs" / "run-worker" / "events.jsonl").read_text()


def test_codex_exec_backend_preflight_builds_list_argv_without_launching(tmp_path):
    calls: list[tuple[tuple[str, ...], object, dict[str, str]]] = []

    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        calls.append((argv, cwd, environment))
        return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")

    request = _codex_exec_request(
        tmp_path,
        ignore_user_config=True,
        codex_home="C:/codex-home",
        codex_config_path="C:/codex-home/config.toml",
        model="gpt-test",
        reasoning_effort="medium",
        environment={"CODEX_HOME": "C:/codex-home"},
    )

    preflight = CodexExecBackend(
        codex_executable="C:/Tools/codex.exe",
        command_runner=runner,
    ).preflight(request)

    assert calls == [
        (
            ("C:/Tools/codex.exe", "--version"),
            tmp_path,
            {"CODEX_HOME": "C:/codex-home"},
        )
    ]
    assert preflight.failure_class is None
    assert preflight.version_stdout == "codex 1.2.3\n"
    assert preflight.argv == (
        "C:/Tools/codex.exe",
        "exec",
        "--json",
        "--output-schema",
        "schemas/worker-result.schema.json",
        "--output-last-message",
        "runs/run-worker/final-message.txt",
        "--sandbox",
        "workspace-write",
        "--ignore-user-config",
        "Do the slice.",
    )
    assert preflight.metadata["argv"] == list(preflight.argv)
    assert preflight.metadata["codex_home"] == "C:/codex-home"
    assert preflight.metadata["goal_mode_decision"] == "prompt_rendered_fallback"
    assert preflight.metadata["raw_evidence_paths"] == {
        "prompt": "runs/run-worker/prompt.md",
        "jsonl": "runs/run-worker/events.jsonl",
        "stdout": "runs/run-worker/stdout.txt",
        "stderr": "runs/run-worker/stderr.txt",
        "final_message": "runs/run-worker/final-message.txt",
        "diff_summary": "runs/run-worker/diff-summary.txt",
        "result": "artifacts/run-worker/worker-result.raw.json",
    }
    assert preflight.metadata["version_gated_options"] == [
        "model",
        "reasoning_effort",
        "config",
    ]


def test_codex_exec_backend_records_windowsapps_access_denied_without_launching(tmp_path):
    calls: list[tuple[str, ...]] = []

    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        calls.append(argv)
        raise PermissionError("Access is denied")

    request = _codex_exec_request(tmp_path)

    result = CodexExecBackend(
        codex_executable=(
            "C:/Program Files/WindowsApps/OpenAI.Codex_26.519.5221.0_x64__2p2nqsd0c76g0/"
            "app/resources/codex.exe"
        ),
        command_runner=runner,
    ).run(request)

    assert calls == [
        (
            "C:/Program Files/WindowsApps/OpenAI.Codex_26.519.5221.0_x64__2p2nqsd0c76g0/"
            "app/resources/codex.exe",
            "--version",
        )
    ]
    assert result.status == "failed"
    assert result.failure_class == "codex_cli_unavailable"
    assert result.result_path is None
    assert result.metadata["failure_class"] == "codex_cli_unavailable"
    assert result.metadata["argv"][1:4] == ["exec", "--json", "--output-schema"]
    assert not (tmp_path / "artifacts" / "run-worker" / "worker-result.raw.json").exists()
    assert (tmp_path / "runs" / "run-worker" / "prompt.md").read_text() == "Do the slice."
    assert (tmp_path / "runs" / "run-worker" / "stderr.txt").read_text() == "Access is denied"
    assert (tmp_path / "runs" / "run-worker" / "final-message.txt").read_text() == (
        "Codex Exec preflight failed: codex_cli_unavailable\n"
    )
    assert (tmp_path / "runs" / "run-worker" / "diff-summary.txt").read_text() == ""
    assert (
        "codex_exec.preflight_failed"
        in (tmp_path / "runs" / "run-worker" / "events.jsonl").read_text()
    )


def test_codex_exec_backend_preflight_success_stays_non_live_until_enabled(tmp_path):
    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        assert argv == ("C:/Tools/codex.exe", "--version")
        return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")

    request = _codex_exec_request(tmp_path)

    result = CodexExecBackend(
        codex_executable="C:/Tools/codex.exe",
        command_runner=runner,
    ).run(request)

    assert result.status == "blocked"
    assert result.failure_class is None
    assert result.metadata["launch_decision"] == "stage6b_preflight_only_launch_disabled"
    assert "preflight passed" in (tmp_path / "runs" / "run-worker" / "stdout.txt").read_text()
    assert (
        "codex_exec.preflight_ready"
        in (tmp_path / "runs" / "run-worker" / "events.jsonl").read_text()
    )


def test_codex_exec_backend_launch_success_returns_result_path_and_preserves_final_message(
    tmp_path,
):
    calls: list[tuple[str, ...]] = []

    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        calls.append(argv)
        if argv == ("C:/Tools/codex.exe", "--version"):
            return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")
        result_file = tmp_path / "artifacts" / "run-worker" / "worker-result.raw.json"
        result_file.parent.mkdir(parents=True)
        result_file.write_text('{"status":"completed"}\n', encoding="utf-8")
        final_file = tmp_path / "runs" / "run-worker" / "final-message.txt"
        final_file.parent.mkdir(parents=True, exist_ok=True)
        final_file.write_text("assistant final\n", encoding="utf-8")
        (tmp_path / "runs" / "run-worker" / "events.jsonl").write_text(
            '{"event":"assistant.step"}\n',
            encoding="utf-8",
        )
        (tmp_path / "runs" / "run-worker" / "diff-summary.txt").write_text(
            "src/success.py\n",
            encoding="utf-8",
        )
        return CommandExecutionResult(exit_code=0, stdout='{"event":"done"}\n')

    request = _codex_exec_request(tmp_path)

    result = CodexExecBackend(
        codex_executable="C:/Tools/codex.exe",
        command_runner=runner,
        launch_enabled=True,
    ).run(request)

    assert calls[0] == ("C:/Tools/codex.exe", "--version")
    assert calls[1][1:4] == ("exec", "--json", "--output-schema")
    assert result.status == "completed"
    assert result.result_path == "artifacts/run-worker/worker-result.raw.json"
    assert result.failure_class is None
    assert result.metadata["launch_decision"] == "executed"
    assert (
        result.metadata["raw_evidence_paths"]["result"]
        == "artifacts/run-worker/worker-result.raw.json"
    )
    assert (tmp_path / "runs" / "run-worker" / "stdout.txt").read_text() == ('{"event":"done"}\n')
    assert (tmp_path / "runs" / "run-worker" / "final-message.txt").read_text() == (
        "assistant final\n"
    )
    assert (tmp_path / "runs" / "run-worker" / "diff-summary.txt").read_text() == (
        "src/success.py\n"
    )
    jsonl = (tmp_path / "runs" / "run-worker" / "events.jsonl").read_text()
    assert "assistant.step" in jsonl
    assert "codex_exec.completed" in jsonl


def test_codex_exec_backend_launch_failure_preserves_process_evidence(tmp_path):
    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        if argv == ("C:/Tools/codex.exe", "--version"):
            return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")
        events_file = tmp_path / "runs" / "run-worker" / "events.jsonl"
        events_file.parent.mkdir(parents=True, exist_ok=True)
        events_file.write_text('{"event":"assistant.error"}\n', encoding="utf-8")
        (tmp_path / "runs" / "run-worker" / "diff-summary.txt").write_text(
            "src/failure.py\n",
            encoding="utf-8",
        )
        return CommandExecutionResult(exit_code=42, stdout="partial\n", stderr="boom\n")

    request = _codex_exec_request(tmp_path)

    result = CodexExecBackend(
        codex_executable="C:/Tools/codex.exe",
        command_runner=runner,
        launch_enabled=True,
    ).run(request)

    assert result.status == "failed"
    assert result.exit_code == 42
    assert result.failure_class == "codex_exec_failed"
    assert result.metadata["launch_decision"] == "exec_failed"
    assert (tmp_path / "runs" / "run-worker" / "stdout.txt").read_text() == "partial\n"
    assert (tmp_path / "runs" / "run-worker" / "stderr.txt").read_text() == "boom\n"
    assert (tmp_path / "runs" / "run-worker" / "final-message.txt").read_text() == (
        "Codex Exec failed with exit code 42.\n"
    )
    assert (tmp_path / "runs" / "run-worker" / "diff-summary.txt").read_text() == (
        "src/failure.py\n"
    )
    jsonl = (tmp_path / "runs" / "run-worker" / "events.jsonl").read_text()
    assert "assistant.error" in jsonl
    assert "codex_exec.failed" in jsonl


def test_codex_exec_backend_launch_missing_result_preserves_evidence(tmp_path):
    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        if argv == ("C:/Tools/codex.exe", "--version"):
            return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")
        return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")

    request = _codex_exec_request(tmp_path)

    result = CodexExecBackend(
        codex_executable="C:/Tools/codex.exe",
        command_runner=runner,
        launch_enabled=True,
    ).run(request)

    assert result.status == "failed"
    assert result.failure_class == "worker_result_missing"
    assert result.metadata["launch_decision"] == "worker_result_missing"
    assert (tmp_path / "runs" / "run-worker" / "stdout.txt").read_text() == ("codex 1.2.3\n")
    assert (tmp_path / "runs" / "run-worker" / "final-message.txt").read_text() == (
        "Codex Exec completed without a Worker Result JSON artifact.\n"
    )
    assert (
        "codex_exec.worker_result_missing"
        in (tmp_path / "runs" / "run-worker" / "events.jsonl").read_text()
    )


def _codex_exec_request(tmp_path, **overrides) -> WorkerLaunchRequest:
    values = {
        "worker_run_id": "run-worker",
        "task_id": "task-worker",
        "repo_root": tmp_path,
        "worktree_path": tmp_path,
        "result_path": "artifacts/run-worker/worker-result.raw.json",
        "prompt_path": "runs/run-worker/prompt.md",
        "jsonl_path": "runs/run-worker/events.jsonl",
        "stdout_path": "runs/run-worker/stdout.txt",
        "stderr_path": "runs/run-worker/stderr.txt",
        "final_message_path": "runs/run-worker/final-message.txt",
        "diff_summary_path": "runs/run-worker/diff-summary.txt",
        "result_schema_path": "schemas/worker-result.schema.json",
        "prompt": "Do the slice.",
        "rendered_goal_contract": "Goal Contract",
        "sandbox_mode": "workspace-write",
        "approval_policy": "never",
        "allowed_paths": ("src/**",),
        "verification_commands": ("python -B -m pytest -p no:cacheprovider",),
        "acceptance_criteria": ("Criterion passes.",),
    }
    values.update(overrides)
    return WorkerLaunchRequest(**values)
