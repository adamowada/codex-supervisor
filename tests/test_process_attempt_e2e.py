from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_full_afk_process_attempt_starts_tiny_project(tmp_path: Path) -> None:
    db_path = tmp_path / "planning.sqlite3"
    workspace = tmp_path / "tiny-project"
    project_file = workspace / "README.md"
    verifier_file = workspace / ".codex-supervisor" / "verify.py"

    _run_cli("plan-init", "--path", str(db_path))
    _run_cli(
        "task-create",
        "--path",
        str(db_path),
        "--plan-id",
        "plan-afk",
        "--plan-title",
        "AFK project",
        "--plan-goal",
        "Start a tiny project through a generic task intent.",
        "--task-id",
        "task-afk",
        "--title",
        "Create README",
        "--intent",
        "Create a tiny project by writing README.md in the workspace.",
        "--assurance",
        "high",
        "--acceptance",
        "README.md exists",
        "--json",
    )
    _write_text_verifier(
        verifier_file,
        (
            "content = Path('README.md').read_text(encoding='utf-8')\n"
            "if content != '# Tiny Project\\n':\n"
            "    raise SystemExit(3)\n"
            "print('README.md verified')\n"
        ),
    )

    completed = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        "task-afk",
        "--attempt-id",
        "attempt-afk",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "10",
        "--check",
        "README.md exists in workspace",
        "--artifact",
        str(project_file),
        "--verify-command",
        _shell_command((sys.executable, "-B", str(verifier_file))),
        "--acceptance-result",
        "README.md exists=pass",
        "--risk",
        "Worker ran inside an isolated temporary workspace.",
        "--json",
        "--",
        sys.executable,
        "-c",
        (
            "from pathlib import Path; "
            "Path('README.md').write_text('# Tiny Project\\n', encoding='utf-8')"
        ),
    )

    payload = json.loads(completed.stdout)
    assert payload["exit_code"] == 0
    assert payload["verifier_exit_code"] == 0
    assert payload["transition"]["task_status"] == "done"
    assert payload["transition"]["attempt"]["status"] == "succeeded"
    assert payload["transition"]["acceptance"]["accepted"] is True
    assert "verifier exit code: 0" in payload["transition"]["evidence"]["checks"]
    assert project_file.read_text(encoding="utf-8") == "# Tiny Project\n"
    assert Path(payload["stdout_path"]).exists()
    assert Path(payload["stderr_path"]).exists()
    assert Path(payload["verifier_stdout_path"]).exists()
    assert Path(payload["verifier_stderr_path"]).exists()

    queued = json.loads(
        _run_cli("queue-next", "--path", str(db_path), "--json").stdout
    )
    assert queued["task"] is None
    assert queued["next_transition"] == "none"


