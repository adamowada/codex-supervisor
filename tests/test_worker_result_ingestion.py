from __future__ import annotations

import json
from pathlib import Path

from codex_supervisor.cli import main
from codex_supervisor.planning import (
    PlanRecord,
    SupervisorTaskRecord,
    initialize_planning_database,
    open_existing_planning_database,
)
from codex_supervisor.worker_backends import ContractWorkerBackend, WorkerLaunchRequest
from codex_supervisor.worker_result_ingestion import ingest_worker_result_path


def test_worker_result_ingestion_module_completes_run(tmp_path: Path) -> None:
    store = _prepare_claimed_worker_with_result(tmp_path)

    result = ingest_worker_result_path(
        store,
        "run-test",
        "artifacts/run-test/worker-result.raw.json",
    )

    read_store = open_existing_planning_database(tmp_path / "plans" / "planning.sqlite3")
    run = read_store.list_worker_runs(task_id="task-test")[0]
    assert result.changed_files == ["src/worker.py"]
    assert run.status == "completed"
    assert run.result_id == result.result_id


def test_worker_result_ingest_cli_completes_run(
    tmp_path: Path,
    capsys,
) -> None:
    _prepare_claimed_worker_with_result(tmp_path)
    db_path = tmp_path / "plans" / "planning.sqlite3"

    exit_code = main(
        [
            "worker-result-ingest",
            "--path",
            str(db_path),
            "--worker-run-id",
            "run-test",
            "--result-path",
            "artifacts/run-test/worker-result.raw.json",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    read_store = open_existing_planning_database(db_path)
    run = read_store.list_worker_runs(task_id="task-test")[0]
    assert payload["status"] == "completed"
    assert payload["result_id"] == run.result_id


def _prepare_claimed_worker_with_result(tmp_path: Path):
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-test",
            slug="test",
            title="Test Plan",
            goal="Ingest worker results.",
            status="active",
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id="task-test",
            plan_id="plan-test",
            title="Task",
            goal="Complete through result ingestion.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["Criterion passes."],
            verification_commands=["python -B -m pytest -p no:cacheprovider"],
            allowed_paths=["src/**"],
            review_required=False,
        )
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "worker.py").write_text("print('ok')\n", encoding="utf-8")
    claim = store.claim_next_ready_afk_task(worker_run_id="run-test", backend="codex_exec")
    assert claim is not None
    request = WorkerLaunchRequest(
        worker_run_id="run-test",
        task_id="task-test",
        repo_root=tmp_path,
        worktree_path=tmp_path,
        result_path="artifacts/run-test/worker-result.raw.json",
        prompt_path="runs/run-test/prompt.md",
        jsonl_path="runs/run-test/events.jsonl",
        stdout_path="runs/run-test/stdout.txt",
        stderr_path="runs/run-test/stderr.txt",
        final_message_path="runs/run-test/final-message.txt",
        diff_summary_path="runs/run-test/diff-summary.txt",
        evidence_manifest_path="artifacts/run-test/evidence-manifest.json",
        result_schema_path="schemas/worker-result.schema.json",
        prompt="Do it.",
        rendered_goal_contract="Goal Contract",
        sandbox_mode="workspace-write",
        approval_policy="never",
        allowed_paths=("src/**",),
        verification_commands=("python -B -m pytest -p no:cacheprovider",),
        acceptance_criteria=("Criterion passes.",),
    )
    ContractWorkerBackend(changed_files=("src/worker.py",)).run(request)
    return store
