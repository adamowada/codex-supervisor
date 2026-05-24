from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_supervisor.cli import main
from codex_supervisor.planning import (
    PlanRecord,
    SupervisorTaskRecord,
    initialize_planning_database,
    open_existing_planning_database,
)


def test_review_result_ingest_cli_persists_review_result_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = _db_path(tmp_path)
    _store(db_path)
    review_result_path = _write_review_result(tmp_path)

    exit_code = main(
        [
            "review-result-ingest",
            "--path",
            str(db_path),
            "--plan-id",
            "plan-review",
            "--progress-id",
            "progress-review-cli",
            "--review-result-path",
            str(review_result_path),
            "--review-result-artifact-id",
            "insights/review-result.json",
            "--review-artifact-id",
            "insights/review-report.md",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    store = open_existing_planning_database(db_path)
    progress = store.list_plan_progress(plan_id="plan-review")
    links = store.list_plan_artifact_links(plan_id="plan-review")

    assert exit_code == 0
    assert captured.err == ""
    assert payload["review_result"] == {
        "finding_counts": {
            "accepted": 1,
            "needs_hitl": 1,
            "total": 3,
            "waived": 1,
        },
        "mode": "everything",
        "review_id": "review-cli-001",
        "target": "diff:HEAD~1..HEAD",
    }
    assert payload["progress"]["progress_id"] == "progress-review-cli"
    assert payload["progress"]["event_type"] == "review_result_recorded"
    assert payload["repair_tasks"] == {
        "created_task_ids": [],
        "created_tasks": [],
        "existing_task_ids": [],
        "requested": False,
        "skipped_findings": [],
    }
    assert progress[0].progress_id == "progress-review-cli"
    assert {(link.artifact_id, link.relationship) for link in links} == {
        ("insights/review-result.json", "review-result"),
        ("insights/review-report.md", "review-artifact"),
    }
    assert store.list_supervisor_tasks() == ()
    assert store.list_worker_runs() == ()


def test_review_result_ingest_cli_can_route_repair_tasks(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = _db_path(tmp_path)
    store = _store(db_path)
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-source-review",
            plan_id="plan-review",
            title="Source Review",
            goal="Provide completed review evidence.",
            task_type="AFK",
            status="completed",
            acceptance_criteria=("Review completed.",),
            verification_commands=("uv run --no-sync python -B scripts/verify.py",),
            allowed_paths=("src/codex_supervisor/cli.py",),
        )
    )
    review_result_path = _write_review_result(tmp_path)

    exit_code = main(
        [
            "review-result-ingest",
            "--path",
            str(db_path),
            "--plan-id",
            "plan-review",
            "--progress-id",
            "progress-review-cli-with-repairs",
            "--review-result-path",
            str(review_result_path),
            "--review-result-artifact-id",
            "insights/review-result.json",
            "--create-repair-tasks",
            "--source-task-id",
            "task-source-review",
            "--repair-verification-command",
            "uv run --no-sync python -B -m pytest tests/test_review_cli.py -q -p no:cacheprovider",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    store = open_existing_planning_database(db_path)
    tasks = store.list_supervisor_tasks()
    repair_task = next(task for task in tasks if task.task_id != "task-source-review")

    assert exit_code == 0
    assert captured.err == ""
    assert payload["repair_tasks"]["requested"] is True
    assert payload["repair_tasks"]["created_task_ids"] == [
        "task-review-repair-review-cli-001-finding-accepted"
    ]
    assert payload["repair_tasks"]["existing_task_ids"] == []
    assert [
        (finding["finding_id"], finding["status"])
        for finding in payload["repair_tasks"]["skipped_findings"]
    ] == [
        ("finding-waived", "waived"),
        ("finding-hitl", "needs_hitl"),
    ]
    assert repair_task.status == "ready"
    assert repair_task.blocked_by == ["task-source-review"]
    assert repair_task.allowed_paths == ["src/codex_supervisor/cli.py"]
    assert repair_task.verification_commands == [
        "uv run --no-sync python -B -m pytest tests/test_review_cli.py -q -p no:cacheprovider"
    ]
    assert store.list_worker_runs() == ()


def test_review_result_ingest_cli_rejects_invalid_review_payload(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = _db_path(tmp_path)
    _store(db_path)
    review_result_path = tmp_path / "invalid-review-result.json"
    review_result_path.write_text(
        json.dumps(
            {
                "review_id": "review-invalid",
                "mode": "everything",
                "target": "diff:HEAD",
                "verification_evidence": [],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "review-result-ingest",
            "--path",
            str(db_path),
            "--plan-id",
            "plan-review",
            "--progress-id",
            "progress-invalid",
            "--review-result-path",
            str(review_result_path),
            "--review-result-artifact-id",
            "insights/invalid-review-result.json",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    store = open_existing_planning_database(db_path)

    assert exit_code == 1
    assert captured.out == ""
    assert "Could not ingest review result: findings must be a list" in captured.err
    assert store.list_plan_progress(plan_id="plan-review") == ()
    assert store.list_plan_artifact_links(plan_id="plan-review") == ()
    assert store.list_worker_runs() == ()


def test_review_result_ingest_cli_reports_existing_repair_tasks_on_rerun(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = _db_path(tmp_path)
    store = _store(db_path)
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-source-review",
            plan_id="plan-review",
            title="Source Review",
            goal="Provide completed review evidence.",
            task_type="AFK",
            status="completed",
            acceptance_criteria=("Review completed.",),
            verification_commands=("uv run --no-sync python -B scripts/verify.py",),
            allowed_paths=("src/codex_supervisor/cli.py",),
        )
    )
    review_result_path = _write_review_result(tmp_path)
    base_args = [
        "review-result-ingest",
        "--path",
        str(db_path),
        "--plan-id",
        "plan-review",
        "--review-result-path",
        str(review_result_path),
        "--review-result-artifact-id",
        "insights/review-result.json",
        "--create-repair-tasks",
        "--source-task-id",
        "task-source-review",
        "--json",
    ]

    assert main([*base_args, "--progress-id", "progress-first"]) == 0
    capsys.readouterr()
    assert main([*base_args, "--progress-id", "progress-second"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["repair_tasks"]["created_task_ids"] == []
    assert payload["repair_tasks"]["existing_task_ids"] == [
        "task-review-repair-review-cli-001-finding-accepted"
    ]


def _db_path(tmp_path: Path) -> Path:
    return tmp_path / "plans" / "planning.sqlite3"


def _store(db_path: Path):
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-review",
            slug="review",
            title="Review Plan",
            goal="Ingest review results.",
            status="active",
        )
    )
    return store


def _write_review_result(tmp_path: Path) -> Path:
    review_result_path = tmp_path / "review-result.json"
    review_result_path.write_text(json.dumps(_review_result_payload()), encoding="utf-8")
    return review_result_path


def _review_result_payload() -> dict[str, object]:
    return {
        "review_id": "review-cli-001",
        "mode": "everything",
        "target": "diff:HEAD~1..HEAD",
        "findings": [
            {
                "finding_id": "finding-accepted",
                "mode": "code_quality",
                "severity": "P2",
                "status": "accepted",
                "title": "Add CLI coverage",
                "evidence": "The review ingestion command needs focused coverage.",
                "location": {"path": "src/codex_supervisor/cli.py"},
                "recommendation": "Add a review CLI test.",
            },
            {
                "finding_id": "finding-waived",
                "mode": "architecture",
                "severity": "P3",
                "status": "waived",
                "title": "Keep CLI helper local",
                "evidence": "The helper is still small.",
                "location": {"scope": "review CLI"},
                "recommendation": "Extract later if another command needs it.",
                "waiver_rationale": "One local CLI command does not justify another module yet.",
            },
            {
                "finding_id": "finding-hitl",
                "mode": "source_of_truth_drift",
                "severity": "P1",
                "status": "needs_hitl",
                "title": "Needs human policy call",
                "evidence": "The finding needs product judgment.",
                "location": {"scope": "review policy"},
                "recommendation": "Ask for HITL confirmation.",
            },
        ],
        "verification_evidence": [
            {
                "command": "uv run --no-sync python -B -m pytest tests/test_review_cli.py",
                "exit_code": 0,
                "summary": "passed",
            }
        ],
    }
