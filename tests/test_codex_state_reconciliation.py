from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from codex_supervisor.cli import main
from codex_supervisor.codex_state import (
    CodexStateReconciliationDryRunReport,
    build_codex_state_observation_report,
    build_codex_state_reconciliation_dry_run,
    inventory_codex_state,
)
from codex_supervisor.codex_state_reconciliation import (
    CODEX_STATE_APPLIED_EVENT,
    CODEX_STATE_FINDING_EVENT,
    CODEX_STATE_SNAPSHOT_RELATIONSHIP,
    apply_codex_state_reconciliation_report,
)
from codex_supervisor.planning import (
    PlanRecord,
    SupervisorTaskRecord,
    initialize_planning_database,
)

OBSERVED_AT = "2026-05-25T00:00:00Z"
PLAN_ID = "plan-stage10-codex-state-automation-bridge"
TASK_ID = "task-stage10d-codex-state-reconciliation-apply"


def test_apply_codex_state_reconciliation_report_writes_append_only_evidence(
    tmp_path: Path,
) -> None:
    store = _planning_store(tmp_path)
    report = _dry_run_report(tmp_path, linked_plan_id=PLAN_ID, linked_task_id=TASK_ID)
    approved_ids = tuple(proposal.proposal_id for proposal in report.proposals)
    before_counts = _table_counts(store.path)

    apply_report = apply_codex_state_reconciliation_report(
        store,
        report,
        approved_proposal_ids=approved_ids,
    )

    assert [applied.action_type for applied in apply_report.applied] == [
        "artifact-link",
        "follow-up-finding",
        "progress-event",
    ]
    applied_progress = {applied.action_type: applied for applied in apply_report.applied}[
        "progress-event"
    ]
    assert applied_progress.action_status == "applied"
    assert applied_progress.proposal_id.startswith("codex-state-")
    assert applied_progress.source_kind == "thread"
    assert applied_progress.source_database == "state_5.sqlite"
    assert applied_progress.source_table == "threads"
    assert applied_progress.source_id == "state_5.sqlite::threads::thread"
    assert applied_progress.observed_at == OBSERVED_AT
    assert applied_progress.confidence == "inferred"
    assert applied_progress.linked_plan_id == PLAN_ID
    assert applied_progress.linked_task_id == TASK_ID
    assert applied_progress.raw_snapshot_hash
    progress_rows = store.list_plan_progress(plan_id=PLAN_ID)
    event_types = {progress.event_type for progress in progress_rows}
    assert CODEX_STATE_APPLIED_EVENT in event_types
    assert CODEX_STATE_FINDING_EVENT in event_types
    details = json.loads(
        next(
            progress.details
            for progress in progress_rows
            if progress.progress_id == applied_progress.progress_id
        )
    )
    assert details["proposal_id"] == applied_progress.proposal_id
    assert details["action_status"] == "applied"
    assert details["raw_snapshot_hash"] == applied_progress.raw_snapshot_hash
    artifact_links = store.list_plan_artifact_links(plan_id=PLAN_ID)
    assert any(link.relationship == CODEX_STATE_SNAPSHOT_RELATIONSHIP for link in artifact_links)
    after_counts = _table_counts(store.path)
    assert after_counts["supervisor_tasks"] == before_counts["supervisor_tasks"]
    assert after_counts["plan_milestones"] == before_counts["plan_milestones"]
    assert after_counts["plan_acceptance_criteria"] == before_counts["plan_acceptance_criteria"]
    assert after_counts["worker_runs"] == before_counts["worker_runs"]


def test_apply_codex_state_reconciliation_report_is_idempotent(
    tmp_path: Path,
) -> None:
    store = _planning_store(tmp_path)
    report = _dry_run_report(tmp_path, linked_plan_id=PLAN_ID, linked_task_id=TASK_ID)
    approved_id = report.proposals[0].proposal_id

    first = apply_codex_state_reconciliation_report(
        store,
        report,
        approved_proposal_ids=(approved_id,),
    )
    second = apply_codex_state_reconciliation_report(
        store,
        report,
        approved_proposal_ids=(approved_id,),
    )

    assert len(first.applied) == 1
    assert second.applied == ()
    duplicate_skip = next(skip for skip in second.skipped if skip.proposal_id == approved_id)
    assert duplicate_skip.skip_reason == "duplicate_already_applied"