def test_attempt_run_updates_liveness_while_worker_runs(tmp_path: Path) -> None:
    db_path = tmp_path / ".codex-supervisor" / "planning.sqlite3"
    workspace = tmp_path / "live-worker-project"
    marker = tmp_path / "release-worker"
    output_file = workspace / "done.txt"
    liveness_path = (
        workspace / ".codex-supervisor" / "evidence" / "attempt-live-liveness.json"
    )

    _run_cli("plan-init", "--path", str(db_path))
    _run_cli(
        "task-create",
        "--path",
        str(db_path),
        "--plan-id",
        "plan-live",
        "--plan-title",
        "Live worker",
        "--plan-goal",
        "Observe one autonomous worker while it runs.",
        "--task-id",
        "task-live",
        "--title",
        "Create done file",
        "--intent",
        "Create done.txt after the worker starts.",
        "--assurance",
        "medium",
        "--acceptance",
        "done.txt exists",
        "--json",
    )

    worker_code = (
        "import sys, time\n"
        "from pathlib import Path\n"
        "marker = Path(sys.argv[1])\n"
        "print('worker alive', flush=True)\n"
        "deadline = time.time() + 10\n"
        "while not marker.exists() and time.time() < deadline:\n"
        "    time.sleep(0.05)\n"
        "Path('done.txt').write_text('done\\n', encoding='utf-8')\n"
    )
    process = subprocess.Popen(
        _cli_command(
            "attempt-run",
            "--path",
            str(db_path),
            "--task-id",
            "task-live",
            "--attempt-id",
            "attempt-live",
            "--workspace",
            str(workspace),
            "--timeout-seconds",
            "10",
            "--artifact",
            str(output_file),
            "--acceptance-result",
            "pass",
            "--json",
            "--",
            sys.executable,
            "-c",
            worker_code,
            str(marker),
        ),
        cwd=REPO_ROOT,
        env=_cli_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        live_payload = _wait_for_liveness_output(liveness_path)
        assert live_payload["state"] == "running"
        assert live_payload["last_output_at"] is not None
        assert live_payload["ended_at"] is None
        marker.write_text("release\n", encoding="utf-8")
        stdout, stderr = process.communicate(timeout=15)
    finally:
        if process.poll() is None:
            process.kill()

    assert process.returncode == 0, stderr
    payload = json.loads(stdout)
    assert payload["transition"]["task_status"] == "done"
    assert output_file.read_text(encoding="utf-8") == "done\n"
    final_liveness = json.loads(liveness_path.read_text(encoding="utf-8"))
    assert final_liveness["state"] == "succeeded"
    assert final_liveness["last_output_at"] is not None
    assert final_liveness["ended_at"] is not None


def test_timeout_worker_can_be_accepted_by_verifier_on_original_task(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / ".codex-supervisor" / "planning.sqlite3"
    workspace = tmp_path / "timeout-recovery-project"
    project_file = workspace / "README.md"
    verifier_file = workspace / ".codex-supervisor" / "verify.py"

    _run_cli("plan-init", "--path", str(db_path))
    _run_cli(
        "task-create",
        "--path",
        str(db_path),
        "--plan-id",
        "plan-timeout-recovery",
        "--plan-title",
        "Timeout recovery",
        "--plan-goal",
        "Accept verified product state even when the worker times out.",
        "--task-id",
        "task-timeout-recovery",
        "--title",
        "Create README before hanging",
        "--intent",
        "Create README.md, then simulate a worker that never exits cleanly.",
        "--assurance",
        "high",
        "--acceptance",
        "README.md contains the recovered content",
        "--json",
    )
    _write_text_verifier(
        verifier_file,
        (
            "content = Path('README.md').read_text(encoding='utf-8')\n"
            "if content != '# Recovered\\n':\n"
            "    raise SystemExit(3)\n"
            "print('timeout recovery verified')\n"
        ),
    )

    completed = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        "task-timeout-recovery",
        "--attempt-id",
        "attempt-timeout-recovery",
        "--executor",
        "worker-process",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "2",
        "--summary",
        "Assign work to a worker that hangs after producing valid output.",
        "--artifact",
        str(project_file),
        "--verify-command",
        _shell_command((sys.executable, "-B", str(verifier_file))),
        "--acceptance-result",
        "pass",
        "--risk",
        "Verifier recovery accepted product state on the original task.",
        "--json",
        "--",
        sys.executable,
        "-c",
        (
            "import time\n"
            "from pathlib import Path\n"
            "Path('README.md').write_text('# Recovered\\n', encoding='utf-8')\n"
            "print('wrote README', flush=True)\n"
            "time.sleep(10)\n"
        ),
    )

    payload = json.loads(completed.stdout)
    assert payload["exit_code"] == 124
    assert payload["verifier_exit_code"] == 0
    assert payload["transition"]["task_status"] == "done"
    assert payload["transition"]["attempt"]["status"] == "succeeded"
    assert payload["transition"]["acceptance"]["accepted"] is True
    assert "Timed out after 2 seconds" in payload["transition"]["attempt"]["summary"]
    assert "Verifier exit code: 0" in payload["transition"]["attempt"]["summary"]
    assert project_file.read_text(encoding="utf-8") == "# Recovered\n"
    liveness = json.loads(Path(payload["liveness_path"]).read_text(encoding="utf-8"))
    assert liveness["state"] == "timed_out"
    assert liveness["last_output_at"] is not None
    assert liveness["ended_at"] is not None
    assert _planning_integrity_failures(db_path) == ()


def test_happy_path_plain_pass_records_one_worker_attempt_and_clean_plan(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / ".codex-supervisor" / "planning.sqlite3"
    workspace = tmp_path / "tiny-worker-project"
    project_file = workspace / "README.md"

    _run_cli("plan-init", "--path", str(db_path))
    _run_cli(
        "task-create",
        "--path",
        str(db_path),
        "--plan-id",
        "plan-happy-path",
        "--plan-title",
        "Happy path",
        "--plan-goal",
        "Assign one tiny project to one autonomous worker process.",
        "--task-id",
        "task-happy-path",
        "--title",
        "Create README",
        "--intent",
        "Create README.md in the worker workspace.",
        "--assurance",
        "high",
        "--acceptance",
        "README.md exists",
        "--json",
    )

    completed = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        "task-happy-path",
        "--attempt-id",
        "attempt-happy-path",
        "--executor",
        "worker-process",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "10",
        "--summary",
        "Assign tiny project to worker process.",
        "--check",
        "Worker created README.md.",
        "--artifact",
        str(project_file),
        "--acceptance-result",
        "pass",
        "--risk",
        "Worker ran inside an isolated temporary workspace.",
        "--json",
        "--",
        sys.executable,
        "-c",
        (
            "from pathlib import Path; "
            "Path('README.md').write_text('# Tiny Worker Project\\n', encoding='utf-8')"
        ),
    )

    payload = json.loads(completed.stdout)
    assert payload["exit_code"] == 0
    assert payload["transition"]["task_status"] == "done"
    assert payload["transition"]["acceptance"]["accepted"] is True
    assert project_file.read_text(encoding="utf-8") == "# Tiny Worker Project\n"
    assert Path(payload["assignment_path"]).is_file()
    assert Path(payload["stdout_path"]).is_file()
    assert Path(payload["stderr_path"]).is_file()

    with sqlite3.connect(db_path) as connection:
        plan_status = connection.execute(
            "select status from plans where plan_id = 'plan-happy-path'"
        ).fetchone()[0]
        task_status = connection.execute(
            "select status from tasks where task_id = 'task-happy-path'"
        ).fetchone()[0]
        attempts = connection.execute(
            "select attempt_id, executor, status from attempts order by attempt_id"
        ).fetchall()
        evidence_count = connection.execute("select count(*) from evidence_bundles").fetchone()[0]

    assert plan_status == "done"
    assert task_status == "done"
    assert attempts == [("attempt-happy-path", "worker-process", "succeeded")]
    assert evidence_count == 1
    assert _planning_integrity_failures(db_path) == ()


def test_full_afk_worker_gets_assignment_and_manages_empty_project_end_to_end(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / ".codex-supervisor" / "planning.sqlite3"
    workspace = tmp_path / "empty-worker-project"
    project_file = workspace / "index.html"
    worker_report = workspace / "worker-report.json"

    assert not workspace.exists()

    _run_cli("plan-init", "--path", str(db_path))
    _run_cli(
        "task-create",
        "--path",
        str(db_path),
        "--plan-id",
        "plan-full-afk",
        "--plan-title",
        "Full AFK project",
        "--plan-goal",
        "Start a tiny project by assigning task intent to an autonomous worker.",
        "--task-id",
        "task-full-afk",
        "--title",
        "Create HTML-only hello world site",
        "--intent",
        "Create index.html with visible Hello, world! text and no CSS, JavaScript, or images.",
        "--assurance",
        "high",
        "--acceptance",
        "index.html exists and contains visible Hello, world! text",
        "--acceptance",
        "index.html contains no CSS, JavaScript, or image references",
        "--json",
    )

    completed = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        "task-full-afk",
        "--attempt-id",
        "attempt-full-afk",
        "--executor",
        "worker-process",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "10",
        "--summary",
        "Assign task intent to a worker process to create the project.",
        "--check",
        "Worker read CODEX_SUPERVISOR_TASK_JSON and created index.html.",
        "--check",
        "index.html was inspected for CSS, JavaScript, and image references.",
        "--artifact",
        str(project_file),
        "--artifact",
        str(worker_report),
        "--acceptance-result",
        "index.html exists and contains visible Hello, world! text=pass",
        "--acceptance-result",
        "index.html contains no CSS, JavaScript, or image references=pass",
        "--risk",
        "Worker ran inside an isolated empty workspace and only wrote declared artifacts.",
        "--review-evidence",
        (
            "Supervisor captured stdout, stderr, command metadata, assignment metadata, "
            "and declared artifacts."
        ),
        "--json",
        "--",
        sys.executable,
        "-c",
        _assignment_worker_code(),
    )

    payload = json.loads(completed.stdout)
    assignment_path = Path(payload["assignment_path"])
    evidence_artifacts = payload["transition"]["evidence"]["artifacts"]

    assert payload["exit_code"] == 0
    assert payload["transition"]["task_status"] == "done"
    assert payload["transition"]["attempt"]["status"] == "succeeded"
    assert payload["transition"]["acceptance"]["accepted"] is True
    assert assignment_path.exists()
    assert str(assignment_path) in evidence_artifacts
    assert str(project_file) in evidence_artifacts
    assert str(worker_report) in evidence_artifacts
    html = project_file.read_text(encoding="utf-8")
    assert "Hello, world!" in html
    forbidden_markers = ("<script", "<style", "stylesheet", ".css", "<img", "src=")
    assert all(marker not in html.casefold() for marker in forbidden_markers)

    assignment = json.loads(assignment_path.read_text(encoding="utf-8"))
    assert assignment["task"]["task_id"] == "task-full-afk"
    assert assignment["task"]["assurance"] == "high"
    assert assignment["task"]["acceptance_criteria"] == [
        "index.html exists and contains visible Hello, world! text",
        "index.html contains no CSS, JavaScript, or image references",
    ]
    assert assignment["attempt"]["attempt_id"] == "attempt-full-afk"
    assert assignment["workspace"] == str(workspace.resolve())

    report = json.loads(worker_report.read_text(encoding="utf-8"))
    assert report["assignment_task_id"] == "task-full-afk"
    assert report["assignment_attempt_id"] == "attempt-full-afk"

    with sqlite3.connect(db_path) as connection:
        attempts = connection.execute(
            "select attempt_id, executor, status from attempts"
        ).fetchall()
        evidence_count = connection.execute(
            "select count(*) from evidence_bundles"
        ).fetchone()[0]
    assert attempts == [("attempt-full-afk", "worker-process", "succeeded")]
    assert evidence_count == 1


def test_full_afk_follow_up_product_mutation_is_assigned_to_worker(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / ".codex-supervisor" / "planning.sqlite3"
    workspace = tmp_path / "factory-project"
    project_file = workspace / "README.md"
    verifier_file = workspace / ".codex-supervisor" / "verify.py"

    init = _run_cli("plan-init", "--path", str(db_path), "--json")
    assert json.loads(init.stdout)["schema_version"] == "1"
    _run_cli(
        "task-create",
        "--path",
        str(db_path),
        "--plan-id",
        "plan-factory-build",
        "--plan-title",
        "Factory build",
        "--plan-goal",
        "Create the initial product artifact through a worker.",
        "--task-id",
        "task-build-readme",
        "--title",
        "Create README",
        "--intent",
        "Create README.md in the worker workspace.",
        "--assurance",
        "high",
        "--acceptance",
        "README.md exists",
        "--json",
    )

    first = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        "task-build-readme",
        "--attempt-id",
        "attempt-build-readme",
        "--executor",
        "worker-process",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "10",
        "--summary",
        "Assign initial product file creation to a worker.",
        "--check",
        "Worker created README.md.",
        "--artifact",
        str(project_file),
        "--acceptance-result",
        "pass",
        "--risk",
        "Worker ran inside an isolated temporary workspace.",
        "--json",
        "--",
        sys.executable,
        "-c",
        (
            "from pathlib import Path; "
            "Path('README.md').write_text('# Factory Project\\n', encoding='utf-8')"
        ),
    )
    assert json.loads(first.stdout)["transition"]["task_status"] == "done"

    _run_cli(
        "task-create",
        "--path",
        str(db_path),
        "--plan-id",
        "plan-factory-follow-up",
        "--plan-title",
        "Factory follow-up",
        "--plan-goal",
        "Apply discovered product cleanup through a worker.",
        "--task-id",
        "task-update-readme",
        "--title",
        "Update README",
        "--intent",
        "Add a local verification note to README.md.",
        "--assurance",
        "high",
        "--acceptance",
        "README.md contains the local verification note",
        "--json",
    )
    _write_text_verifier(
        verifier_file,
        (
            "content = Path('README.md').read_text(encoding='utf-8')\n"
            "if 'Verified locally by worker.\\n' not in content:\n"
            "    raise SystemExit(3)\n"
            "print('follow-up verified')\n"
        ),
    )

    follow_up = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        "task-update-readme",
        "--attempt-id",
        "attempt-update-readme",
        "--executor",
        "worker-process",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "10",
        "--summary",
        "Assign product follow-up mutation to a worker.",
        "--check",
        "Worker added the local verification note.",
        "--artifact",
        str(project_file),
        "--verify-command",
        _shell_command((sys.executable, "-B", str(verifier_file))),
        "--acceptance-result",
        "pass",
        "--risk",
        "Follow-up work used a worker attempt instead of supervisor product edits.",
        "--json",
        "--",
        sys.executable,
        "-c",
        (
            "from pathlib import Path; "
            "Path('README.md').write_text("
            "Path('README.md').read_text(encoding='utf-8') + "
            "'Verified locally by worker.\\n', encoding='utf-8')"
        ),
    )

    payload = json.loads(follow_up.stdout)
    assert payload["exit_code"] == 0
    assert payload["verifier_exit_code"] == 0
    assert payload["transition"]["task_status"] == "done"
    assert project_file.read_text(encoding="utf-8") == (
        "# Factory Project\nVerified locally by worker.\n"
    )

    with sqlite3.connect(db_path) as connection:
        attempts = connection.execute(
            "select attempt_id, executor, status from attempts order by attempt_id"
        ).fetchall()
        plans = connection.execute(
            "select plan_id, status from plans order by plan_id"
        ).fetchall()
        evidence_count = connection.execute("select count(*) from evidence_bundles").fetchone()[0]

    assert attempts == [
        ("attempt-build-readme", "worker-process", "succeeded"),
        ("attempt-update-readme", "worker-process", "succeeded"),
    ]
    assert plans == [
        ("plan-factory-build", "done"),
        ("plan-factory-follow-up", "done"),
    ]
    assert evidence_count == 2
    assert _planning_integrity_failures(db_path) == ()


