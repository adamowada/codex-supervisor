from __future__ import annotations

import hashlib
import json

import pytest

from codex_supervisor.planning import (
    PlanRecord,
    SupervisorTaskRecord,
    WorkerRunRecord,
    initialize_planning_database,
)
from codex_supervisor.worker_results import (
    MAX_WORKER_RESULT_BYTES,
    WorkerResultError,
    validate_worker_result_file,
    validate_worker_result_payload,
)


def test_worker_result_validation_accepts_completed_contract(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "worker.py").write_text("print('ok')\n", encoding="utf-8")
    result_path = "artifacts/run-worker/worker-result.raw.json"
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
    assert result.artifacts == ("artifacts/run-worker/worker-result.raw.json",)


def test_worker_result_validation_checks_changed_files_in_worktree_root(tmp_path):
    worktree = tmp_path / "worktrees" / "run-worker"
    (worktree / "src").mkdir(parents=True)
    (worktree / "src" / "worker.py").write_text("print('ok')\n", encoding="utf-8")
    result_path = "artifacts/run-worker/worker-result.raw.json"
    result_file = tmp_path / result_path
    result_file.parent.mkdir(parents=True)
    result_file.write_text(json.dumps(_worker_result()), encoding="utf-8")

    result = validate_worker_result_file(
        result_file,
        repo_root=tmp_path,
        changed_files_root=worktree,
        result_path=result_path,
        worker_run_id="run-worker",
        allowed_paths=("src/**",),
        verification_commands=("python -B -m pytest -p no:cacheprovider",),
        acceptance_criteria=("Criterion passes.",),
    )

    assert result.changed_files == ("src/worker.py",)


def test_worker_result_validation_checks_support_artifacts_in_worktree_root(tmp_path):
    worktree = tmp_path / "worktrees" / "run-worker"
    (worktree / "src").mkdir(parents=True)
    (worktree / "src" / "worker.py").write_text("print('ok')\n", encoding="utf-8")
    (worktree / "artifacts" / "browser").mkdir(parents=True)
    (worktree / "artifacts" / "browser" / "smoke.png").write_bytes(b"png")
    result_path = "artifacts/run-worker/worker-result.raw.json"
    result_file = tmp_path / result_path
    result_file.parent.mkdir(parents=True)
    payload = _worker_result()
    payload["artifacts"] = ["artifacts/browser/smoke.png"]
    payload["browser_smoke_results"] = [
        {
            "artifact": "artifacts/browser/smoke.png",
            "command": "node tests/browser-smoke.mjs",
            "exit_code": 0,
            "status": "passed",
            "summary": "Browser smoke passed.",
            "tool": "playwright",
            "url": "http://127.0.0.1:5173",
        }
    ]
    result_file.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_worker_result_file(
        result_file,
        repo_root=tmp_path,
        changed_files_root=worktree,
        artifact_root=worktree,
        result_path=result_path,
        worker_run_id="run-worker",
        allowed_paths=("src/**",),
        verification_commands=("python -B -m pytest -p no:cacheprovider",),
        acceptance_criteria=("Criterion passes.",),
    )

    assert result.artifacts == ("artifacts/browser/smoke.png",)


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


def test_completed_worker_result_can_use_transient_raw_json_source(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "worker.py").write_text("print('ok')\n", encoding="utf-8")
    result_file = tmp_path / "artifacts" / "run-worker" / "worker-result.raw.json"
    result_file.parent.mkdir(parents=True)
    result_file.write_text("{}", encoding="utf-8")
    payload = _worker_result()
    payload["artifacts"] = ["artifacts/run-worker/worker-result.raw.json"]

    result = validate_worker_result_payload(
        payload,
        repo_root=tmp_path,
        result_path="artifacts/run-worker/worker-result.raw.json",
        worker_run_id="run-worker",
        allowed_paths=("src/**",),
        verification_commands=("python -B -m pytest -p no:cacheprovider",),
        acceptance_criteria=("Criterion passes.",),
    )

    assert result.artifacts == ("artifacts/run-worker/worker-result.raw.json",)


