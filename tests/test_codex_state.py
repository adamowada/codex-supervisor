from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from codex_supervisor.cli import main
from codex_supervisor.codex_state import inventory_codex_state

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
    capsys,
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
