from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from codex_supervisor.acp_gate import check_target_workspace_acp_gate

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_acp_gate_accepts_worker_backed_product_change(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init")
    db_path = workspace / ".codex-supervisor" / "planning.sqlite3"
    product_file = workspace / "README.md"

    _run_cli("plan-init", "--path", str(db_path))
    _create_task(db_path)
    completed = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        "task-acp",
        "--attempt-id",
        "attempt-acp",
        "--executor",
        "worker-process",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "10",
        "--summary",
        "Assign README creation to worker.",
        "--check",
        "Worker created README.md.",
        "--artifact",
        str(product_file),
        "--acceptance-result",
        "pass",
        "--risk",
        "No known residual risk.",
        "--gap",
        "No known gap.",
        "--next-action",
        "No next action.",
        "--review-evidence",
        "Worker evidence captured through attempt-run.",
        "--json",
        "--",
        sys.executable,
        "-c",
        "from pathlib import Path; Path('README.md').write_text('# OK\\n', encoding='utf-8')",
    )

    assert json.loads(completed.stdout)["transition"]["task_status"] == "done"
    result = check_target_workspace_acp_gate(workspace)

    assert result.ok is True
    assert result.changed_product_paths == ("README.md",)
    assert result.worker_backed_paths == ("README.md",)
    assert "accepted attempt attempt-acp lacks launch packet hash" in result.warnings
    assert (
        "active plan plan-acp has no open task and no accepted final proof task"
        in result.warnings
    )


def test_acp_gate_accepts_worker_backed_nested_untracked_product_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init")
    db_path = workspace / ".codex-supervisor" / "planning.sqlite3"
    product_file = workspace / "reports" / "summary.md"

    _run_cli("plan-init", "--path", str(db_path))
    _create_task(db_path)
    completed = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        "task-acp",
        "--attempt-id",
        "attempt-acp",
        "--executor",
        "worker-process",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "10",
        "--summary",
        "Assign nested report creation to worker.",
        "--check",
        "Worker created reports/summary.md.",
        "--artifact",
        str(product_file),
        "--acceptance-result",
        "pass",
        "--risk",
        "No known residual risk.",
        "--gap",
        "No known gap.",
        "--next-action",
        "No next action.",
        "--review-evidence",
        "Worker evidence captured through attempt-run.",
        "--json",
        "--",
        sys.executable,
        "-c",
        (
            "from pathlib import Path; "
            "Path('reports/summary.md').parent.mkdir(parents=True, exist_ok=True); "
            "Path('reports/summary.md').write_text('# OK\\n', encoding='utf-8')"
        ),
    )

    assert json.loads(completed.stdout)["transition"]["task_status"] == "done"
    result = check_target_workspace_acp_gate(workspace)

    assert result.ok is True
    assert result.changed_product_paths == ("reports/summary.md",)
    assert result.worker_backed_paths == ("reports/summary.md",)


def test_acp_gate_accepts_attempt_run_captured_product_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init")
    db_path = workspace / ".codex-supervisor" / "planning.sqlite3"

    _run_cli("plan-init", "--path", str(db_path))
    _create_task(db_path)
    completed = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        "task-acp",
        "--attempt-id",
        "attempt-acp",
        "--executor",
        "worker-process",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "10",
        "--summary",
        "Assign unknown product creation to worker.",
        "--check",
        "Worker created product files discovered through git status.",
        "--acceptance-result",
        "pass",
        "--risk",
        "No known residual risk.",
        "--gap",
        "No known gap.",
        "--next-action",
        "No next action.",
        "--review-evidence",
        "Worker evidence captured through attempt-run.",
        "--json",
        "--",
        sys.executable,
        "-c",
        (
            "from pathlib import Path; "
            "Path('README.md').write_text('# OK\\n', encoding='utf-8'); "
            "Path('reports').mkdir(exist_ok=True); "
            "Path('reports/summary.md').write_text('# Summary\\n', encoding='utf-8')"
        ),
    )

    payload = json.loads(completed.stdout)
    assert payload["transition"]["task_status"] == "done"
    assert "README.md" in payload["transition"]["evidence"]["artifacts"]
    assert "reports/summary.md" in payload["transition"]["evidence"]["artifacts"]
    result = check_target_workspace_acp_gate(workspace)

    assert result.ok is True
    assert result.changed_product_paths == ("README.md", "reports/summary.md")
    assert result.worker_backed_paths == ("README.md", "reports/summary.md")


