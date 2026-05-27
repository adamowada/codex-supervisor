from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import codex_supervisor.worker_backends as worker_backends
from codex_supervisor.worker_backends import (
    CodexExecBackend,
    CommandExecutionResult,
    ContractWorkerBackend,
    WorkerLaunchRequest,
    _default_command_runner,
    _minimal_process_environment,
)


def test_contract_worker_backend_emits_contract_compatible_result(tmp_path):
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
        evidence_manifest_path="artifacts/run-worker/evidence-manifest.json",
        result_schema_path="schemas/worker-result.schema.json",
        prompt="Do the slice.",
        rendered_goal_contract="Goal Contract",
        sandbox_mode="workspace-write",
        approval_policy="never",
        allowed_paths=("src/**",),
        verification_commands=("python -B -m pytest -p no:cacheprovider",),
        acceptance_criteria=("Criterion passes.",),
    )

    result = ContractWorkerBackend(changed_files=("src/worker.py",)).run(request)

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
        "Contract worker completed the requested slice.\n"
    )
    assert (tmp_path / "runs" / "run-worker" / "stderr.txt").read_text() == ""
    assert (tmp_path / "runs" / "run-worker" / "diff-summary.txt").read_text() == (
        "src/worker.py\n"
    )
    manifest = json.loads(
        (tmp_path / "artifacts" / "run-worker" / "evidence-manifest.json").read_text()
    )
    assert manifest["paths"]["raw_result"]["exists"] is True
    assert (
        result.metadata["evidence_manifest_path"] == "artifacts/run-worker/evidence-manifest.json"
    )


def test_contract_worker_backend_can_return_failure_without_result_file(tmp_path):
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
        evidence_manifest_path="artifacts/run-worker/evidence-manifest.json",
        result_schema_path="schemas/worker-result.schema.json",
        prompt="Do the slice.",
        rendered_goal_contract="Goal Contract",
        sandbox_mode="workspace-write",
        approval_policy="never",
        allowed_paths=("src/**",),
        verification_commands=("python -B -m pytest -p no:cacheprovider",),
        acceptance_criteria=("Criterion passes.",),
    )

    result = ContractWorkerBackend(
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
        "Contract worker failed: codex_cli_unavailable\n"
    )
    assert (
        "contract_worker.failed" in (tmp_path / "runs" / "run-worker" / "events.jsonl").read_text()
    )


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
        reasoning_effort="high",
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
        str(tmp_path / "runs/run-worker/worker-result.schema.json"),
        "--output-last-message",
        str(tmp_path / "runs/run-worker/final-message.txt"),
        "--sandbox",
        "workspace-write",
        "--cd",
        str(tmp_path),
        "--model",
        "gpt-test",
        "-c",
        'model_reasoning_effort="high"',
        "-c",
        'approval_policy="never"',
        "--ignore-user-config",
        "-",
    )
    assert preflight.metadata["argv"][0] == "<local-path:codex.exe>"
    assert preflight.metadata["argv"][-1] == "-"
    assert "Do the slice." not in preflight.metadata["argv"]
    assert preflight.metadata["codex_home"] == "<codex-home>"
    assert preflight.metadata["goal_mode_decision"] == "prompt_rendered_fallback"
    assert preflight.metadata["prompt_transport"] == "stdin"
    assert len(preflight.metadata["prompt_sha256"]) == 64
    assert preflight.metadata["environment_keys"] == ["CODEX_HOME"]
    assert preflight.metadata["raw_evidence_paths"] == {
        "prompt": "runs/run-worker/prompt.md",
        "jsonl": "runs/run-worker/events.jsonl",
        "stdout": "runs/run-worker/stdout.txt",
        "stderr": "runs/run-worker/stderr.txt",
        "final_message": "runs/run-worker/final-message.txt",
        "diff_summary": "runs/run-worker/diff-summary.txt",
        "result": "artifacts/run-worker/worker-result.raw.json",
        "evidence_manifest": "artifacts/run-worker/evidence-manifest.json",
    }
    assert preflight.metadata["capability_mappings"]["reasoning_effort"] == {
        "requested": "high",
        "transport": "config_override",
        "codex_config_key": "model_reasoning_effort",
        "fallback": "retry_without_reasoning_effort_when_cli_rejects_mapping",
    }
    assert preflight.metadata["version_gated_options"] == [
        "model",
        "reasoning_effort_config",
        "config",
    ]


