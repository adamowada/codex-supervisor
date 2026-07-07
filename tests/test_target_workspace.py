from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

from codex_supervisor.compact_planning import initialize_compact_planning_database
from codex_supervisor.target_workspace import (
    artifact_to_workspace_relative,
    changed_product_paths,
    has_attempt_run_metadata,
    product_paths_from_porcelain_z,
    worker_backed_product_paths,
)


def test_product_paths_from_porcelain_z_excludes_supervisor_and_gitignore() -> None:
    output = "\0".join(
        (
            "?? README.md",
            " M .gitignore",
            "?? .codex-supervisor/planning.sqlite3",
            " M app/main.py",
            "R  old.txt",
            "docs/new.txt",
            "",
        )
    )

    assert product_paths_from_porcelain_z(output) == (
        "README.md",
        "app/main.py",
        "docs/new.txt",
    )


def test_artifact_to_workspace_relative_normalizes_absolute_and_relative_paths(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    assert artifact_to_workspace_relative(workspace, workspace / "app" / "main.py") == (
        "app/main.py"
    )
    assert artifact_to_workspace_relative(workspace, ".\\docs\\note.md") == "docs/note.md"
    assert artifact_to_workspace_relative(workspace, tmp_path / "outside.txt") is None


def test_changed_product_paths_and_worker_backed_paths_share_product_rules(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    db_path = workspace / ".codex-supervisor" / "planning.sqlite3"
    evidence_dir = workspace / ".codex-supervisor" / "evidence"
    evidence_dir.mkdir(parents=True)
    initialize_compact_planning_database(db_path)
    _git(workspace, "init")
    (workspace / ".gitignore").write_text(".codex-supervisor/\n", encoding="utf-8")
    (workspace / "README.md").write_text("# Product\n", encoding="utf-8")
    _insert_succeeded_attempt(
        db_path,
        artifacts=(
            str(evidence_dir / "attempt-1-assignment.json"),
            str(evidence_dir / "attempt-1-command.json"),
            str(workspace / "README.md"),
            str(workspace / ".codex-supervisor" / "planning.sqlite3"),
        ),
    )

    assert changed_product_paths(workspace) == ("README.md",)
    assert worker_backed_product_paths(workspace, database_path=db_path) == ("README.md",)
    assert has_attempt_run_metadata(
        workspace,
        attempt_id="attempt-1",
        artifacts=(
            str(evidence_dir / "attempt-1-assignment.json"),
            str(evidence_dir / "attempt-1-command.json"),
        ),
    )


def _insert_succeeded_attempt(db_path: Path, *, artifacts: tuple[str, ...]) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """insert into plans(plan_id, title, status, priority, goal, created_at, updated_at)
               values ('plan-1', 'Plan', 'done', 100, 'Goal', ?, ?)""",
            ("2026-06-04T00:00:00Z", "2026-06-04T00:00:00Z"),
        )
        connection.execute(
            """insert into tasks(
                   task_id, plan_id, title, status, assurance, intent,
                   acceptance_json, created_at, updated_at
               ) values ('task-1', 'plan-1', 'Task', 'done', 'high', 'Intent', ?, ?, ?)""",
            (
                '["README.md exists"]',
                "2026-06-04T00:00:00Z",
                "2026-06-04T00:00:00Z",
            ),
        )
        connection.execute(
            """insert into attempts(
                   attempt_id, task_id, executor, status, summary, started_at, finished_at
               ) values ('attempt-1', 'task-1', 'worker-process', 'succeeded', ?, ?, ?)""",
            (
                "Worker succeeded.",
                "2026-06-04T00:00:00Z",
                "2026-06-04T00:00:01Z",
            ),
        )
        connection.execute(
            """insert into evidence_bundles(
                   bundle_id, task_id, attempt_id, assurance, summary,
                   checks_json, artifacts_json, created_at
               ) values ('evidence-1', 'task-1', 'attempt-1', 'high', ?, '[]', ?, ?)""",
            (
                "Evidence.",
                json.dumps(list(artifacts), indent=2),
                "2026-06-04T00:00:01Z",
            ),
        )


def _git(workspace: Path, *args: str) -> None:
    subprocess.run(
        ("git", "-C", str(workspace), *args),
        text=True,
        capture_output=True,
        check=True,
    )
