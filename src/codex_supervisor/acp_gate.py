"""ACP guardrails for target workspaces."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from codex_supervisor.evidence_codec import LAUNCH_PACKET_SHA256_CHECK_PREFIX, has_check_prefix
from codex_supervisor.target_workspace import (
    SUPERVISOR_DIR,
    artifact_to_workspace_relative,
    git_check_ignore,
    has_attempt_run_metadata,
    inspect_product_provenance,
    is_git_worktree,
    is_product_path,
    tracked_supervisor_paths,
)
from codex_supervisor.work_graph import plan_has_durable_completion


@dataclass(frozen=True)
class AcpGateResult:
    """Result of checking whether a target workspace is ready for ACP."""

    ok: bool
    failures: tuple[str, ...]
    warnings: tuple[str, ...]
    changed_product_paths: tuple[str, ...]
    worker_backed_paths: tuple[str, ...]


def check_target_workspace_acp_gate(
    workspace: Path,
    *,
    database_path: Path | None = None,
) -> AcpGateResult:
    """Check target-workspace ACP rules without mutating the workspace."""

    workspace = workspace.resolve()
    database_path = (database_path or workspace / SUPERVISOR_DIR / "planning.sqlite3").resolve()
    failures: list[str] = []
    warnings: list[str] = []

    if not is_git_worktree(workspace):
        failures.append("workspace is not a git worktree")
        return AcpGateResult(
            ok=False,
            failures=tuple(failures),
            warnings=(),
            changed_product_paths=(),
            worker_backed_paths=(),
        )

    ignored = git_check_ignore(workspace, workspace / SUPERVISOR_DIR / "planning.sqlite3")
    if not ignored:
        failures.append(".codex-supervisor/planning.sqlite3 is not ignored by git")

    tracked_supervisor = tracked_supervisor_paths(workspace)
    if tracked_supervisor:
        failures.append(".codex-supervisor has tracked paths: " + "\n".join(tracked_supervisor))

    provenance = inspect_product_provenance(
        workspace,
        database_path=database_path,
    )
    if provenance.inspection_error is not None:
        failures.append(provenance.inspection_error)
    if provenance.unbacked_paths:
        failures.append(
            "product paths lack accepted attempt-run worker evidence: "
            + ", ".join(provenance.unbacked_paths)
        )
    warnings.extend(_substrate_warnings(workspace, database_path=database_path))
    for linked in provenance.linked_worktree_changes:
        failures.append(
            f"linked worktree has unintegrated product changes: "
            f"{linked.worktree}: {', '.join(linked.product_paths)}"
        )

    return AcpGateResult(
        ok=not failures,
        failures=tuple(failures),
        warnings=tuple(warnings),
        changed_product_paths=provenance.changed_product_paths,
        worker_backed_paths=provenance.worker_backed_paths,
    )


def _substrate_warnings(workspace: Path, *, database_path: Path) -> tuple[str, ...]:
    if not database_path.exists():
        return ("planning database is missing; substrate evidence cannot be inspected",)
    warnings: list[str] = []
    with sqlite3.connect(database_path) as connection:
        attempt_rows = connection.execute(
            """select attempts.attempt_id,
                      evidence_bundles.checks_json,
                      evidence_bundles.artifacts_json
               from attempts
               join evidence_bundles on evidence_bundles.attempt_id = attempts.attempt_id
               join acceptance_decisions
                 on acceptance_decisions.attempt_id = attempts.attempt_id
                and acceptance_decisions.bundle_id = evidence_bundles.bundle_id
                and acceptance_decisions.result = 'accepted'
               where attempts.status = 'succeeded'"""
        ).fetchall()
        plan_rows = connection.execute(
            "select plan_id, status from plans where status in ('active', 'done')"
        ).fetchall()
        task_rows = connection.execute(
            "select plan_id, task_id, status, lineage_json from tasks"
        ).fetchall()
        durably_complete_plan_ids = {
            str(plan_id)
            for plan_id, _status in plan_rows
            if plan_has_durable_completion(connection, str(plan_id))
        }

    for attempt_id, checks_json, artifacts_json in attempt_rows:
        checks = _json_string_array(checks_json)
        artifacts = _json_string_array(artifacts_json)
        if not _has_product_artifact(workspace, artifacts):
            continue
        if not has_attempt_run_metadata(
            workspace,
            attempt_id=str(attempt_id),
            task_id=None,
            artifacts=artifacts,
        ):
            warnings.append(f"accepted attempt {attempt_id} lacks launch metadata artifacts")
        if not has_check_prefix(checks, LAUNCH_PACKET_SHA256_CHECK_PREFIX):
            warnings.append(f"accepted attempt {attempt_id} lacks launch packet hash")

    task_records = [
        {
            "plan_id": str(plan_id),
            "task_id": str(task_id),
            "status": str(status),
            "lineage": _lineage(lineage_json),
        }
        for plan_id, task_id, status, lineage_json in task_rows
    ]
    for plan_id, _status in plan_rows:
        plan_id = str(plan_id)
        status = str(_status)
        if plan_id in durably_complete_plan_ids:
            continue
        if status == "done":
            warnings.append(f"completed plan {plan_id} has no accepted final proof task")
        elif status == "active" and not _has_open_task(plan_id, task_records):
            warnings.append(
                f"active plan {plan_id} has no open task and no accepted final proof task"
            )
    return tuple(warnings)


def _has_product_artifact(workspace: Path, artifacts: tuple[str, ...]) -> bool:
    for artifact in artifacts:
        relative = artifact_to_workspace_relative(workspace, artifact)
        if relative is not None and is_product_path(relative):
            return True
    return False


def _has_open_task(plan_id: str, tasks: list[dict[str, object]]) -> bool:
    return any(
        task["plan_id"] == plan_id and task["status"] in {"ready", "running"}
        for task in tasks
    )


def _lineage(raw_json: str) -> tuple[dict[str, str], ...]:
    try:
        decoded = json.loads(raw_json)
    except json.JSONDecodeError:
        return ()
    if not isinstance(decoded, list):
        return ()
    return tuple(item for item in decoded if isinstance(item, dict))


def _json_string_array(raw_json: str) -> tuple[str, ...]:
    try:
        decoded = json.loads(raw_json)
    except json.JSONDecodeError:
        return ()
    if not isinstance(decoded, list):
        return ()
    return tuple(item for item in decoded if isinstance(item, str))