def test_failed_process_attempt_records_terminal_state(tmp_path: Path) -> None:
    db_path = tmp_path / "planning.sqlite3"
    workspace = tmp_path / "failed-project"

    _run_cli("plan-init", "--path", str(db_path))
    _run_cli(
        "task-create",
        "--path",
        str(db_path),
        "--plan-id",
        "plan-afk",
        "--plan-title",
        "AFK project",
        "--plan-goal",
        "Record failed process attempts durably.",
        "--task-id",
        "task-failed",
        "--title",
        "Fail command",
        "--intent",
        "Run a worker command that fails.",
        "--assurance",
        "medium",
        "--acceptance",
        "Command succeeds",
        "--json",
    )

    completed = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        "task-failed",
        "--attempt-id",
        "attempt-failed",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "10",
        "--json",
        "--",
        sys.executable,
        "-c",
        "raise SystemExit(7)",
    )

    payload = json.loads(completed.stdout)
    assert payload["exit_code"] == 7
    assert payload["transition"]["task_status"] == "blocked"
    assert payload["transition"]["attempt"]["status"] == "failed"
    assert payload["transition"]["acceptance"]["accepted"] is False
    assert Path(payload["stdout_path"]).exists()
    assert Path(payload["stderr_path"]).exists()
    assert _planning_integrity_failures(db_path) == ()