def test_codex_exec_backend_prefers_windows_cmd_when_bare_codex_is_requested(
    tmp_path,
    monkeypatch,
):
    calls: list[tuple[str, ...]] = []

    def fake_which(candidate: str) -> str | None:
        return {
            "codex.cmd": "C:/Tools/codex.cmd",
            "codex": "C:/Tools/codex.ps1",
        }.get(candidate)

    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        calls.append(argv)
        return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")

    monkeypatch.setattr(worker_backends.os, "name", "nt")
    monkeypatch.setattr(worker_backends.shutil, "which", fake_which)

    preflight = CodexExecBackend(codex_executable="codex", command_runner=runner).preflight(
        _codex_exec_request(tmp_path)
    )

    assert calls == [("C:/Tools/codex.cmd", "--version")]
    assert preflight.executable_path == "C:/Tools/codex.cmd"
    assert preflight.resolution_method == "configured_path_windows_cmd"
    assert preflight.failure_class is None


def test_codex_exec_backend_rejects_configured_powershell_shim_without_launching(tmp_path):
    calls: list[tuple[str, ...]] = []

    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        calls.append(argv)
        return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")

    result = CodexExecBackend(
        codex_executable="C:/Tools/codex.ps1",
        command_runner=runner,
    ).run(_codex_exec_request(tmp_path))

    assert calls == []
    assert result.status == "failed"
    assert result.failure_class == "codex_cli_unavailable"
    assert "PowerShell .ps1 shim" in (tmp_path / "runs/run-worker/stderr.txt").read_text()


def test_codex_exec_backend_fails_closed_for_unsupported_options(tmp_path):
    calls: list[tuple[str, ...]] = []

    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        calls.append(argv)
        return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")

    request = _codex_exec_request(
        tmp_path,
        service_tier="flex",
        native_goal_mode=True,
    )

    preflight = CodexExecBackend(
        codex_executable="C:/Tools/codex.exe",
        command_runner=runner,
    ).preflight(request)

    assert calls == []
    assert preflight.failure_class == "codex_launch_option_unsupported"
    assert "reasoning_effort" not in preflight.version_stderr
    assert "service_tier" in preflight.version_stderr
    assert "native_goal_mode" in preflight.version_stderr


def test_default_command_runner_preserves_raw_bytes_and_decodes_for_display(tmp_path):
    result = _default_command_runner(
        (
            sys.executable,
            "-c",
            (
                "import sys; "
                "sys.stdout.buffer.write(b'hello\\xff'); "
                "sys.stderr.buffer.write(b'err\\xfe')"
            ),
        ),
        tmp_path,
        {},
    )

    assert result.exit_code == 0
    assert result.stdout == "hello\ufffd"
    assert result.stderr == "err\ufffd"
    assert result.stdout_bytes == b"hello\xff"
    assert result.stderr_bytes == b"err\xfe"


def test_codex_exec_backend_fails_closed_for_unapplied_config_path(tmp_path):
    calls: list[tuple[str, ...]] = []

    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        calls.append(argv)
        return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")

    request = _codex_exec_request(
        tmp_path,
        codex_config_path="C:/codex-home/config.toml",
    )

    preflight = CodexExecBackend(
        codex_executable="C:/Tools/codex.exe",
        command_runner=runner,
    ).preflight(request)

    assert calls == []
    assert preflight.failure_class == "codex_launch_option_unsupported"
    assert "codex_config_path_without_codex_home" in preflight.version_stderr


def test_codex_exec_backend_fails_closed_for_mismatched_config_path(tmp_path):
    calls: list[tuple[str, ...]] = []

    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        calls.append(argv)
        return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")

    request = _codex_exec_request(
        tmp_path,
        codex_home="C:/codex-home",
        codex_config_path="C:/other-codex-home/config.toml",
    )

    preflight = CodexExecBackend(
        codex_executable="C:/Tools/codex.exe",
        command_runner=runner,
    ).preflight(request)

    assert calls == []
    assert preflight.failure_class == "codex_launch_option_unsupported"
    assert "codex_config_path" in preflight.version_stderr