def test_completed_worker_result_accepts_empty_supporting_artifacts(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "worker.py").write_text("print('ok')\n", encoding="utf-8")
    payload = _worker_result()
    payload["artifacts"] = []

    result = validate_worker_result_payload(
        payload,
        repo_root=tmp_path,
        result_path="artifacts/run-worker/worker-result.raw.json",
        worker_run_id="run-worker",
        allowed_paths=("src/**",),
        verification_commands=("python -B -m pytest -p no:cacheprovider",),
        acceptance_criteria=("Criterion passes.",),
    )

    assert result.artifacts == ()


def test_worker_result_validation_requires_task_verification_command(tmp_path):
    payload = _worker_result()

    with pytest.raises(WorkerResultError, match="missing task verification command"):
        validate_worker_result_payload(
            payload,
            repo_root=tmp_path,
            result_path="artifacts/run-worker/worker-result.raw.json",
            worker_run_id="run-worker",
            allowed_paths=("src/**",),
            verification_commands=("python -B scripts/verify.py",),
            acceptance_criteria=("Criterion passes.",),
        )


def test_worker_result_validation_accepts_browser_smoke_evidence_outside_tests_run(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "worker.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "artifacts" / "browser").mkdir(parents=True)
    (tmp_path / "artifacts" / "browser" / "signin.png").write_bytes(b"png")
    (tmp_path / "artifacts" / "run-worker").mkdir(parents=True)
    (tmp_path / "artifacts" / "run-worker" / "worker-result.raw.json").write_text(
        "{}",
        encoding="utf-8",
    )
    payload = _worker_result()
    payload["browser_smoke_results"] = [
        {
            "status": "passed",
            "summary": "Registered, signed in, edited a todo, and signed out.",
            "tool": "playwright",
            "command": "node --input-type=module -",
            "exit_code": 0,
            "artifact": "artifacts/browser/signin.png",
            "url": "http://127.0.0.1:5173",
        }
    ]

    result = validate_worker_result_payload(
        payload,
        repo_root=tmp_path,
        result_path="artifacts/run-worker/worker-result.raw.json",
        worker_run_id="run-worker",
        allowed_paths=("src/**",),
        verification_commands=("python -B -m pytest -p no:cacheprovider",),
        acceptance_criteria=("Criterion passes.",),
    )

    assert result.payload["browser_smoke_results"][0]["command"] == "node --input-type=module -"


def test_worker_result_validation_rejects_unbounded_browser_smoke_dev_server(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "worker.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "artifacts" / "browser").mkdir(parents=True)
    (tmp_path / "artifacts" / "browser" / "signin.png").write_bytes(b"png")
    payload = _worker_result()
    payload["browser_smoke_results"] = [
        {
            "status": "passed",
            "summary": "Browser smoke passed.",
            "tool": "manual",
            "command": "npm run dev",
            "exit_code": 0,
            "artifact": "artifacts/browser/signin.png",
            "url": "http://127.0.0.1:5173",
        }
    ]

    with pytest.raises(WorkerResultError, match="unbounded dev server"):
        validate_worker_result_payload(
            payload,
            repo_root=tmp_path,
            result_path="artifacts/run-worker/worker-result.raw.json",
            worker_run_id="run-worker",
            allowed_paths=("src/**",),
            verification_commands=("python -B -m pytest -p no:cacheprovider",),
            acceptance_criteria=("Criterion passes.",),
        )


def test_worker_result_validation_accepts_bounded_browser_smoke_harness(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "worker.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "artifacts" / "browser").mkdir(parents=True)
    (tmp_path / "artifacts" / "browser" / "signin.png").write_bytes(b"png")
    payload = _worker_result()
    payload["browser_smoke_results"] = [
        {
            "status": "passed",
            "summary": "Browser smoke passed.",
            "tool": "playwright",
            "command": "node scripts/smoke-browser.mjs",
            "exit_code": 0,
            "artifact": "artifacts/browser/signin.png",
            "url": "http://127.0.0.1:5173",
        }
    ]

    result = validate_worker_result_payload(
        payload,
        repo_root=tmp_path,
        result_path="artifacts/run-worker/worker-result.raw.json",
        worker_run_id="run-worker",
        allowed_paths=("src/**",),
        verification_commands=("python -B -m pytest -p no:cacheprovider",),
        acceptance_criteria=("Criterion passes.",),
    )

    assert result.payload["browser_smoke_results"][0]["command"] == "node scripts/smoke-browser.mjs"


def test_worker_result_validation_requires_changed_files_within_allowed_paths(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "worker.py").write_text("print('ok')\n", encoding="utf-8")
    result_file = tmp_path / "artifacts" / "run-worker" / "worker-result.raw.json"
    result_file.parent.mkdir(parents=True)
    result_file.write_text("{}", encoding="utf-8")
    payload = _worker_result()

    with pytest.raises(WorkerResultError, match="not covered by allowed_paths"):
        validate_worker_result_payload(
            payload,
            repo_root=tmp_path,
            result_path="artifacts/run-worker/worker-result.raw.json",
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
            result_path="artifacts/run-worker/worker-result.raw.json",
            worker_run_id="run-worker",
            allowed_paths=("src/**",),
            verification_commands=("python -B -m pytest -p no:cacheprovider",),
            acceptance_criteria=("Criterion passes.",),
        )


def test_worker_result_validation_rejects_oversized_json(tmp_path):
    result_path = "artifacts/run-worker/worker-result.raw.json"
    result_file = tmp_path / result_path
    result_file.parent.mkdir(parents=True)
    result_file.write_text(
        json.dumps({"padding": "x" * MAX_WORKER_RESULT_BYTES}),
        encoding="utf-8",
    )

    with pytest.raises(WorkerResultError, match="too large"):
        validate_worker_result_file(
            result_file,
            repo_root=tmp_path,
            result_path=result_path,
            worker_run_id="run-worker",
            allowed_paths=("src/**",),
            verification_commands=("python -B -m pytest -p no:cacheprovider",),
            acceptance_criteria=("Criterion passes.",),
        )


def test_worker_result_ingestion_redacts_unknown_raw_payload_fields(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "worker.py").write_text("print('ok')\n", encoding="utf-8")
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-worker-result",
            slug="worker-result",
            title="Worker Result",
            goal="Store worker results safely.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-worker",
            plan_id="plan-worker-result",
            title="Worker",
            goal="Complete worker result.",
            task_type="AFK",
            status="running",
            acceptance_criteria=["Criterion passes."],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
        )
    )
    store.upsert_worker_run(
        WorkerRunRecord(
            worker_run_id="run-worker",
            task_id="task-worker",
            backend="codex_exec",
            status="running",
        )
    )
    result_path = "artifacts/run-worker/worker-result.raw.json"
    payload = _worker_result()
    payload["secret_notes"] = "do-not-store-this"
    result_file = tmp_path / result_path
    result_file.parent.mkdir(parents=True)
    result_file.write_text(json.dumps(payload), encoding="utf-8")
    original_raw = result_file.read_bytes()

    record = store.ingest_worker_result("run-worker", result_path)

    assert "secret_notes" not in record.raw_payload
    assert "secret_notes" in record.metadata["redacted_raw_payload_keys"]
    assert "do-not-store-this" not in json.dumps(record.raw_payload, sort_keys=True)
    assert result_file.read_bytes() == original_raw
    assert record.source_sha256 == hashlib.sha256(original_raw).hexdigest()
    normalized_path = record.metadata["normalized_result_path"]
    normalized_file = tmp_path / normalized_path
    assert normalized_path == "artifacts/run-worker/worker-result.normalized.json"
    normalized_payload = json.loads(normalized_file.read_text(encoding="utf-8"))
    assert normalized_payload["source_path"] == result_path
    assert normalized_payload["source_sha256"] == record.source_sha256
    assert normalized_payload["worker_result"] == record.raw_payload
    assert (
        record.metadata["normalized_result_sha256"]
        == hashlib.sha256(normalized_file.read_bytes()).hexdigest()
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
        "artifacts": ["artifacts/run-worker/worker-result.raw.json"],
        "completion_notes": "Ready.",
    }