def test_missing_worker_command_records_terminal_state(tmp_path: Path) -> None:
    db_path = tmp_path / "planning.sqlite3"
    workspace = tmp_path / "missing-worker-project"

    _run_cli("plan-init", "--path", str(db_path))
    _run_cli(
        "task-create",
        "--path",
        str(db_path),
        "--plan-id",
        "plan-missing-worker",
        "--plan-title",
        "Missing worker",
        "--plan-goal",
        "Record spawn failures durably.",
        "--task-id",
        "task-missing-worker",
        "--title",
        "Run missing worker",
        "--intent",
        "Run a worker command that cannot be started.",
        "--assurance",
        "medium",
        "--acceptance",
        "Worker command starts",
        "--json",
    )

    completed = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        "task-missing-worker",
        "--attempt-id",
        "attempt-missing-worker",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "10",
        "--json",
        "--",
        "definitely-not-a-real-worker-command-for-codex-supervisor",
    )

    payload = json.loads(completed.stdout)
    assert payload["exit_code"] == 1
    assert payload["transition"]["task_status"] == "blocked"
    assert payload["transition"]["attempt"]["status"] == "failed"
    assert payload["transition"]["acceptance"]["accepted"] is False
    assert "Could not start worker process" in payload["transition"]["attempt"]["summary"]
    assert _planning_integrity_failures(db_path) == ()


