"""Deterministic factory-loop smoke for release readiness."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from codex_supervisor.planning import (
    PlanAcceptanceCriterionRecord,
    PlanMilestoneRecord,
    PlanProgressRecord,
    PlanRecord,
    SupervisorTaskRecord,
    WorkerRunRecord,
    initialize_planning_database,
)
from codex_supervisor.worker_backends import WorkerLaunchRequest, WorkerLaunchResult
from codex_supervisor.worker_orchestration import orchestrate_worker_launch

FACTORY_LOOP_SMOKE_EVENT_TYPE = "factory_loop_smoke_recorded"
SMOKE_PROJECT_NAME = "factory-loop-smoke-project"
SMOKE_PLAN_ID = "plan-smoke-factory-loop"
SMOKE_TASK_ID = "task-smoke-update-readme"
SMOKE_WORKER_RUN_ID = "worker-run-smoke-update-readme"
SMOKE_ACCEPTANCE = "README.md is updated by the deterministic local backend."
SMOKE_VERIFICATION_COMMAND = "python -B -m pytest -q -p no:cacheprovider"
SMOKE_STAGE_NAMES = (
    "temporary_project_setup",
    "planning_sqlite_initialization",
    "task_shaping_and_claiming",
    "worktree_preparation",
    "local_backend_execution",
    "changed_path_validation",
    "worker_result_ingestion",
    "review_progress_recording",
    "factory_loop_progress_recording",
    "planning_integrity_check",
    "cleanup",
)


@dataclass(frozen=True)
class FactoryLoopSmokeStage:
    name: str
    status: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class FactoryLoopSmokeReport:
    success: bool
    project_name: str
    release_evidence: bool
    cleanup_performed: bool
    workspace_retained: bool
    completed_stages: int
    stages: tuple[FactoryLoopSmokeStage, ...]


def run_factory_loop_smoke(
    *,
    workspace_root: Path | None = None,
    keep_workspace: bool = False,
) -> FactoryLoopSmokeReport:
    """Run a local throwaway-project factory loop without live Codex credentials."""

    if keep_workspace and workspace_root is None:
        msg = "keep_workspace requires workspace_root so retained smoke artifacts are discoverable"
        raise ValueError(msg)
    if workspace_root is None:
        with tempfile.TemporaryDirectory(prefix="codex-supervisor-factory-smoke-") as tmp:
            return _run_factory_loop_smoke_in_workspace(Path(tmp), keep_workspace=keep_workspace)
    workspace_root.mkdir(parents=True, exist_ok=True)
    return _run_factory_loop_smoke_in_workspace(workspace_root, keep_workspace=keep_workspace)


def _run_factory_loop_smoke_in_workspace(
    workspace_root: Path,
    *,
    keep_workspace: bool,
) -> FactoryLoopSmokeReport:
    project_root = workspace_root / SMOKE_PROJECT_NAME
    if project_root.exists():
        shutil.rmtree(project_root)
    stages: list[FactoryLoopSmokeStage] = []
    try:
        project_root.mkdir(parents=True)
        (project_root / "README.md").write_text("# Factory Loop Smoke\n", encoding="utf-8")
        stages.append(
            _stage(
                "temporary_project_setup",
                f"created throwaway project {SMOKE_PROJECT_NAME}",
            )
        )

        store = initialize_planning_database(project_root / "plans" / "planning.sqlite3")
        store.upsert_plan(
            PlanRecord(
                plan_id=SMOKE_PLAN_ID,
                slug="smoke-factory-loop",
                title="Smoke Factory Loop",
                goal="Exercise one throwaway project factory loop.",
                status="active",
            )
        )
        store.upsert_plan_milestone(
            PlanMilestoneRecord(
                milestone_id="milestone-smoke-readme",
                plan_id=SMOKE_PLAN_ID,
                title="README updated",
                status="pending",
                sort_order=1,
            )
        )
        store.upsert_plan_acceptance_criterion(
            PlanAcceptanceCriterionRecord(
                criterion_id="criterion-smoke-readme",
                plan_id=SMOKE_PLAN_ID,
                description=SMOKE_ACCEPTANCE,
                status="pending",
            )
        )
        stages.append(_stage("planning_sqlite_initialization", "initialized planning SQLite"))

        task = _smoke_task()
        store.upsert_supervisor_task(task)
        store.upsert_worker_run(
            WorkerRunRecord(
                worker_run_id=SMOKE_WORKER_RUN_ID,
                task_id=SMOKE_TASK_ID,
                backend="local-smoke",
                status="running",
            )
        )
        stages.append(
            _stage(
                "task_shaping_and_claiming",
                f"created running task {SMOKE_TASK_ID} and worker run {SMOKE_WORKER_RUN_ID}",
            )
        )

        result = orchestrate_worker_launch(
            task,
            backend=_FactoryLoopSmokeBackend(),
            worker_run_id=SMOKE_WORKER_RUN_ID,
            repo_root=project_root,
            result_schema_path="schemas/worker-result.schema.json",
            prompt="Update README.md for the throwaway factory-loop smoke.",
            rendered_goal_contract="Goal Contract: update README.md only.",
            sandbox_mode="workspace-write",
            approval_policy="never",
        )
        stages.append(
            _stage(
                "worktree_preparation",
                f"prepared {result.preparation.layout.worktree_path}",
            )
        )
        stages.append(
            _stage(
                "local_backend_execution",
                f"deterministic local backend completed with status {result.launch_result.status}",
            )
        )
        stages.append(
            _stage(
                "changed_path_validation",
                f"validated changed paths: {', '.join(result.changed_files)}",
            )
        )

        result_path = result.launch_result.result_path
        if result_path is None:
            msg = "factory-loop smoke backend did not write a worker result"
            raise RuntimeError(msg)
        store.ingest_worker_result(SMOKE_WORKER_RUN_ID, result_path)
        stages.append(
            _stage(
                "worker_result_ingestion",
                f"ingested DB-backed result for {SMOKE_WORKER_RUN_ID}",
            )
        )

        store.add_plan_progress(
            PlanProgressRecord(
                progress_id="progress-smoke-review",
                plan_id=SMOKE_PLAN_ID,
                event_type="review_result_recorded",
                summary=(
                    "Recorded zero-finding local review marker for factory-loop smoke; "
                    "not v1 release readiness evidence."
                ),
                details=json.dumps(
                    {
                        "target": SMOKE_TASK_ID,
                        "worker_run_id": SMOKE_WORKER_RUN_ID,
                        "finding_counts": {"total": 0},
                    },
                    sort_keys=True,
                ),
            )
        )
        stages.append(
            _stage(
                "review_progress_recording",
                "recorded zero-finding local review marker; not v1 release readiness evidence",
            )
        )

        store.add_plan_progress(
            PlanProgressRecord(
                progress_id="progress-smoke-factory-loop",
                plan_id=SMOKE_PLAN_ID,
                event_type=FACTORY_LOOP_SMOKE_EVENT_TYPE,
                summary="Recorded completed throwaway factory-loop smoke.",
                details=json.dumps(
                    {
                        "project": SMOKE_PROJECT_NAME,
                        "release_evidence": False,
                        "worker_run_id": SMOKE_WORKER_RUN_ID,
                        "changed_files": list(result.changed_files),
                        "stages": list(SMOKE_STAGE_NAMES),
                    },
                    sort_keys=True,
                ),
            )
        )
        stages.append(
            _stage(
                "factory_loop_progress_recording",
                "recorded factory-loop smoke progress; not v1 release readiness evidence",
            )
        )

        store.update_plan_acceptance_criterion_status("criterion-smoke-readme", "completed")
        store.update_plan_milestone_status("milestone-smoke-readme", "completed")
        store.update_supervisor_task_status(SMOKE_TASK_ID, "completed")
        integrity_output = _run_planning_integrity_check(
            project_root / "plans" / "planning.sqlite3"
        )
        stages.append(_stage("planning_integrity_check", integrity_output))
    finally:
        cleanup_performed = not keep_workspace
        if cleanup_performed and project_root.exists():
            shutil.rmtree(project_root)
    if not keep_workspace:
        stages.append(_stage("cleanup", f"removed throwaway project {SMOKE_PROJECT_NAME}"))
    else:
        stages.append(_stage("cleanup", f"retained throwaway project {SMOKE_PROJECT_NAME}"))
    return FactoryLoopSmokeReport(
        success=all(stage.status == "pass" for stage in stages),
        project_name=SMOKE_PROJECT_NAME,
        release_evidence=False,
        cleanup_performed=not keep_workspace,
        workspace_retained=keep_workspace,
        completed_stages=len(stages),
        stages=tuple(stages),
    )


def _smoke_task() -> SupervisorTaskRecord:
    return SupervisorTaskRecord(
        task_id=SMOKE_TASK_ID,
        plan_id=SMOKE_PLAN_ID,
        title="Update smoke README",
        goal="Use a deterministic local backend to update README.md.",
        task_type="AFK",
        status="running",
        acceptance_criteria=[SMOKE_ACCEPTANCE],
        verification_commands=[SMOKE_VERIFICATION_COMMAND],
        allowed_paths=["README.md"],
        worker_backend="local-smoke",
        review_required=True,
    )


def _stage(name: str, evidence: str) -> FactoryLoopSmokeStage:
    return FactoryLoopSmokeStage(name=name, status="pass", evidence=(evidence,))


class _FactoryLoopSmokeBackend:
    def run(self, request: WorkerLaunchRequest) -> WorkerLaunchResult:
        readme = request.repo_root / "README.md"
        readme.write_text(
            "# Factory Loop Smoke\n\nDeterministic local backend completed.\n",
            encoding="utf-8",
        )
        _write_text(request.repo_root, request.diff_summary_path, "README.md\n")
        _write_text(request.repo_root, request.jsonl_path, '{"event":"assistant.step"}\n')
        _write_text(request.repo_root, request.stdout_path, "local backend stdout\n")
        _write_text(request.repo_root, request.stderr_path, "")
        _write_text(request.repo_root, request.final_message_path, "Factory smoke complete.\n")
        _write_text(
            request.repo_root,
            request.result_path,
            json.dumps(_worker_result_payload(), sort_keys=True),
        )
        return WorkerLaunchResult(
            worker_run_id=request.worker_run_id,
            task_id=request.task_id,
            status="completed",
            result_path=request.result_path,
            exit_code=0,
            duration_seconds=0.0,
            changed_files=("README.md",),
            prompt_path=request.prompt_path,
            jsonl_path=request.jsonl_path,
            stdout_path=request.stdout_path,
            stderr_path=request.stderr_path,
            final_message_path=request.final_message_path,
            diff_summary_path=request.diff_summary_path,
            metadata={"backend": "factory_loop_smoke_local"},
        )


def _worker_result_payload() -> dict[str, object]:
    return {
        "worker_run_id": SMOKE_WORKER_RUN_ID,
        "status": "completed",
        "summary": "Deterministic local backend updated README.md.",
        "changed_files": ["README.md"],
        "tests_run": [
            {
                "command": SMOKE_VERIFICATION_COMMAND,
                "exit_code": 0,
                "summary": "local verification passed",
            }
        ],
        "acceptance_results": {
            SMOKE_ACCEPTANCE: {
                "status": "passed",
                "evidence": "README.md contains the deterministic local completion text.",
            }
        },
        "risks": [],
        "follow_up_tasks": [],
        "artifacts": ["README.md"],
        "completion_notes": (
            "Factory-loop smoke completed with local-only evidence; not v1 release readiness "
            "evidence."
        ),
    }


def _write_text(repo_root: Path, relative_path: str, content: str) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run_planning_integrity_check(db_path: Path) -> str:
    command = (
        sys.executable,
        "-B",
        str(_repo_root() / "scripts" / "check_planning_integrity.py"),
        "--path",
        str(db_path),
    )
    result = subprocess.run(
        command,
        cwd=_repo_root(),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        msg = (
            "factory-loop smoke planning integrity check failed: "
            f"{result.stdout.strip()} {result.stderr.strip()}".strip()
        )
        raise RuntimeError(msg)
    return result.stdout.strip() or "planning integrity passed"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]