def test_codex_exec_backend_uses_absolute_paths_for_relative_repo_request(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    worktree = tmp_path / "worktrees" / "run-worker"
    worktree.mkdir(parents=True)

    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")

    request = _codex_exec_request(
        Path("."),
        worktree_path=Path("worktrees/run-worker"),
    )

    preflight = CodexExecBackend(
        codex_executable="C:/Tools/codex.exe",
        command_runner=runner,
    ).preflight(request)

    output_schema_path = Path(preflight.argv[4])
    final_message_path = Path(preflight.argv[6])
    cd_path = Path(preflight.argv[10])
    assert output_schema_path.is_absolute()
    assert final_message_path.is_absolute()
    assert cd_path.is_absolute()
    assert output_schema_path == tmp_path / "runs" / "run-worker" / "worker-result.schema.json"
    assert final_message_path == tmp_path / "runs" / "run-worker" / "final-message.txt"
    assert cd_path == worktree


def test_codex_exec_backend_fails_closed_on_codex_home_environment_conflict(tmp_path):
    calls: list[tuple[str, ...]] = []

    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        calls.append(argv)
        return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")

    request = _codex_exec_request(
        tmp_path,
        codex_home="C:/intended-codex-home",
        environment={"CODEX_HOME": "C:/other-codex-home"},
    )

    result = CodexExecBackend(
        codex_executable="C:/Tools/codex.exe",
        command_runner=runner,
    ).run(request)

    assert calls == []
    assert result.status == "failed"
    assert result.failure_class == "codex_home_conflict"
    assert "codex_home conflicts" in (tmp_path / "runs" / "run-worker" / "stderr.txt").read_text()


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
    prompt = (tmp_path / "runs" / "run-worker" / "prompt.md").read_text()
    assert "# Goal Contract" in prompt
    assert "Do the slice." in prompt
    assert "Worker Result JSON" in prompt
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
        _write_valid_worker_result(
            tmp_path,
            worker_run_id="run-worker",
            changed_file="src/success.py",
        )
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
    assert calls[1][-1] == "-"
    assert result.status == "completed"
    assert result.result_path == "artifacts/run-worker/worker-result.raw.json"
    assert result.failure_class is None
    assert result.metadata["launch_decision"] == "executed"
    assert (
        result.metadata["evidence_manifest_path"] == "artifacts/run-worker/evidence-manifest.json"
    )
    assert (tmp_path / "artifacts" / "run-worker" / "evidence-manifest.json").exists()
    assert (
        result.metadata["raw_evidence_paths"]["result"]
        == "artifacts/run-worker/worker-result.raw.json"
    )
    assert (tmp_path / "runs" / "run-worker" / "stdout.txt").read_text() == ('{"event":"done"}\n')
    schema = json.loads(
        (tmp_path / "runs" / "run-worker" / "worker-result.schema.json").read_text()
    )
    assert schema["additionalProperties"] is False
    assert "worker_run_ids" not in schema["properties"]
    assert schema["properties"]["tests_run"]["items"]["additionalProperties"] is False
    assert schema["properties"]["browser_smoke_results"]["items"]["additionalProperties"] is False
    assert "browser_smoke_results" in schema["required"]
    assert set(schema["properties"]["browser_smoke_results"]["items"]["required"]) == {
        "artifact",
        "command",
        "exit_code",
        "status",
        "summary",
        "tool",
        "url",
    }
    assert (
        schema["properties"]["acceptance_results"]["properties"]["Criterion passes."][
            "additionalProperties"
        ]
        is False
    )
    final_payload = json.loads((tmp_path / "runs" / "run-worker" / "final-message.txt").read_text())
    assert final_payload["worker_run_id"] == "run-worker"
    assert result.metadata["worker_result_source"] == "output_last_message"
    assert (tmp_path / "runs" / "run-worker" / "diff-summary.txt").read_text() == (
        "src/success.py\n"
    )
    jsonl = (tmp_path / "runs" / "run-worker" / "events.jsonl").read_text()
    assert "assistant.step" in jsonl
    assert "codex_exec.completed" in jsonl


def test_codex_exec_backend_copies_worker_support_artifacts_from_worktree(tmp_path):
    worktree = tmp_path / "worktrees" / "run-worker"

    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        if argv == ("C:/Tools/codex.exe", "--version"):
            return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")
        assert cwd == worktree
        (worktree / "src").mkdir(parents=True)
        (worktree / "src" / "success.py").write_text("print('ok')\n", encoding="utf-8")
        smoke_path = worktree / "artifacts" / "browser" / "smoke.png"
        smoke_path.parent.mkdir(parents=True)
        smoke_path.write_bytes(b"png")
        payload = _worker_result_payload(worker_run_id="run-worker", changed_file="src/success.py")
        payload["artifacts"] = ["artifacts/browser/smoke.png"]
        payload["browser_smoke_results"] = [
            {
                "artifact": "artifacts/browser/smoke.png",
                "command": "node tests/browser-smoke.mjs",
                "exit_code": 0,
                "status": "passed",
                "summary": "Smoke passed.",
                "tool": "playwright",
                "url": "http://127.0.0.1:5173",
            }
        ]
        final_file = tmp_path / "runs" / "run-worker" / "final-message.txt"
        final_file.parent.mkdir(parents=True, exist_ok=True)
        final_file.write_text(json.dumps(payload), encoding="utf-8")
        (tmp_path / "runs" / "run-worker" / "events.jsonl").write_text(
            '{"event":"assistant.step"}\n',
            encoding="utf-8",
        )
        (tmp_path / "runs" / "run-worker" / "diff-summary.txt").write_text(
            "src/success.py\n",
            encoding="utf-8",
        )
        return CommandExecutionResult(exit_code=0, stdout='{"event":"done"}\n')

    request = _codex_exec_request(tmp_path, worktree_path=worktree)

    result = CodexExecBackend(
        codex_executable="C:/Tools/codex.exe",
        command_runner=runner,
        launch_enabled=True,
    ).run(request)

    assert result.status == "completed"
    assert (tmp_path / "artifacts" / "browser" / "smoke.png").read_bytes() == b"png"


def test_codex_exec_backend_fails_closed_when_custom_result_schema_is_missing(tmp_path):
    calls: list[tuple[str, ...]] = []

    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        calls.append(argv)
        return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")

    request = _codex_exec_request(
        tmp_path,
        result_schema_path="schemas/worker-result.schema.json",
    )

    result = CodexExecBackend(
        codex_executable="C:/Tools/codex.exe",
        command_runner=runner,
        launch_enabled=True,
    ).run(request)

    assert calls == [("C:/Tools/codex.exe", "--version")]
    assert result.status == "failed"
    assert result.failure_class == "worker_result_schema_unavailable"
    assert result.metadata["launch_decision"] == "result_schema_unavailable"
    assert not (tmp_path / "schemas" / "worker-result.schema.json").exists()


def test_codex_exec_backend_launch_success_requires_valid_worker_result(tmp_path):
    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        if argv == ("C:/Tools/codex.exe", "--version"):
            return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")
        final_file = tmp_path / "runs" / "run-worker" / "final-message.txt"
        final_file.parent.mkdir(parents=True, exist_ok=True)
        final_file.write_text('{"status":"completed"}\n', encoding="utf-8")
        return CommandExecutionResult(exit_code=0, stdout='{"event":"done"}\n')

    request = _codex_exec_request(tmp_path)

    result = CodexExecBackend(
        codex_executable="C:/Tools/codex.exe",
        command_runner=runner,
        launch_enabled=True,
    ).run(request)

    assert result.status == "failed"
    assert result.failure_class == "worker_result_invalid"
    assert result.metadata["launch_decision"] == "worker_result_invalid"
    assert (tmp_path / "runs" / "run-worker" / "final-message.txt").read_text() == (
        '{"status":"completed"}\n'
    )


def test_codex_exec_backend_blocks_completion_on_malformed_jsonl(tmp_path):
    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        if argv == ("C:/Tools/codex.exe", "--version"):
            return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")
        _write_valid_worker_result(
            tmp_path,
            worker_run_id="run-worker",
            changed_file="src/success.py",
        )
        return CommandExecutionResult(exit_code=0, stdout="not-jsonl\n")

    result = CodexExecBackend(
        codex_executable="C:/Tools/codex.exe",
        command_runner=runner,
        launch_enabled=True,
    ).run(_codex_exec_request(tmp_path))

    assert result.status == "failed"
    assert result.failure_class == "jsonl_malformed"
    assert result.metadata["jsonl_validation"]["line"] == 1


def test_codex_exec_backend_allows_explicit_degraded_jsonl(tmp_path):
    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        if argv == ("C:/Tools/codex.exe", "--version"):
            return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")
        _write_valid_worker_result(
            tmp_path,
            worker_run_id="run-worker",
            changed_file="src/success.py",
        )
        return CommandExecutionResult(exit_code=0, stdout="not-jsonl\n")

    result = CodexExecBackend(
        codex_executable="C:/Tools/codex.exe",
        command_runner=runner,
        launch_enabled=True,
    ).run(_codex_exec_request(tmp_path, allow_degraded_jsonl=True))

    assert result.status == "completed"
    assert result.metadata["jsonl_required"] is False


def test_codex_exec_backend_launch_timeout_preserves_timeout_evidence(tmp_path):
    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        if argv == ("C:/Tools/codex.exe", "--version"):
            return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")
        raise subprocess.TimeoutExpired(argv, 5, output='{"event":"partial"}\n')

    request = _codex_exec_request(tmp_path, launch_timeout_seconds=5.0)

    result = CodexExecBackend(
        codex_executable="C:/Tools/codex.exe",
        command_runner=runner,
        launch_enabled=True,
    ).run(request)

    assert result.status == "failed"
    assert result.exit_code == 124
    assert result.failure_class == "codex_exec_timeout"
    assert "timed out after 5" in (tmp_path / "runs" / "run-worker" / "stderr.txt").read_text()
    assert "codex_exec.timeout" in (tmp_path / "runs" / "run-worker" / "events.jsonl").read_text()


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


def test_codex_exec_backend_retries_with_cli_defaults_when_model_is_rejected(tmp_path):
    calls: list[tuple[str, ...]] = []

    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        calls.append(argv)
        if argv == ("C:/Tools/codex.exe", "--version"):
            return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")
        if "--model" in argv:
            return CommandExecutionResult(
                exit_code=1,
                stderr="invalid_request_error: model gpt-5 is not supported\n",
            )
        if "--output-schema" not in argv:
            return CommandExecutionResult(exit_code=0, stdout='{"event":"probe.ok"}\n')
        _write_valid_worker_result(
            tmp_path,
            worker_run_id="run-worker",
            changed_file="src/success.py",
        )
        (tmp_path / "runs" / "run-worker" / "events.jsonl").write_text(
            '{"event":"assistant.step"}\n',
            encoding="utf-8",
        )
        (tmp_path / "runs" / "run-worker" / "diff-summary.txt").write_text(
            "src/success.py\n",
            encoding="utf-8",
        )
        return CommandExecutionResult(exit_code=0, stdout='{"event":"done"}\n')

    request = _codex_exec_request(tmp_path, model="gpt-5")

    result = CodexExecBackend(
        codex_executable="C:/Tools/codex.exe",
        command_runner=runner,
        launch_enabled=True,
    ).run(request)

    exec_calls = [argv for argv in calls if len(argv) > 1 and argv[1] == "exec"]
    assert len(exec_calls) == 3
    assert "--model" in exec_calls[0]
    assert "--model" not in exec_calls[1]
    assert "--model" not in exec_calls[2]
    assert result.status == "completed"
    assert result.metadata["capability_preflight"]["status"] == "fallback_resolved"
    assert result.metadata["capability_preflight"]["removed_options"] == ["model"]
    assert result.metadata["requested_capabilities"]["model"] == "gpt-5"
    assert result.metadata["resolved_capabilities"]["model"] is None
    assert "capability_retry" not in result.metadata


def test_codex_exec_backend_retries_without_reasoning_mapping_when_cli_rejects_it(tmp_path):
    calls: list[tuple[str, ...]] = []

    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        calls.append(argv)
        if argv == ("C:/Tools/codex.exe", "--version"):
            return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")
        if any("model_reasoning_effort" in item for item in argv):
            return CommandExecutionResult(
                exit_code=1,
                stderr="unsupported config key model_reasoning_effort\n",
            )
        if "--output-schema" not in argv:
            return CommandExecutionResult(exit_code=0, stdout='{"event":"probe.ok"}\n')
        _write_valid_worker_result(
            tmp_path,
            worker_run_id="run-worker",
            changed_file="src/success.py",
        )
        (tmp_path / "runs" / "run-worker" / "events.jsonl").write_text(
            '{"event":"assistant.step"}\n',
            encoding="utf-8",
        )
        (tmp_path / "runs" / "run-worker" / "diff-summary.txt").write_text(
            "src/success.py\n",
            encoding="utf-8",
        )
        return CommandExecutionResult(exit_code=0, stdout='{"event":"done"}\n')

    request = _codex_exec_request(tmp_path, reasoning_effort="high")

    result = CodexExecBackend(
        codex_executable="C:/Tools/codex.exe",
        command_runner=runner,
        launch_enabled=True,
    ).run(request)

    exec_calls = [argv for argv in calls if len(argv) > 1 and argv[1] == "exec"]
    assert len(exec_calls) == 3
    assert any("model_reasoning_effort" in item for item in exec_calls[0])
    assert not any("model_reasoning_effort" in item for item in exec_calls[1])
    assert not any("model_reasoning_effort" in item for item in exec_calls[2])
    assert result.status == "completed"
    assert result.metadata["capability_preflight"]["status"] == "fallback_resolved"
    assert result.metadata["capability_preflight"]["removed_options"] == ["reasoning_effort"]
    assert result.metadata["requested_capabilities"]["reasoning_effort"] == "high"
    assert result.metadata["resolved_capabilities"]["reasoning_effort"] is None
    assert "capability_retry" not in result.metadata


def test_codex_exec_backend_blocks_on_unknown_capability_probe_failure(tmp_path):
    calls: list[tuple[str, ...]] = []

    def runner(
        argv: tuple[str, ...],
        cwd,
        environment: dict[str, str],
    ) -> CommandExecutionResult:
        calls.append(argv)
        if argv == ("C:/Tools/codex.exe", "--version"):
            return CommandExecutionResult(exit_code=0, stdout="codex 1.2.3\n")
        return CommandExecutionResult(exit_code=1, stderr="authentication failed\n")

    request = _codex_exec_request(tmp_path, model="gpt-5")

    result = CodexExecBackend(
        codex_executable="C:/Tools/codex.exe",
        command_runner=runner,
        launch_enabled=True,
    ).run(request)

    exec_calls = [argv for argv in calls if len(argv) > 1 and argv[1] == "exec"]
    assert len(exec_calls) == 1
    assert result.status == "failed"
    assert result.failure_class == "codex_capability_probe_failed"
    assert result.metadata["capability_preflight"]["status"] == "failed"
    assert result.metadata["resolved_capabilities"]["model"] == "gpt-5"
    assert "authentication failed" in (tmp_path / "runs" / "run-worker" / "stderr.txt").read_text()


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
        "Codex Exec completed without a Worker Result JSON final message.\n"
    )
    assert (
        "codex_exec.worker_result_missing"
        in (tmp_path / "runs" / "run-worker" / "events.jsonl").read_text()
    )