def test_verifier_failure_blocks_supplied_passing_acceptance(tmp_path: Path) -> None:
    db_path = tmp_path / "planning.sqlite3"
    workspace = tmp_path / "bad-content-project"
    project_file = workspace / "index.html"
    verifier_file = workspace / ".codex-supervisor" / "verify.py"

    _run_cli("plan-init", "--path", str(db_path))
    _run_cli(
        "task-create",
        "--path",
        str(db_path),
        "--plan-id",
        "plan-verifier-failure",
        "--plan-title",
        "Verifier failure",
        "--plan-goal",
        "Reject caller optimism when machine verification fails.",
        "--task-id",
        "task-verifier-failure",
        "--title",
        "Create plain HTML",
        "--intent",
        "Create index.html with a heading and no CSS.",
        "--assurance",
        "high",
        "--acceptance",
        "index.html contains no CSS",
        "--json",
    )
    _write_text_verifier(
        verifier_file,
        (
            "html = Path('index.html').read_text(encoding='utf-8').casefold()\n"
            "if '<style' in html:\n"
            "    raise SystemExit(4)\n"
            "print('index.html contains no css')\n"
        ),
    )

    completed = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        "task-verifier-failure",
        "--attempt-id",
        "attempt-verifier-failure",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "10",
        "--check",
        "Caller claimed index.html contains no CSS.",
        "--artifact",
        str(project_file),
        "--verify-command",
        _shell_command((sys.executable, "-B", str(verifier_file))),
        "--acceptance-result",
        "index.html contains no CSS=pass",
        "--risk",
        "Worker ran in an isolated temporary workspace.",
        "--json",
        "--",
        sys.executable,
        "-c",
        "from pathlib import Path; Path('index.html').write_text('<style></style>', encoding='utf-8')",
    )

    payload = json.loads(completed.stdout)
    checks = payload["transition"]["evidence"]["checks"]
    assert payload["exit_code"] == 0
    assert payload["verifier_exit_code"] == 4
    assert payload["transition"]["task_status"] == "blocked"
    assert payload["transition"]["attempt"]["status"] == "failed"
    assert payload["transition"]["acceptance"]["accepted"] is False
    assert payload["transition"]["acceptance"]["failed_acceptance_criteria"] == [
        "index.html contains no CSS"
    ]
    assert "verifier exit code: 4" in checks
    assert "acceptance: index.html contains no CSS = fail" in checks
    assert "acceptance: index.html contains no CSS = pass" not in checks
    assert Path(payload["verifier_stdout_path"]).is_file()
    assert Path(payload["verifier_stderr_path"]).is_file()
    assert _planning_integrity_failures(db_path) == ()


