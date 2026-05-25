from __future__ import annotations

import json

import pytest

from codex_supervisor.worker_results import (
    WorkerResultError,
    validate_worker_result_file,
    validate_worker_result_payload,
)


def test_worker_result_validation_accepts_completed_contract(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "worker.py").write_text("print('ok')\n", encoding="utf-8")
    result_path = "worker-results/run-worker-result.json"
    result_file = tmp_path / result_path
    result_file.parent.mkdir(parents=True)
    result_file.write_text(json.dumps(_worker_result()), encoding="utf-8")

    result = validate_worker_result_file(
        result_file,
        repo_root=tmp_path,
        result_path=result_path,
        worker_run_id="run-worker",
        allowed_paths=("src/**",),
        verification_commands=("python -B -m pytest -p no:cacheprovider",),
        acceptance_criteria=("Criterion passes.",),
    )

    assert result.worker_run_ids == ("run-worker",)
    assert result.changed_files == ("src/worker.py",)
    assert result.artifacts == ("worker-results/run-worker-result.json",)


@pytest.mark.parametrize("status", ["blocked", "failed", "needs_review"])
def test_worker_result_validation_accepts_noncompleted_contract_without_success_evidence(
    tmp_path,
    status,
):
    payload = {
        "worker_run_id": "run-worker",
        "status": status,
        "summary": "Worker could not complete.",
        "changed_files": [],
        "tests_run": [],
        "acceptance_results": {},
        "risks": ["No accepted change."],
        "follow_up_tasks": [],
        "artifacts": [],
        "handoff_notes": "Needs follow-up.",
    }

    result = validate_worker_result_payload(
        payload,
        repo_root=tmp_path,
        result_path="runs/run-worker/result.json",
        worker_run_id="run-worker",
        allowed_paths=("src/**",),
        verification_commands=("python -B -m pytest -p no:cacheprovider",),
        acceptance_criteria=("Criterion passes.",),
    )

    assert result.status == status
    assert result.changed_files == ()
    assert result.artifacts == ()


def test_completed_worker_result_must_use_durable_tracked_result_path(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "worker.py").write_text("print('ok')\n", encoding="utf-8")
    payload = _worker_result()
    payload["artifacts"] = ["runs/run-worker/result.json"]

    with pytest.raises(WorkerResultError, match="durable tracked evidence"):
        validate_worker_result_payload(
            payload,
            repo_root=tmp_path,
            result_path="runs/run-worker/result.json",
            worker_run_id="run-worker",
            allowed_paths=("src/**",),
            verification_commands=("python -B -m pytest -p no:cacheprovider",),
            acceptance_criteria=("Criterion passes.",),
        )


def test_worker_result_validation_requires_task_verification_command(tmp_path):
    payload = _worker_result()

    with pytest.raises(WorkerResultError, match="missing task verification command"):
        validate_worker_result_payload(
            payload,
            repo_root=tmp_path,
            result_path="worker-results/run-worker-result.json",
            worker_run_id="run-worker",
            allowed_paths=("src/**",),
            verification_commands=("python -B scripts/verify.py",),
            acceptance_criteria=("Criterion passes.",),
        )


def test_worker_result_validation_requires_changed_files_within_allowed_paths(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "worker.py").write_text("print('ok')\n", encoding="utf-8")
    result_file = tmp_path / "worker-results" / "run-worker-result.json"
    result_file.parent.mkdir(parents=True)
    result_file.write_text("{}", encoding="utf-8")
    payload = _worker_result()

    with pytest.raises(WorkerResultError, match="not covered by allowed_paths"):
        validate_worker_result_payload(
            payload,
            repo_root=tmp_path,
            result_path="worker-results/run-worker-result.json",
            worker_run_id="run-worker",
            allowed_paths=("tests/**",),
            verification_commands=("python -B -m pytest -p no:cacheprovider",),
            acceptance_criteria=("Criterion passes.",),
        )


def test_worker_result_validation_requires_acceptance_evidence(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "worker.py").write_text("print('ok')\n", encoding="utf-8")
    payload = _worker_result()
    payload["acceptance_results"] = {}

    with pytest.raises(WorkerResultError, match="acceptance_results"):
        validate_worker_result_payload(
            payload,
            repo_root=tmp_path,
            result_path="worker-results/run-worker-result.json",
            worker_run_id="run-worker",
            allowed_paths=("src/**",),
            verification_commands=("python -B -m pytest -p no:cacheprovider",),
            acceptance_criteria=("Criterion passes.",),
        )


def _worker_result() -> dict[str, object]:
    return {
        "worker_run_id": "run-worker",
        "status": "completed",
        "summary": "Completed.",
        "changed_files": ["src/worker.py"],
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
                "evidence": "Evidence.",
            }
        },
        "risks": ["No live backend was launched."],
        "follow_up_tasks": [],
        "artifacts": ["worker-results/run-worker-result.json"],
        "handoff_notes": "Ready.",
    }