def test_apply_codex_state_reconciliation_report_surfaces_conflicts_and_unapproved(
    tmp_path: Path,
) -> None:
    store = _planning_store(tmp_path)
    missing_target_report = _dry_run_report(
        tmp_path,
        linked_plan_id="missing-plan",
        linked_task_id="missing-task",
    )
    approved_id = missing_target_report.proposals[0].proposal_id

    conflict_report = apply_codex_state_reconciliation_report(
        store,
        missing_target_report,
        approved_proposal_ids=(approved_id,),
    )

    assert conflict_report.applied == ()
    assert {finding.finding_type for finding in conflict_report.findings} >= {
        "missing_linked_plan",
        "missing_linked_task",
        "database_unavailable",
    }
    assert conflict_report.skipped[0].skip_reason == "target_conflict"

    unsupported = replace(
        missing_target_report.proposals[0],
        linked_plan_id=PLAN_ID,
        linked_task_id=TASK_ID,
        action_type="unsupported-action",
    )
    unsupported_report = replace(missing_target_report, proposals=(unsupported,), findings=())
    unsupported_apply = apply_codex_state_reconciliation_report(
        store,
        unsupported_report,
        approved_proposal_ids=(unsupported.proposal_id,),
    )

    assert unsupported_apply.applied == ()
    assert unsupported_apply.skipped[0].skip_reason == "unsupported_action_type"
    assert {finding.finding_type for finding in unsupported_apply.findings} == {
        "unsupported_action_type"
    }

    unapproved_report = apply_codex_state_reconciliation_report(
        store,
        _dry_run_report(tmp_path, linked_plan_id=PLAN_ID, linked_task_id=TASK_ID),
        approved_proposal_ids=("codex-state-missing-reviewed-id",),
    )

    assert unapproved_report.applied == ()
    assert {skip.skip_reason for skip in unapproved_report.skipped} == {"not_approved"}
    assert any(
        finding.finding_type == "unknown_approved_proposal"
        and finding.source_id == "codex-state-missing-reviewed-id"
        for finding in unapproved_report.findings
    )


def test_codex_state_reconcile_apply_cli_uses_reviewed_report_without_codex_home_reads(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = _planning_store(tmp_path)
    codex_home = tmp_path / "codex-home"
    _create_database(
        codex_home / "state_5.sqlite",
        """
        CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT, transcript TEXT);
        INSERT INTO threads VALUES ('thread-1', 'Stage work', 'do-not-print-this-secret');
        """,
    )
    report = _dry_run_report(
        tmp_path,
        linked_plan_id=PLAN_ID,
        linked_task_id=TASK_ID,
        codex_home=codex_home,
    )
    report_path = tmp_path / "reviewed-report.json"
    report_path.write_text(json.dumps(asdict(report), sort_keys=True), encoding="utf-8")
    before_codex_home = _file_snapshot(codex_home)
    before_counts = _table_counts(store.path)

    exit_code = main(
        [
            "codex-state-reconcile-apply",
            "--path",
            str(store.path),
            "--report-path",
            str(report_path),
            "--approve-proposal-id",
            report.proposals[0].proposal_id,
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    serialized = json.dumps(payload, sort_keys=True)
    after_counts = _table_counts(store.path)

    assert exit_code == 0
    assert captured.err == ""
    assert _file_snapshot(codex_home) == before_codex_home
    assert payload["applied"][0]["proposal_id"] == report.proposals[0].proposal_id
    assert payload["applied"][0]["action_status"] == "applied"
    assert payload["skipped"]
    assert after_counts["supervisor_tasks"] == before_counts["supervisor_tasks"]
    assert after_counts["plan_milestones"] == before_counts["plan_milestones"]
    assert after_counts["plan_acceptance_criteria"] == before_counts["plan_acceptance_criteria"]
    assert after_counts["worker_runs"] == before_counts["worker_runs"]
    assert "do-not-print-this-secret" not in serialized
    assert "Stage work" not in serialized


def _planning_store(tmp_path: Path):
    store = initialize_planning_database(tmp_path / "planning.sqlite3")
    store.upsert_plan(
        PlanRecord(
            plan_id=PLAN_ID,
            slug="stage10",
            title="Stage 10",
            goal="Apply Codex state reconciliation reports safely.",
            status="active",
            priority=82,
        )
    )
    store.upsert_supervisor_task(
        SupervisorTaskRecord(
            task_id=TASK_ID,
            plan_id=PLAN_ID,
            title="Stage 10D",
            goal="Apply reviewed Codex state reconciliation proposals.",
            task_type="AFK",
            status="ready",
            acceptance_criteria=["accepted"],
            verification_commands=[
                "uv run --no-sync python -B -m pytest "
                "tests/test_codex_state_reconciliation.py -q -p no:cacheprovider"
            ],
            allowed_paths=["src/codex_supervisor/codex_state_reconciliation.py"],
            blocked_by=[],
        ),
        validate_current_queue_contract=True,
    )
    return store


def _dry_run_report(
    tmp_path: Path,
    *,
    linked_plan_id: str,
    linked_task_id: str,
    codex_home: Path | None = None,
) -> CodexStateReconciliationDryRunReport:
    home = codex_home or tmp_path / f"codex-home-{linked_plan_id}-{linked_task_id}"
    if not (home / "state_5.sqlite").exists():
        _create_database(
            home / "state_5.sqlite",
            """
            CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT, transcript TEXT);
            INSERT INTO threads VALUES ('thread-1', 'Stage work', 'private transcript');
            """,
        )
    observation_report = build_codex_state_observation_report(
        inventory_codex_state(home, observed_at=OBSERVED_AT),
        linked_plan_id=linked_plan_id,
        linked_task_id=linked_task_id,
    )
    return build_codex_state_reconciliation_dry_run(observation_report)


def _create_database(path: Path, script: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(script)


def _table_counts(path: Path) -> dict[str, int]:
    with sqlite3.connect(path) as connection:
        return {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "plan_progress_events",
                "plan_artifact_links",
                "plan_milestones",
                "plan_acceptance_criteria",
                "supervisor_tasks",
                "worker_runs",
            )
        }


def _file_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