def test_process_attempt_capture_is_utf8_error_tolerant(tmp_path: Path) -> None:
    db_path = tmp_path / "planning.sqlite3"
    workspace = tmp_path / "encoding-project"
    project_file = workspace / "result.txt"
    verifier_file = workspace / ".codex-supervisor" / "verify.py"

    _run_cli("plan-init", "--path", str(db_path))
    _run_cli(
        "task-create",
        "--path",
        str(db_path),
        "--plan-id",
        "plan-encoding",
        "--plan-title",
        "Encoding capture",
        "--plan-goal",
        "Capture worker and verifier output without locale-dependent crashes.",
        "--task-id",
        "task-encoding",
        "--title",
        "Capture output",
        "--intent",
        "Run worker and verifier commands that emit bytes outside valid UTF-8.",
        "--assurance",
        "high",
        "--acceptance",
        "result.txt exists",
        "--json",
    )
    _write_text_verifier(
        verifier_file,
        (
            "import sys\n"
            "content = Path('result.txt').read_text(encoding='utf-8')\n"
            "if content != 'done\\n':\n"
            "    raise SystemExit(4)\n"
            "sys.stdout.buffer.write(b'verifier stdout: \\xff\\n')\n"
            "sys.stderr.buffer.write(b'verifier stderr: \\xfe\\n')\n"
        ),
    )

    completed = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        "task-encoding",
        "--attempt-id",
        "attempt-encoding",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "10",
        "--artifact",
        str(project_file),
        "--verify-command",
        _shell_command((sys.executable, "-B", str(verifier_file))),
        "--acceptance-result",
        "pass",
        "--risk",
        "Output bytes are captured with replacement for invalid UTF-8.",
        "--json",
        "--",
        sys.executable,
        "-c",
        (
            "import sys; "
            "from pathlib import Path; "
            "Path('result.txt').write_text('done\\n', encoding='utf-8'); "
            "sys.stdout.buffer.write(b'worker stdout: \\xff\\n'); "
            "sys.stderr.buffer.write(b'worker stderr: \\xfe\\n')"
        ),
    )

    payload = json.loads(completed.stdout)

    assert payload["exit_code"] == 0
    assert payload["verifier_exit_code"] == 0
    assert payload["transition"]["task_status"] == "done"
    assert payload["transition"]["attempt"]["status"] == "succeeded"
    assert payload["transition"]["acceptance"]["accepted"] is True
    assert "worker stdout: \ufffd" in Path(payload["stdout_path"]).read_text(
        encoding="utf-8"
    )
    assert "worker stderr: \ufffd" in Path(payload["stderr_path"]).read_text(
        encoding="utf-8"
    )
    assert "verifier stdout: \ufffd" in Path(
        payload["verifier_stdout_path"]
    ).read_text(encoding="utf-8")
    assert "verifier stderr: \ufffd" in Path(
        payload["verifier_stderr_path"]
    ).read_text(encoding="utf-8")
    assert _planning_integrity_failures(db_path) == ()