def test_default_process_environment_uses_minimal_allowlist():
    filtered = _minimal_process_environment(
        {
            "Path": "C:/tools",
            "APPDATA": "C:/AppData/Roaming",
            "SYSTEMROOT": "C:/Windows",
            "OPENAI_API_KEY": "sk-redacted",
            "SECRET_TOKEN": "nope",
        }
    )

    assert filtered == {
        "Path": "C:/tools",
        "APPDATA": "C:/AppData/Roaming",
        "SYSTEMROOT": "C:/Windows",
    }


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
        "evidence_manifest_path": "artifacts/run-worker/evidence-manifest.json",
        "result_schema_path": "runs/run-worker/worker-result.schema.json",
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


def _write_valid_worker_result(tmp_path, *, worker_run_id: str, changed_file: str) -> None:
    changed_path = tmp_path / changed_file
    changed_path.parent.mkdir(parents=True, exist_ok=True)
    changed_path.write_text("print('ok')\n", encoding="utf-8")
    result_path = f"artifacts/{worker_run_id}/worker-result.raw.json"
    result_file = tmp_path / result_path
    result_file.parent.mkdir(parents=True, exist_ok=True)
    payload = _worker_result_payload(worker_run_id=worker_run_id, changed_file=changed_file)
    result_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    final_file = tmp_path / "runs" / worker_run_id / "final-message.txt"
    final_file.parent.mkdir(parents=True, exist_ok=True)
    final_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _worker_result_payload(*, worker_run_id: str, changed_file: str) -> dict[str, object]:
    result_path = f"artifacts/{worker_run_id}/worker-result.raw.json"
    return {
        "worker_run_id": worker_run_id,
        "status": "completed",
        "summary": "Worker completed.",
        "changed_files": [changed_file],
        "tests_run": [
            {
                "command": "python -B -m pytest -p no:cacheprovider",
                "exit_code": 0,
                "summary": "passed",
            }
        ],
        "acceptance_results": {
            "Criterion passes.": {
                "status": "passed",
                "evidence": "Verified in test.",
            }
        },
        "risks": [],
        "follow_up_tasks": [],
        "artifacts": [result_path],
        "completion_notes": "Ready.",
    }