def test_acp_gate_warns_when_shipping_proof_lacks_accepted_evidence(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init")
    db_path = workspace / ".codex-supervisor" / "planning.sqlite3"

    _run_cli("plan-init", "--path", str(db_path))
    _create_task(db_path)
    _run_cli(
        "task-create",
        "--path",
        str(db_path),
        "--plan-id",
        "plan-acp",
        "--plan-title",
        "ACP plan",
        "--plan-goal",
        "Validate ACP.",
        "--task-id",
        "task-proof",
        "--title",
        "Final proof",
        "--intent",
        "Claim durable completion for task-acp.",
        "--assurance",
        "high",
        "--acceptance",
        "Final proof exists",
        "--lineage",
        "shipping_proof_of=task-acp",
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "update tasks set status = 'done' where task_id in ('task-acp', 'task-proof')"
        )

    result = check_target_workspace_acp_gate(workspace)

    assert (
        "active plan plan-acp has no open task and no accepted final proof task"
        in result.warnings
    )


def test_acp_gate_rejects_product_path_dirty_before_attempt_run(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init")
    db_path = workspace / ".codex-supervisor" / "planning.sqlite3"
    product_file = workspace / "README.md"

    _run_cli("plan-init", "--path", str(db_path))
    _create_task(db_path)
    product_file.write_text("# Preexisting direct edit\n", encoding="utf-8")
    completed = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        "task-acp",
        "--attempt-id",
        "attempt-acp",
        "--executor",
        "worker-process",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "10",
        "--summary",
        "Run a worker after the product path is already dirty.",
        "--artifact",
        str(product_file),
        "--acceptance-result",
        "pass",
        "--risk",
        "No known residual risk.",
        "--review-evidence",
        "The worker ran, but the dirty product path predated the worker.",
        "--json",
        "--",
        sys.executable,
        "-c",
        "print('worker made no product change')",
    )

    assert json.loads(completed.stdout)["transition"]["task_status"] == "blocked"
    result = check_target_workspace_acp_gate(workspace)

    assert result.ok is False
    assert result.changed_product_paths == ("README.md",)
    assert result.worker_backed_paths == ()
    assert result.failures == (
        "product paths lack accepted attempt-run worker evidence: README.md",
    )


def test_acp_gate_rejects_rejected_attempt_run_product_change(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init")
    db_path = workspace / ".codex-supervisor" / "planning.sqlite3"
    product_file = workspace / "README.md"

    _run_cli("plan-init", "--path", str(db_path))
    _create_task(db_path)
    completed = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        "task-acp",
        "--attempt-id",
        "attempt-acp",
        "--executor",
        "worker-process",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "10",
        "--summary",
        "Run a worker whose acceptance is rejected.",
        "--artifact",
        str(product_file),
        "--acceptance-result",
        "fail",
        "--risk",
        "Rejected evidence must not satisfy ACP provenance.",
        "--json",
        "--",
        sys.executable,
        "-c",
        "from pathlib import Path; Path('README.md').write_text('# Rejected\\n', encoding='utf-8')",
    )

    assert json.loads(completed.stdout)["transition"]["task_status"] == "blocked"
    result = check_target_workspace_acp_gate(workspace)

    assert result.ok is False
    assert result.changed_product_paths == ("README.md",)
    assert result.worker_backed_paths == ()
    assert result.failures == (
        "product paths lack accepted attempt-run worker evidence: README.md",
    )


def test_acp_gate_rejects_direct_edit_after_accepted_attempt_run(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init")
    db_path = workspace / ".codex-supervisor" / "planning.sqlite3"
    product_file = workspace / "README.md"

    _run_cli("plan-init", "--path", str(db_path))
    _create_task(db_path)
    completed = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        "task-acp",
        "--attempt-id",
        "attempt-acp",
        "--executor",
        "worker-process",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "10",
        "--summary",
        "Assign README creation to worker.",
        "--artifact",
        str(product_file),
        "--acceptance-result",
        "pass",
        "--risk",
        "No known residual risk.",
        "--review-evidence",
        "Worker evidence captured through attempt-run.",
        "--json",
        "--",
        sys.executable,
        "-c",
        "from pathlib import Path; Path('README.md').write_text('# Worker\\n', encoding='utf-8')",
    )
    assert json.loads(completed.stdout)["transition"]["task_status"] == "done"

    product_file.write_text("# Direct edit after worker\n", encoding="utf-8")
    result = check_target_workspace_acp_gate(workspace)

    assert result.ok is False
    assert result.changed_product_paths == ("README.md",)
    assert result.worker_backed_paths == ()
    assert result.failures == (
        "product paths lack accepted attempt-run worker evidence: README.md",
    )


def test_acp_gate_rejects_dirty_linked_worktree_product_changes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    linked = tmp_path / "linked-agent"
    workspace.mkdir()
    _git(workspace, "init")
    db_path = workspace / ".codex-supervisor" / "planning.sqlite3"

    _run_cli("plan-init", "--path", str(db_path))
    _git(workspace, "add", ".gitignore")
    _git(
        workspace,
        "-c",
        "user.email=smoke@example.invalid",
        "-c",
        "user.name=Live Smoke",
        "commit",
        "-m",
        "baseline",
    )
    _git(workspace, "worktree", "add", "-b", "agent-branch", str(linked))
    (linked / "server").mkdir()
    (linked / "server" / "app.js").write_text("console.log('todo')\n", encoding="utf-8")

    result = check_target_workspace_acp_gate(workspace)

    assert result.ok is False
    assert result.failures == (
        f"linked worktree has unintegrated product changes: {linked}: server/app.js",
    )


def test_acp_gate_rejects_direct_product_edit_without_worker_evidence(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init")
    db_path = workspace / ".codex-supervisor" / "planning.sqlite3"

    _run_cli("plan-init", "--path", str(db_path))
    (workspace / "README.md").write_text("# Direct edit\n", encoding="utf-8")

    result = check_target_workspace_acp_gate(workspace)

    assert result.ok is False
    assert result.changed_product_paths == ("README.md",)
    assert result.worker_backed_paths == ()
    assert result.failures == (
        "product paths lack accepted attempt-run worker evidence: README.md",
    )


def test_acp_gate_rejects_attempt_transition_product_artifact(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init")
    db_path = workspace / ".codex-supervisor" / "planning.sqlite3"
    product_file = workspace / "README.md"

    _run_cli("plan-init", "--path", str(db_path))
    _create_task(db_path)
    product_file.write_text("# Direct transition artifact\n", encoding="utf-8")
    _run_cli(
        "attempt-transition",
        "--path",
        str(db_path),
        "--task-id",
        "task-acp",
        "--attempt-id",
        "attempt-manual",
        "--executor",
        "codex",
        "--status",
        "running",
        "--summary",
        "Record state.",
    )
    _run_cli(
        "attempt-transition",
        "--path",
        str(db_path),
        "--task-id",
        "task-acp",
        "--attempt-id",
        "attempt-manual",
        "--executor",
        "codex",
        "--status",
        "succeeded",
        "--summary",
        "Recorded direct product file artifact.",
        "--check",
        "README.md exists.",
        "--artifact",
        str(workspace / ".codex-supervisor" / "evidence" / "attempt-manual-assignment.json"),
        "--artifact",
        str(workspace / ".codex-supervisor" / "evidence" / "attempt-manual-command.json"),
        "--artifact",
        str(product_file),
        "--acceptance-result",
        "pass",
        "--risk",
        "No known residual risk.",
        "--review-evidence",
        "This evidence did not come from attempt-run.",
    )

    result = check_target_workspace_acp_gate(workspace)

    assert result.ok is False
    assert result.changed_product_paths == ("README.md",)
    assert result.worker_backed_paths == ()
    assert result.failures == (
        "product paths lack accepted attempt-run worker evidence: README.md",
    )


def test_acp_gate_rejects_tracked_supervisor_state(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init")
    db_path = workspace / ".codex-supervisor" / "planning.sqlite3"

    _run_cli("plan-init", "--path", str(db_path))
    _git(workspace, "add", "-f", ".codex-supervisor/planning.sqlite3")

    result = check_target_workspace_acp_gate(workspace)

    assert result.ok is False
    assert result.failures == (
        ".codex-supervisor/planning.sqlite3 is not ignored by git",
        ".codex-supervisor has tracked paths: .codex-supervisor/planning.sqlite3",
    )


def test_acp_gate_script_reports_failures_as_json(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init")
    db_path = workspace / ".codex-supervisor" / "planning.sqlite3"

    _run_cli("plan-init", "--path", str(db_path))
    (workspace / "README.md").write_text("# Direct edit\n", encoding="utf-8")

    completed = subprocess.run(
        (
            sys.executable,
            "-B",
            str(REPO_ROOT / "scripts" / "check_target_workspace_acp.py"),
            "--workspace",
            str(workspace),
            "--json",
        ),
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert payload["changed_product_paths"] == ["README.md"]
    assert payload["worker_backed_paths"] == []
    assert "warnings" in payload


def _create_task(db_path: Path) -> None:
    _run_cli(
        "task-create",
        "--path",
        str(db_path),
        "--plan-id",
        "plan-acp",
        "--plan-title",
        "ACP gate",
        "--plan-goal",
        "Prove target workspace ACP checks.",
        "--task-id",
        "task-acp",
        "--title",
        "Create README",
        "--intent",
        "Create README.md through a worker.",
        "--assurance",
        "high",
        "--acceptance",
        "README.md exists",
        "--json",
    )


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (sys.executable, "-B", "-m", "codex_supervisor.cli", *args),
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=15,
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


def _git(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", str(workspace), *args),
        check=True,
        text=True,
        capture_output=True,
    )