def test_failed_process_attempt_forces_acceptance_results_to_fail(tmp_path: Path) -> None:
    db_path = tmp_path / "planning.sqlite3"
    workspace = tmp_path / "failed-acceptance-project"

    _run_cli("plan-init", "--path", str(db_path))
    _run_cli(
        "task-create",
        "--path",
        str(db_path),
        "--plan-id",
        "plan-afk-failure",
        "--plan-title",
        "AFK failure evidence",
        "--plan-goal",
        "Record honest acceptance evidence for failed worker attempts.",
        "--task-id",
        "task-failed-acceptance",
        "--title",
        "Fail command honestly",
        "--intent",
        "Run a worker command that fails while caller-supplied evidence claims success.",
        "--assurance",
        "medium",
        "--acceptance",
        "Command succeeds",
        "--json",
    )

    completed = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        "task-failed-acceptance",
        "--attempt-id",
        "attempt-failed-acceptance",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "10",
        "--check",
        "Caller declared this check before the process completed.",
        "--artifact",
        str(workspace / "missing.txt"),
        "--acceptance-result",
        "Command succeeds=pass",
        "--json",
        "--",
        sys.executable,
        "-c",
        "raise SystemExit(7)",
    )

    payload = json.loads(completed.stdout)
    checks = payload["transition"]["evidence"]["checks"]
    assert payload["exit_code"] == 7
    assert payload["transition"]["task_status"] == "blocked"
    assert payload["transition"]["acceptance"]["accepted"] is False
    assert payload["transition"]["acceptance"]["failed_acceptance_criteria"] == [
        "Command succeeds"
    ]
    assert "acceptance: Command succeeds = fail" in checks
    assert "acceptance: Command succeeds = pass" not in checks
    assert _planning_integrity_failures(db_path) == ()


