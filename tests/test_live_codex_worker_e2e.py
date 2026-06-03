from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(
    os.environ.get("CODEX_SUPERVISOR_RUN_LIVE_CODEX_E2E") != "1",
    reason="set CODEX_SUPERVISOR_RUN_LIVE_CODEX_E2E=1 to run the live Codex worker e2e",
)
def test_live_codex_exec_worker_can_complete_supervised_project(tmp_path: Path) -> None:
    codex_executable = _resolve_codex_executable()
    workspace = tmp_path / "live-codex-worker-project"
    db_path = workspace / ".codex-supervisor" / "planning.sqlite3"
    project_file = workspace / "README.md"
    verifier_file = workspace / ".codex-supervisor" / "verify.py"

    _run_cli("plan-init", "--path", str(db_path))
    _run_cli(
        "task-create",
        "--path",
        str(db_path),
        "--plan-id",
        "plan-live-codex-worker",
        "--plan-title",
        "Live Codex worker",
        "--plan-goal",
        "Assign one tiny project to a real Codex worker process.",
        "--task-id",
        "task-live-codex-worker",
        "--title",
        "Create README",
        "--intent",
        "Create README.md with exactly '# Live Codex Worker' as the heading.",
        "--assurance",
        "high",
        "--acceptance",
        "README.md has the expected heading",
        "--json",
    )
    _write_text_verifier(
        verifier_file,
        (
            "content = Path('README.md').read_text(encoding='utf-8')\n"
            "if content != '# Live Codex Worker\\n':\n"
            "    raise SystemExit('README.md content mismatch')\n"
            "print('live Codex worker output verified')\n"
        ),
    )

    prompt = (
        "Read CODEX_SUPERVISOR_TASK_JSON. In CODEX_SUPERVISOR_WORKSPACE, create README.md "
        "with exactly this content and trailing newline: # Live Codex Worker"
    )
    completed = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        "task-live-codex-worker",
        "--attempt-id",
        "attempt-live-codex-worker",
        "--executor",
        "codex-exec",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "300",
        "--summary",
        "Assign README creation to a real Codex worker process.",
        "--check",
        "Codex worker created README.md.",
        "--artifact",
        str(project_file),
        "--verify-command",
        _shell_command((sys.executable, "-B", str(verifier_file))),
        "--acceptance-result",
        "pass",
        "--risk",
        "Live Codex worker behavior depends on the installed Codex CLI.",
        "--gap",
        "No known gap.",
        "--next-action",
        "No next action.",
        "--review-evidence",
        "Verifier proved the live Codex worker artifact.",
        "--json",
        "--",
        *_codex_exec_command(codex_executable, prompt),
    )

    payload = json.loads(completed.stdout)
    assert payload["exit_code"] == 0
    assert payload["verifier_exit_code"] == 0
    assert payload["transition"]["task_status"] == "done"
    assert payload["transition"]["acceptance"]["accepted"] is True
    assert project_file.read_text(encoding="utf-8") == "# Live Codex Worker\n"


def _resolve_codex_executable() -> Path:
    configured = os.environ.get("CODEX_SUPERVISOR_CODEX_EXECUTABLE")
    if configured:
        return Path(configured)
    candidate_names = ("codex.ps1", "codex") if os.name == "nt" else ("codex",)
    for name in candidate_names:
        resolved = shutil.which(name)
        if resolved:
            return Path(resolved)
    pytest.skip(
        "set CODEX_SUPERVISOR_CODEX_EXECUTABLE to the codex or codex.ps1 executable"
    )


def _codex_exec_command(codex_executable: Path, prompt: str) -> tuple[str, ...]:
    if os.name == "nt" and codex_executable.suffix.casefold() == ".ps1":
        return (
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(codex_executable),
            "exec",
            prompt,
        )
    return (str(codex_executable), "exec", prompt)


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (sys.executable, "-B", "-m", "codex_supervisor.cli", *args),
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=360,
        env=_cli_env(),
        check=True,
    )


def _cli_env() -> dict[str, str]:
    env = os.environ.copy()
    src_path = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = (
        src_path if not env.get("PYTHONPATH") else src_path + os.pathsep + env["PYTHONPATH"]
    )
    return env


def _write_text_verifier(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("from pathlib import Path\n" + body, encoding="utf-8")


def _shell_command(args: tuple[str, ...]) -> str:
    return subprocess.list2cmdline(args)
