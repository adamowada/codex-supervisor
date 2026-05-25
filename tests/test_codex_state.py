from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from codex_supervisor.cli import main
from codex_supervisor.codex_state import (
    build_codex_state_observation_report,
    build_codex_state_reconciliation_dry_run,
    inventory_codex_state,
)

OBSERVED_AT = "2026-05-25T00:00:00Z"


def test_inventory_codex_state_reads_database_table_metadata(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    _create_database(
        codex_home / "state_5.sqlite",
        """
        CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT, transcript TEXT);
        INSERT INTO threads VALUES ('thread-1', 'Stage work', 'private transcript');
        INSERT INTO threads VALUES ('thread-2', 'Review work', 'another private transcript');
        CREATE TABLE thread_spawn_edges (parent_thread_id TEXT, child_thread_id TEXT);
        INSERT INTO thread_spawn_edges VALUES ('thread-1', 'thread-2');
        CREATE TABLE agent_jobs (id TEXT PRIMARY KEY, stderr TEXT);
        INSERT INTO agent_jobs VALUES ('job-1', 'private stderr payload');
        """,
    )
    _create_database(
        codex_home / "sqlite" / "codex-dev.db",
        """
        CREATE TABLE automations (id TEXT PRIMARY KEY, prompt TEXT);
        INSERT INTO automations VALUES ('automation-1', 'private automation prompt');
        CREATE TABLE automation_runs (id TEXT PRIMARY KEY, automation_id TEXT);
        INSERT INTO automation_runs VALUES ('run-1', 'automation-1');
        CREATE TABLE inbox_items (id TEXT PRIMARY KEY, body TEXT);
        INSERT INTO inbox_items VALUES ('inbox-1', 'private inbox body');
        """,
    )

    inventory = inventory_codex_state(codex_home, observed_at=OBSERVED_AT)

    assert inventory.codex_home == str(codex_home.resolve())
    assert inventory.observed_at == OBSERVED_AT
    state_database = _database(inventory, "state_5.sqlite")
    assert state_database.status == "present"
    state_tables = {table.source_table: table for table in state_database.tables}
    assert state_tables["threads"].source_database == "state_5.sqlite"
    assert state_tables["threads"].row_count == 2
    assert state_tables["threads"].source_kinds == ("thread",)
    assert state_tables["thread_spawn_edges"].source_kinds == ("thread_spawn_edge", "thread")
    assert state_tables["agent_jobs"].source_kinds == ("agent_job",)
    desktop_tables = {
        table.source_table: table for table in _database(inventory, "sqlite/codex-dev.db").tables
    }
    assert desktop_tables["automations"].source_kinds == ("automation",)
    assert desktop_tables["automation_runs"].source_kinds == ("automation_run",)
    assert desktop_tables["inbox_items"].source_kinds == ("inbox_item",)


def test_inventory_codex_state_reports_missing_and_corrupt_databases(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "logs_2.sqlite").write_text("not a sqlite database", encoding="utf-8")

    inventory = inventory_codex_state(codex_home, observed_at=OBSERVED_AT)

    goals_database = _database(inventory, "goals_1.sqlite")
    assert goals_database.status == "missing"
    assert goals_database.failure_class == "missing"
    assert goals_database.tables == ()
    logs_database = _database(inventory, "logs_2.sqlite")
    assert logs_database.status == "unreadable"
    assert logs_database.failure_class == "sqlite_error"
    assert logs_database.tables == ()


def test_inventory_codex_state_does_not_mutate_codex_home(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    _create_database(
        codex_home / "state_5.sqlite",
        """
        CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT);
        INSERT INTO threads VALUES ('thread-1', 'Stage work');
        """,
    )
    (codex_home / "logs_2.sqlite").write_text("not a sqlite database", encoding="utf-8")
    before = _file_snapshot(codex_home)

    inventory = inventory_codex_state(codex_home, observed_at=OBSERVED_AT)

    assert _file_snapshot(codex_home) == before
    assert _database(inventory, "goals_1.sqlite").status == "missing"
    assert not (codex_home / "goals_1.sqlite").exists()
    assert not (codex_home / "sqlite" / "codex-dev.db").exists()


def test_codex_state_inventory_cli_prints_json_without_row_payloads(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    codex_home = tmp_path / "codex-home"
    _create_database(
        codex_home / "state_5.sqlite",
        """
        CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT, transcript TEXT);
        INSERT INTO threads VALUES ('thread-1', 'Stage work', 'do-not-print-this-secret');
        """,
    )

    exit_code = main(
        [
            "codex-state-inventory",
            "--codex-home",
            str(codex_home),
            "--observed-at",
            OBSERVED_AT,
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    serialized = json.dumps(payload, sort_keys=True)

    assert exit_code == 0
    assert captured.err == ""
    assert payload["observed_at"] == OBSERVED_AT
    assert "threads" in serialized
    assert "row_count" in serialized
    assert "do-not-print-this-secret" not in serialized
    assert "Stage work" not in serialized


def test_build_codex_state_observation_report_returns_import_contract_fields(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    _create_database(
        codex_home / "state_5.sqlite",
        """
        CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT, transcript TEXT);
        INSERT INTO threads VALUES ('thread-1', 'Stage work', 'private transcript');
        CREATE TABLE thread_spawn_edges (parent_thread_id TEXT, child_thread_id TEXT);
        INSERT INTO thread_spawn_edges VALUES ('thread-1', 'thread-2');
        """,
    )
    inventory = inventory_codex_state(codex_home, observed_at=OBSERVED_AT)

    report = build_codex_state_observation_report(
        inventory,
        linked_plan_id="plan-stage10-codex-state-automation-bridge",
        linked_task_id="task-stage10b-codex-state-observations",
    )

    observations = {observation.source_id: observation for observation in report.observations}
    thread_observation = observations["state_5.sqlite::threads::thread"]
    assert thread_observation.source_kind == "thread"
    assert thread_observation.source_database == "state_5.sqlite"
    assert thread_observation.source_table == "threads"
    assert thread_observation.observed_at == OBSERVED_AT
    assert thread_observation.confidence == "inferred"
    assert thread_observation.linked_plan_id == "plan-stage10-codex-state-automation-bridge"
    assert thread_observation.linked_task_id == "task-stage10b-codex-state-observations"
    assert len(thread_observation.raw_snapshot_hash) == 64
    assert "1 row(s)" in thread_observation.summary
    spawn_observation = observations["state_5.sqlite::thread_spawn_edges::thread_spawn_edge"]
    assert spawn_observation.source_kind == "thread_spawn_edge"
    assert "private transcript" not in json.dumps(report, default=str)


def test_codex_state_observation_hashes_are_deterministic_metadata_only(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    _create_database(
        codex_home / "state_5.sqlite",
        """
        CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT);
        INSERT INTO threads VALUES ('thread-1', 'Stage work');
        """,
    )
    first = build_codex_state_observation_report(
        inventory_codex_state(codex_home, observed_at="2026-05-25T00:00:00Z")
    )
    second = build_codex_state_observation_report(
        inventory_codex_state(codex_home, observed_at="2026-05-25T00:01:00Z")
    )

    assert first.observations[0].raw_snapshot_hash == second.observations[0].raw_snapshot_hash


def test_observation_report_records_nonfatal_findings(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    _create_database(codex_home / "state_5.sqlite", "")
    (codex_home / "logs_2.sqlite").write_text("not a sqlite database", encoding="utf-8")

    report = build_codex_state_observation_report(
        inventory_codex_state(codex_home, observed_at=OBSERVED_AT)
    )

    findings = {finding.source_database: finding for finding in report.findings}
    assert findings["state_5.sqlite"].finding_type == "empty_database"
    assert findings["state_5.sqlite"].failure_class == "empty_database"
    assert findings["goals_1.sqlite"].finding_type == "database_unavailable"
    assert findings["goals_1.sqlite"].failure_class == "missing"
    assert findings["logs_2.sqlite"].failure_class == "sqlite_error"
    assert findings["sqlite/codex-dev.db"].failure_class == "missing"
    assert report.observations == ()


def test_codex_state_observations_cli_prints_json_without_payloads_or_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    codex_home = tmp_path / "codex-home"
    _create_database(
        codex_home / "state_5.sqlite",
        """
        CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT, transcript TEXT);
        INSERT INTO threads VALUES ('thread-1', 'Stage work', 'do-not-print-this-secret');
        """,
    )
    before = _file_snapshot(codex_home)

    exit_code = main(
        [
            "codex-state-observations",
            "--codex-home",
            str(codex_home),
            "--linked-plan-id",
            "plan-stage10-codex-state-automation-bridge",
            "--linked-task-id",
            "task-stage10b-codex-state-observations",
            "--observed-at",
            OBSERVED_AT,
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    serialized = json.dumps(payload, sort_keys=True)

    assert exit_code == 0
    assert captured.err == ""
    assert _file_snapshot(codex_home) == before
    assert payload["linked_plan_id"] == "plan-stage10-codex-state-automation-bridge"
    assert payload["linked_task_id"] == "task-stage10b-codex-state-observations"
    assert payload["observations"][0]["source_id"] == "state_5.sqlite::threads::thread"
    assert payload["observations"][0]["raw_snapshot_hash"]
    assert payload["findings"]
    assert "do-not-print-this-secret" not in serialized
    assert "Stage work" not in serialized


def test_codex_state_reconciliation_dry_run_builds_proposed_actions(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    _create_database(
        codex_home / "state_5.sqlite",
        """
        CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT, transcript TEXT);
        INSERT INTO threads VALUES ('thread-1', 'Stage work', 'private transcript');
        CREATE TABLE agent_jobs (id TEXT PRIMARY KEY, stderr TEXT);
        INSERT INTO agent_jobs VALUES ('job-1', 'private stderr payload');
        """,
    )
    report = build_codex_state_observation_report(
        inventory_codex_state(codex_home, observed_at=OBSERVED_AT),
        linked_plan_id="plan-stage10-codex-state-automation-bridge",
        linked_task_id="task-stage10c-codex-state-reconciliation-dry-run",
    )

    dry_run = build_codex_state_reconciliation_dry_run(
        report,
        known_plan_ids=("plan-stage10-codex-state-automation-bridge",),
        known_task_ids=("task-stage10c-codex-state-reconciliation-dry-run",),
    )

    thread_proposals = [
        proposal
        for proposal in dry_run.proposals
        if proposal.source_id == "state_5.sqlite::threads::thread"
    ]
    assert [proposal.action_type for proposal in thread_proposals] == [
        "follow-up-finding",
        "progress-event",
    ]
    progress_proposal = thread_proposals[1]
    assert progress_proposal.proposal_id.startswith("codex-state-")
    assert progress_proposal.action_status == "proposed"
    assert progress_proposal.source_kind == "thread"
    assert progress_proposal.source_database == "state_5.sqlite"
    assert progress_proposal.source_table == "threads"
    assert progress_proposal.observed_at == OBSERVED_AT
    assert progress_proposal.confidence == "inferred"
    assert progress_proposal.linked_plan_id == "plan-stage10-codex-state-automation-bridge"
    assert progress_proposal.linked_task_id == "task-stage10c-codex-state-reconciliation-dry-run"
    assert progress_proposal.raw_snapshot_hash
    assert "private transcript" not in json.dumps(dry_run, default=str)
    assert "private stderr payload" not in json.dumps(dry_run, default=str)


def test_codex_state_reconciliation_dry_run_is_deterministic(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    _create_database(
        codex_home / "state_5.sqlite",
        """
        CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT);
        INSERT INTO threads VALUES ('thread-1', 'Stage work');
        CREATE TABLE agent_jobs (id TEXT PRIMARY KEY);
        INSERT INTO agent_jobs VALUES ('job-1');
        """,
    )
    report = build_codex_state_observation_report(
        inventory_codex_state(codex_home, observed_at=OBSERVED_AT),
        linked_plan_id="plan-stage10-codex-state-automation-bridge",
        linked_task_id="task-stage10c-codex-state-reconciliation-dry-run",
    )

    first = build_codex_state_reconciliation_dry_run(report)
    second = build_codex_state_reconciliation_dry_run(report)

    assert first.proposals == second.proposals
    assert [(proposal.source_id, proposal.action_type) for proposal in first.proposals] == [
        ("state_5.sqlite::agent_jobs::agent_job", "follow-up-finding"),
        ("state_5.sqlite::agent_jobs::agent_job", "progress-event"),
        ("state_5.sqlite::threads::thread", "follow-up-finding"),
        ("state_5.sqlite::threads::thread", "progress-event"),
    ]


def test_codex_state_reconciliation_dry_run_reports_conflicts_and_empty_reports(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    _create_database(
        codex_home / "state_5.sqlite",
        """
        CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT);
        INSERT INTO threads VALUES ('thread-1', 'Stage work');
        """,
    )
    report = build_codex_state_observation_report(
        inventory_codex_state(codex_home, observed_at=OBSERVED_AT),
        linked_plan_id="missing-plan",
        linked_task_id="missing-task",
    )

    dry_run = build_codex_state_reconciliation_dry_run(
        report,
        known_plan_ids=("plan-stage10-codex-state-automation-bridge",),
        known_task_ids=("task-stage10c-codex-state-reconciliation-dry-run",),
    )

    assert dry_run.proposals == ()
    finding_types = {finding.finding_type for finding in dry_run.findings}
    assert "missing_linked_plan" in finding_types
    assert "missing_linked_task" in finding_types
    assert "database_unavailable" in finding_types

    empty_report = build_codex_state_observation_report(
        inventory_codex_state(tmp_path / "empty-codex-home", observed_at=OBSERVED_AT)
    )
    empty_dry_run = build_codex_state_reconciliation_dry_run(empty_report)

    empty_finding_types = {finding.finding_type for finding in empty_dry_run.findings}
    assert empty_dry_run.proposals == ()
    assert "empty_observation_report" in empty_finding_types
    assert "database_unavailable" in empty_finding_types


def test_codex_state_reconcile_dry_run_cli_prints_json_without_payloads_or_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    planning_path = workspace / "plans" / "planning.sqlite3"
    planning_path.parent.mkdir(parents=True)
    planning_path.write_bytes(b"planning sentinel")
    codex_home = workspace / "codex-home"
    _create_database(
        codex_home / "state_5.sqlite",
        """
        CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT, transcript TEXT);
        INSERT INTO threads VALUES ('thread-1', 'Stage work', 'do-not-print-this-secret');
        """,
    )
    before_workspace = _file_snapshot(workspace)
    monkeypatch.chdir(workspace)

    exit_code = main(
        [
            "codex-state-reconcile-dry-run",
            "--codex-home",
            str(codex_home),
            "--linked-plan-id",
            "plan-stage10-codex-state-automation-bridge",
            "--linked-task-id",
            "task-stage10c-codex-state-reconciliation-dry-run",
            "--known-plan-id",
            "plan-stage10-codex-state-automation-bridge",
            "--known-task-id",
            "task-stage10c-codex-state-reconciliation-dry-run",
            "--observed-at",
            OBSERVED_AT,
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    serialized = json.dumps(payload, sort_keys=True)

    assert exit_code == 0
    assert captured.err == ""
    assert _file_snapshot(workspace) == before_workspace
    assert payload["observed_at"] == OBSERVED_AT
    assert payload["observations"][0]["source_id"] == "state_5.sqlite::threads::thread"
    assert payload["proposals"][0]["action_type"] == "follow-up-finding"
    assert payload["proposals"][0]["action_status"] == "proposed"
    assert payload["proposals"][0]["proposal_id"].startswith("codex-state-")
    assert payload["proposals"][0]["raw_snapshot_hash"]
    assert payload["findings"]
    assert "do-not-print-this-secret" not in serialized
    assert "Stage work" not in serialized


def _create_database(path: Path, script: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(script)


def _database(inventory, relative_path: str):
    return next(
        database for database in inventory.databases if database.relative_path == relative_path
    )


def _file_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