def test_missing_declared_artifact_blocks_supplied_passing_acceptance(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "planning.sqlite3"
    workspace = tmp_path / "missing-artifact-project"
    missing_artifact = workspace / "missing.txt"

    _run_cli("plan-init", "--path", str(db_path))
    _run_cli(
        "task-create",
        "--path",
        str(db_path),
        "--plan-id",
        "plan-missing-artifact",
        "--plan-title",
        "Missing artifact",
        "--plan-goal",
        "Worker output artifacts must be proven before acceptance.",
        "--task-id",
        "task-missing-artifact",
        "--title",
        "Require artifact",
        "--intent",
        "Run a worker command that exits cleanly without writing the declared artifact.",
        "--assurance",
        "medium",
        "--acceptance",
        "missing.txt exists",
        "--json",
    )

    completed = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        "task-missing-artifact",
        "--attempt-id",
        "attempt-missing-artifact",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "10",
        "--check",
        "Caller claimed the file exists.",
        "--artifact",
        str(missing_artifact),
        "--acceptance-result",
        "missing.txt exists=pass",
        "--json",
        "--",
        sys.executable,
        "-c",
        "print('worker did not create the declared artifact')",
    )

    payload = json.loads(completed.stdout)
    checks = payload["transition"]["evidence"]["checks"]
    assert payload["exit_code"] == 0
    assert payload["transition"]["task_status"] == "blocked"
    assert payload["transition"]["attempt"]["status"] == "succeeded"
    assert payload["transition"]["acceptance"]["accepted"] is False
    assert "missing.txt exists" in payload["transition"]["acceptance"][
        "failed_acceptance_criteria"
    ]
    assert f"missing artifact: {missing_artifact}" in checks
    assert "acceptance: missing.txt exists = fail" in checks
    assert _planning_integrity_failures(db_path) == ()


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _cli_command(*args),
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=15,
        env=_cli_env(),
        check=True,
    )


def _cli_command(*args: str) -> tuple[str, ...]:
    return (sys.executable, "-B", "-m", "codex_supervisor.cli", *args)


def _cli_env() -> dict[str, str]:
    env = os.environ.copy()
    src_path = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = (
        src_path if not env.get("PYTHONPATH") else src_path + os.pathsep + env["PYTHONPATH"]
    )
    return env


def _wait_for_liveness_output(path: Path) -> dict[str, object]:
    deadline = time.time() + 5
    while time.time() < deadline:
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                time.sleep(0.05)
                continue
            if payload.get("last_output_at") is not None:
                return payload
        time.sleep(0.05)
    raise AssertionError(f"liveness output did not appear at {path}")


def _write_text_verifier(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("from pathlib import Path\n" + body, encoding="utf-8")


def _shell_command(args: tuple[str, ...]) -> str:
    return subprocess.list2cmdline(args)


def _planning_integrity_failures(db_path: Path) -> tuple[str, ...]:
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.check_planning_integrity import check_planning_integrity

    return check_planning_integrity(db_path)


def _assignment_worker_code() -> str:
    return (
        "import json, os\n"
        "from pathlib import Path\n"
        "assignment_path = Path(os.environ['CODEX_SUPERVISOR_TASK_JSON'])\n"
        "assignment = json.loads(assignment_path.read_text(encoding='utf-8'))\n"
        "html = '<!DOCTYPE html>\\n<html lang=\"en\">\\n<head>\\n'\n"
        "html += '  <meta charset=\"utf-8\">\\n  <title>Hello World</title>\\n'\n"
        "html += '</head>\\n<body>\\n  <h1>Hello, world!</h1>\\n</body>\\n</html>\\n'\n"
        "Path('index.html').write_text(html, encoding='utf-8')\n"
        "Path('worker-report.json').write_text(json.dumps({\n"
        "  'assignment_task_id': assignment['task']['task_id'],\n"
        "  'assignment_attempt_id': assignment['attempt']['attempt_id'],\n"
        "}, sort_keys=True), encoding='utf-8')\n"
        "print('created index.html from supervisor assignment')\n"
    )
