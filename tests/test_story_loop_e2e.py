from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

from codex_supervisor.planning import (
    PlanRecord,
    SupervisorTaskRecord,
    initialize_planning_database,
    open_existing_planning_database,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHONPATH = str(REPO_ROOT / "src")
ACCEPTANCE = "Live Story Loop e2e completes."
VERIFY_COMMAND = "python -B -m pytest -p no:cacheprovider tests/test_fake.py"


def test_story_loop_run_once_cli_executes_fake_codex_through_real_git_worktree(
    tmp_path: Path,
) -> None:
    project = _seed_story_loop_project(tmp_path)
    fake_codex = _write_fake_codex_executable(tmp_path)

    completed = _run_cli(
        "story-loop-run-once",
        "--path",
        str(project / "plans" / "planning.sqlite3"),
        "--repo-root",
        str(project),
        "--worker-run-id",
        "run-e2e",
        "--codex-executable",
        str(fake_codex),
        "--json",
        cwd=REPO_ROOT,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    payload = json.loads(completed.stdout)
    assert payload["status"] == "completed"
    assert payload["task_id"] == "task-e2e"
    assert payload["worker_run_id"] == "run-e2e"
    assert payload["changed_files"] == ["src/live_story.py"]
    assert payload["changed_files_source"] == "git_worktree"
    assert payload["worktree_created"] is True
    assert payload["result_id"]

    store = open_existing_planning_database(project / "plans" / "planning.sqlite3")
    task = next(task for task in store.list_supervisor_tasks() if task.task_id == "task-e2e")
    run = next(run for run in store.list_worker_runs() if run.worker_run_id == "run-e2e")
    progress_types = {event.event_type for event in store.list_plan_progress(plan_id="plan-e2e")}
    artifact_links = {
        (link.artifact_id, link.relationship)
        for link in store.list_plan_artifact_links(plan_id="plan-e2e")
    }

    assert task.status == "completed"
    assert run.status == "completed"
    assert run.result_id == payload["result_id"]
    assert run.result_path is None
    assert run.metadata["runtime_preflight"]["worker_execution"] == "codex_exec"
    assert run.metadata["runtime_preflight"]["evidence_mode"] == "strict_jsonl"
    assert "browser_smoke_passed" in progress_types
    assert artifact_links == {
        ("artifacts/run-e2e/evidence-manifest.json", "worker-evidence-manifest"),
        ("artifacts/run-e2e/worker-result.raw.json", "worker-result"),
        ("artifacts/run-e2e/worker-result.normalized.json", "worker-result-normalized"),
    }
    assert (project / "artifacts" / "browser" / "smoke.log").read_text(encoding="utf-8") == (
        "fake browser smoke passed\n"
    )
    assert (
        (project / "runs" / "run-e2e" / "prompt.md")
        .read_text(encoding="utf-8")
        .startswith("# Goal Contract\n")
    )
    assert "fake codex e2e update" in (
        project / "worktrees" / "run-e2e" / "src" / "live_story.py"
    ).read_text(encoding="utf-8")


def test_story_loop_run_once_cli_rejects_worker_result_without_test_event(
    tmp_path: Path,
) -> None:
    project = _seed_story_loop_project(tmp_path)
    fake_codex = _write_fake_codex_executable(tmp_path, emit_test_command_event=False)

    completed = _run_cli(
        "story-loop-run-once",
        "--path",
        str(project / "plans" / "planning.sqlite3"),
        "--repo-root",
        str(project),
        "--worker-run-id",
        "run-evidence-gap",
        "--codex-executable",
        str(fake_codex),
        "--json",
        cwd=REPO_ROOT,
    )

    assert completed.returncode == 1, completed.stderr + completed.stdout
    payload = json.loads(completed.stdout)
    assert payload["status"] == "failed"
    assert payload["failure_class"] == "worker_result_evidence_mismatch"
    assert payload["result_id"]

    store = open_existing_planning_database(project / "plans" / "planning.sqlite3")
    run = next(run for run in store.list_worker_runs() if run.worker_run_id == "run-evidence-gap")
    task = next(task for task in store.list_supervisor_tasks() if task.task_id == "task-e2e")
    launch_event = next(
        event
        for event in store.list_worker_run_events(worker_run_id="run-evidence-gap")
        if event.event_type == "codex_exec_launch_result"
    )

    assert run.status == "failed"
    assert run.failure_class == "worker_result_evidence_mismatch"
    assert task.status == "failed"
    reason = "Worker Result tests_run commands were not observed in Codex JSONL command events."
    assert launch_event.metadata["worker_result_evidence_validation"] == {
        "failure_class": "worker_result_evidence_mismatch",
        "missing_tests_run_commands": [VERIFY_COMMAND],
        "path": "runs/run-evidence-gap/events.jsonl",
        "reason": reason,
    }


def test_story_loop_start_and_poll_cli_complete_fake_codex_controller_subprocess(
    tmp_path: Path,
) -> None:
    project = _seed_story_loop_project(tmp_path)
    fake_codex = _write_fake_codex_executable(tmp_path)

    started = _run_cli(
        "story-loop-start",
        "--path",
        str(project / "plans" / "planning.sqlite3"),
        "--repo-root",
        str(project),
        "--worker-run-id",
        "run-async-e2e",
        "--codex-executable",
        str(fake_codex),
        "--json",
        cwd=REPO_ROOT,
    )

    assert started.returncode == 0, started.stderr + started.stdout
    start_payload = json.loads(started.stdout)
    assert start_payload["status"] == "started"
    assert start_payload["controller_mode"] == "async_controller_subprocess"
    assert start_payload["worker_run_id"] == "run-async-e2e"
    assert start_payload["poll_tool"] == "codex_supervisor.story_loop_poll"

    poll_payload: dict[str, object] | None = None
    for _ in range(40):
        polled = _run_cli(
            "story-loop-poll",
            "--path",
            str(project / "plans" / "planning.sqlite3"),
            "--repo-root",
            str(project),
            "--worker-run-id",
            "run-async-e2e",
            "--controller-pid",
            str(start_payload["controller_pid"]),
            "--json",
            cwd=REPO_ROOT,
        )
        assert polled.returncode == 0, polled.stderr + polled.stdout
        poll_payload = json.loads(polled.stdout)
        if poll_payload["done"] is True:
            break
        time.sleep(0.1)

    assert poll_payload is not None
    assert poll_payload["status"] == "completed", poll_payload
    assert poll_payload["done"] is True
    assert poll_payload["worker_run_status"] == "completed"
    assert poll_payload["result_id"]
    assert poll_payload["liveness_probe_path"] == "runs/run-async-e2e/liveness.json"
    assert (project / "runs" / "run-async-e2e" / "controller.stdout.json").is_file()
    assert (project / "runs" / "run-async-e2e" / "controller.json").is_file()
    assert "fake codex e2e update" in (
        project / "worktrees" / "run-async-e2e" / "src" / "live_story.py"
    ).read_text(encoding="utf-8")


def _seed_story_loop_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    _git(project, "init")
    _git(project, "config", "user.email", "codex@example.test")
    _git(project, "config", "user.name", "Codex Test")
    (project / "src").mkdir()
    (project / "src" / "live_story.py").write_text(
        "print('before fake codex')\n",
        encoding="utf-8",
    )
    store = initialize_planning_database(project / "plans" / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-e2e",
            slug="e2e",
            title="E2E",
            goal="Exercise the real CLI Story Loop path with a fake Codex executable.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-e2e",
            plan_id="plan-e2e",
            title="Run fake Codex through CLI",
            goal="Update src/live_story.py through the real Story Loop CLI path.",
            task_type="AFK",
            status="ready",
            scope={"browser_smoke_required": True, "review_skipped": True},
            acceptance_criteria=[ACCEPTANCE],
            verification_commands=[VERIFY_COMMAND],
            allowed_paths=["src/**"],
            worker_backend="codex_exec",
            review_required=False,
        ),
        validate_current_queue_contract=True,
    )
    _git(project, "add", "src/live_story.py", "plans/planning.sqlite3")
    _git(project, "commit", "-m", "Seed e2e story loop project")
    return project


def _write_fake_codex_executable(
    tmp_path: Path,
    *,
    emit_test_command_event: bool = True,
) -> Path:
    tool_dir = tmp_path / "tools"
    tool_dir.mkdir()
    script = tool_dir / "fake_codex.py"
    script_template = """
from __future__ import annotations

import json
import sys
from pathlib import Path

ACCEPTANCE = "Live Story Loop e2e completes."
VERIFY_COMMAND = "python -B -m pytest -p no:cacheprovider tests/test_fake.py"
EMIT_TEST_COMMAND_EVENT = __EMIT_TEST_COMMAND_EVENT__


def main() -> int:
    args = sys.argv[1:]
    if args == ["--version"]:
        print("codex 99.0.0")
        return 0
    if not args or args[0] != "exec":
        print(f"unexpected fake codex argv: {args}", file=sys.stderr)
        return 2
    _prompt = sys.stdin.read()
    final_message = Path(_arg_value(args, "--output-last-message"))
    final_message.parent.mkdir(parents=True, exist_ok=True)
    worker_run_id = final_message.parent.name

    worktree = Path.cwd()
    changed_file = worktree / "src" / "live_story.py"
    changed_file.parent.mkdir(parents=True, exist_ok=True)
    existing = changed_file.read_text(encoding="utf-8") if changed_file.exists() else ""
    changed_file.write_text(existing + "fake codex e2e update\\n", encoding="utf-8")

    smoke_dir = worktree / "artifacts" / "browser"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    (smoke_dir / "smoke.log").write_text("fake browser smoke passed\\n", encoding="utf-8")
    (smoke_dir / "smoke.png").write_bytes(b"fake-png")

    payload = {
        "worker_run_id": worker_run_id,
        "status": "completed",
        "summary": "Fake Codex completed the deterministic e2e slice.",
        "changed_files": ["src/live_story.py"],
        "tests_run": [
            {
                "command": VERIFY_COMMAND,
                "exit_code": 0,
                "summary": "Fake verification passed.",
            }
        ],
        "acceptance_results": {
            ACCEPTANCE: {
                "status": "passed",
                "evidence": "Fake Codex updated src/live_story.py through the real CLI path.",
            }
        },
        "risks": [],
        "follow_up_tasks": [],
        "artifacts": [],
        "browser_smoke_results": [
            {
                "status": "passed",
                "summary": "Fake browser smoke evidence captured.",
                "command": "node scripts/smoke-browser.mjs",
                "exit_code": 0,
                "tool": "playwright",
                "url": "http://127.0.0.1:4173",
                "artifacts": [
                    "artifacts/browser/smoke.log",
                    "artifacts/browser/smoke.png",
                ],
            }
        ],
        "completion_notes": "Ready for deterministic e2e assertions.",
    }
    final_message.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    if EMIT_TEST_COMMAND_EVENT:
        print(json.dumps({
            "type": "item.completed",
            "item": {
                "id": "item-test",
                "type": "command_execution",
                "command": VERIFY_COMMAND,
                "aggregated_output": "passed\\n",
                "exit_code": 0,
                "status": "completed",
            },
        }))
    print(json.dumps({"event": "assistant.step", "summary": "fake codex wrote result"}))
    return 0


def _arg_value(args: list[str], flag: str) -> str:
    index = args.index(flag)
    return args[index + 1]


if __name__ == "__main__":
    raise SystemExit(main())
""".lstrip()
    script.write_text(
        script_template.replace(
            "__EMIT_TEST_COMMAND_EVENT__",
            repr(emit_test_command_event),
        ),
        encoding="utf-8",
    )
    if os.name == "nt":
        wrapper = tool_dir / "codex.cmd"
        wrapper.write_text(
            f'@echo off\r\n"{sys.executable}" -B "%~dp0fake_codex.py" %*\r\n',
            encoding="utf-8",
        )
        return wrapper
    wrapper = tool_dir / "codex"
    wrapper.write_text(
        f'#!/bin/sh\nexec {_sh_quote(sys.executable)} -B "$(dirname "$0")/fake_codex.py" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return wrapper


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = PYTHONPATH + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        (sys.executable, "-B", "-m", "codex_supervisor.cli", *args),
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ("git", *args),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
    return completed


def _sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"
