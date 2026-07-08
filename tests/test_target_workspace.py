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
    inspect_product_provenance,
    product_artifact_state_checks,
    product_path_matches_recorded_state,
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
            "R  docs/new.txt",
            "old.txt",
            "",
        )
    )

    assert product_paths_from_porcelain_z(output) == (
        "README.md",
        "app/main.py",
        "docs/new.txt",
        "old.txt",
    )


def test_product_paths_from_porcelain_z_keeps_copy_source_out_of_changed_paths() -> None:
    output = "\0".join(
        (
            "C  docs/copied.txt",
            "docs/source.txt",
            "",
        )
    )

    assert product_paths_from_porcelain_z(output) == ("docs/copied.txt",)


def test_product_artifact_state_checks_record_rename_source_deletion(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "docs").mkdir()
    (workspace / "docs" / "new.txt").write_text("renamed\n", encoding="utf-8")

    checks = product_artifact_state_checks(workspace, ("docs/new.txt", "old.txt"))

    assert any(check.startswith("product artifact sha256: ") for check in checks)
    assert 'product artifact deleted: {"path":"old.txt"}' in checks


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
    assert artifact_to_workspace_relative(workspace, "..\\outside.txt") is None


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
    product_text = "# Product\n"
    (workspace / "README.md").write_text(product_text, encoding="utf-8")
    _write_attempt_run_metadata(evidence_dir, attempt_id="attempt-1", task_id="task-1")
    _insert_succeeded_attempt(
        db_path,
        checks=product_artifact_state_checks(workspace, ("README.md",)),
        artifacts=(
            str(evidence_dir / "attempt-1-assignment.json"),
            str(evidence_dir / "attempt-1-command.json"),
            str(workspace / "README.md"),
            str(workspace / ".codex-supervisor" / "planning.sqlite3"),
        ),
    )

    assert changed_product_paths(workspace) == ("README.md",)
    assert worker_backed_product_paths(workspace, database_path=db_path) == ("README.md",)
    assert product_path_matches_recorded_state(
        workspace,
        "README.md",
        checks=product_artifact_state_checks(workspace, ("README.md",)),
    )
    assert has_attempt_run_metadata(
        workspace,
        attempt_id="attempt-1",
        artifacts=(
            str(evidence_dir / "attempt-1-assignment.json"),
            str(evidence_dir / "attempt-1-command.json"),
        ),
    )


def test_worker_backed_paths_require_accepted_decision_and_metadata(
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
    _write_attempt_run_metadata(evidence_dir, attempt_id="attempt-1", task_id="task-1")
    _insert_succeeded_attempt(
        db_path,
        checks=product_artifact_state_checks(workspace, ("README.md",)),
        artifacts=(
            str(evidence_dir / "attempt-1-assignment.json"),
            str(evidence_dir / "attempt-1-command.json"),
            str(workspace / "README.md"),
        ),
        acceptance_result="rejected",
        evaluation_accepted=False,
    )

    assert worker_backed_product_paths(workspace, database_path=db_path) == ()


def test_worker_backed_paths_require_current_product_state_match(
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
    (workspace / "README.md").write_text("# Worker output\n", encoding="utf-8")
    checks = product_artifact_state_checks(workspace, ("README.md",))
    _write_attempt_run_metadata(evidence_dir, attempt_id="attempt-1", task_id="task-1")
    _insert_succeeded_attempt(
        db_path,
        checks=checks,
        artifacts=(
            str(evidence_dir / "attempt-1-assignment.json"),
            str(evidence_dir / "attempt-1-command.json"),
            str(workspace / "README.md"),
        ),
    )
    (workspace / "README.md").write_text("# Direct edit after worker\n", encoding="utf-8")

    assert worker_backed_product_paths(workspace, database_path=db_path) == ()


def test_product_provenance_reports_unbacked_current_state(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    db_path = workspace / ".codex-supervisor" / "planning.sqlite3"
    initialize_compact_planning_database(db_path)
    _git(workspace, "init")
    (workspace / ".gitignore").write_text(".codex-supervisor/\n", encoding="utf-8")
    (workspace / "README.md").write_text("# Direct edit\n", encoding="utf-8")

    provenance = inspect_product_provenance(workspace, database_path=db_path)

    assert provenance.changed_product_paths == ("README.md",)
    assert provenance.worker_backed_paths == ()
    assert provenance.unbacked_paths == ("README.md",)
    assert provenance.inspection_error is None


def test_attempt_run_metadata_must_exist_and_match_attempt(
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
        ),
    )

    assert worker_backed_product_paths(workspace, database_path=db_path) == ()


def _insert_succeeded_attempt(
    db_path: Path,
    *,
    artifacts: tuple[str, ...],
    checks: tuple[str, ...] = (),
    acceptance_result: str = "accepted",
    evaluation_accepted: bool = True,
) -> None:
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
               ) values ('evidence-1', 'task-1', 'attempt-1', 'high', ?, ?, ?, ?)""",
            (
                "Evidence.",
                json.dumps(list(checks), indent=2),
                json.dumps(list(artifacts), indent=2),
                "2026-06-04T00:00:01Z",
            ),
        )
        connection.execute(
            """insert into acceptance_decisions(
                   decision_id, task_id, attempt_id, bundle_id, actor,
                   result, rationale, evaluation_json, created_at
               ) values ('acceptance-1', 'task-1', 'attempt-1', 'evidence-1', ?, ?, ?, ?, ?)""",
            (
                "codex-supervisor-policy",
                acceptance_result,
                "Policy decision.",
                json.dumps({"accepted": evaluation_accepted}, indent=2),
                "2026-06-04T00:00:01Z",
            ),
        )


def _write_attempt_run_metadata(
    evidence_dir: Path,
    *,
    attempt_id: str,
    task_id: str,
) -> None:
    (evidence_dir / f"{attempt_id}-assignment.json").write_text(
        json.dumps(
            {
                "recorded_by": "codex-supervisor.attempt-run",
                "attempt": {"attempt_id": attempt_id},
                "task": {"task_id": task_id},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (evidence_dir / f"{attempt_id}-command.json").write_text(
        json.dumps(
            {
                "recorded_by": "codex-supervisor.attempt-run",
                "attempt_id": attempt_id,
                "task_id": task_id,
                "command": ["python", "-c", "print('worker')"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _git(workspace: Path, *args: str) -> None:
    subprocess.run(
        ("git", "-C", str(workspace), *args),
        text=True,
        capture_output=True,
        check=True,
    )
