"""Privacy-safe read-only inventory for local Codex state databases."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast

CODEX_STATE_DATABASE_STATUSES = ("present", "missing", "unreadable")


@dataclass(frozen=True)
class CodexStateDatabaseSpec:
    """One documented Codex local-state SQLite database."""

    name: str
    relative_path: str
    expected_source_kinds: tuple[str, ...]
    summary: str


@dataclass(frozen=True)
class CodexStateTableInventory:
    """Metadata-only inventory for one SQLite table."""

    source_database: str
    source_table: str
    source_kinds: tuple[str, ...]
    row_count: int


@dataclass(frozen=True)
class CodexStateDatabaseInventory:
    """Metadata-only inventory result for one documented Codex database."""

    name: str
    relative_path: str
    status: str
    failure_class: str | None
    failure_reason: str | None
    tables: tuple[CodexStateTableInventory, ...]


@dataclass(frozen=True)
class CodexStateInventory:
    """Metadata-only inventory for a Codex home directory."""

    codex_home: str
    observed_at: str
    databases: tuple[CodexStateDatabaseInventory, ...]


@dataclass(frozen=True)
class CodexStateObservation:
    """Privacy-safe table-level observation shaped for future reconciliation."""

    source_kind: str
    source_database: str
    source_table: str
    source_id: str
    observed_at: str
    confidence: str
    summary: str
    linked_plan_id: str
    linked_task_id: str
    raw_snapshot_hash: str


@dataclass(frozen=True)
class CodexStateReconciliationFinding:
    """Nonfatal finding that future reconciliation should inspect."""

    finding_type: str
    source_database: str
    source_table: str
    source_id: str
    observed_at: str
    failure_class: str
    summary: str


@dataclass(frozen=True)
class CodexStateObservationReport:
    """Privacy-safe observation report derived from a local Codex state inventory."""

    codex_home: str
    observed_at: str
    linked_plan_id: str
    linked_task_id: str
    observations: tuple[CodexStateObservation, ...]
    findings: tuple[CodexStateReconciliationFinding, ...]


DOCUMENTED_CODEX_STATE_DATABASES = (
    CodexStateDatabaseSpec(
        name="state",
        relative_path="state_5.sqlite",
        expected_source_kinds=(
            "thread",
            "thread_spawn_edge",
            "agent_job",
        ),
        summary="Threads, spawn edges, dynamic tools, and agent jobs when present.",
    ),
    CodexStateDatabaseSpec(
        name="goals",
        relative_path="goals_1.sqlite",
        expected_source_kinds=("thread_goal",),
        summary="Per-thread goal rows when present.",
    ),
    CodexStateDatabaseSpec(
        name="logs",
        relative_path="logs_2.sqlite",
        expected_source_kinds=("log_summary",),
        summary="Local execution and application logs for workflow analytics.",
    ),
    CodexStateDatabaseSpec(
        name="desktop",
        relative_path="sqlite/codex-dev.db",
        expected_source_kinds=(
            "automation",
            "automation_run",
            "inbox_item",
        ),
        summary="Automation, automation run, and inbox tables when present.",
    ),
)


def inventory_codex_state(
    codex_home: Path | str,
    *,
    observed_at: str | None = None,
) -> CodexStateInventory:
    """Inventory documented Codex SQLite databases without reading row payloads."""

    resolved_home = Path(codex_home).expanduser().resolve(strict=False)
    observation_time = observed_at or datetime.now(UTC).replace(microsecond=0).isoformat()
    return CodexStateInventory(
        codex_home=str(resolved_home),
        observed_at=observation_time,
        databases=tuple(
            _inventory_database(resolved_home, spec) for spec in DOCUMENTED_CODEX_STATE_DATABASES
        ),
    )


def build_codex_state_observation_report(
    inventory: CodexStateInventory,
    *,
    linked_plan_id: str = "",
    linked_task_id: str = "",
) -> CodexStateObservationReport:
    """Build privacy-safe import observations and findings from inventory metadata."""

    observations: list[CodexStateObservation] = []
    findings: list[CodexStateReconciliationFinding] = []
    for database in inventory.databases:
        if database.status != "present":
            findings.append(_database_finding(database, inventory.observed_at))
            continue
        if not database.tables:
            findings.append(
                CodexStateReconciliationFinding(
                    finding_type="empty_database",
                    source_database=database.relative_path,
                    source_table="",
                    source_id=f"{database.relative_path}::__database__",
                    observed_at=inventory.observed_at,
                    failure_class="empty_database",
                    summary=f"{database.relative_path} is present but has no user tables.",
                )
            )
            continue
        for table in database.tables:
            observations.extend(
                _table_observation(
                    table,
                    source_kind,
                    observed_at=inventory.observed_at,
                    linked_plan_id=linked_plan_id,
                    linked_task_id=linked_task_id,
                )
                for source_kind in table.source_kinds
            )
    return CodexStateObservationReport(
        codex_home=inventory.codex_home,
        observed_at=inventory.observed_at,
        linked_plan_id=linked_plan_id,
        linked_task_id=linked_task_id,
        observations=tuple(observations),
        findings=tuple(findings),
    )


def _inventory_database(
    codex_home: Path,
    spec: CodexStateDatabaseSpec,
) -> CodexStateDatabaseInventory:
    database_path = codex_home / Path(spec.relative_path)
    if not database_path.exists():
        return CodexStateDatabaseInventory(
            name=spec.name,
            relative_path=spec.relative_path,
            status="missing",
            failure_class="missing",
            failure_reason="database file is not present",
            tables=(),
        )
    if not database_path.is_file():
        return CodexStateDatabaseInventory(
            name=spec.name,
            relative_path=spec.relative_path,
            status="unreadable",
            failure_class="not_a_file",
            failure_reason="database path is not a file",
            tables=(),
        )
    try:
        with _connect_read_only(database_path) as connection:
            tables = _inventory_tables(connection, spec)
    except PermissionError as exc:
        return _failed_database_inventory(spec, "permission_error", str(exc))
    except sqlite3.DatabaseError as exc:
        return _failed_database_inventory(spec, "sqlite_error", str(exc))
    except OSError as exc:
        return _failed_database_inventory(spec, "os_error", str(exc))
    return CodexStateDatabaseInventory(
        name=spec.name,
        relative_path=spec.relative_path,
        status="present",
        failure_class=None,
        failure_reason=None,
        tables=tables,
    )


def _connect_read_only(database_path: Path) -> sqlite3.Connection:
    uri = f"{database_path.resolve(strict=False).as_uri()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _inventory_tables(
    connection: sqlite3.Connection,
    spec: CodexStateDatabaseSpec,
) -> tuple[CodexStateTableInventory, ...]:
    table_rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    inventories: list[CodexStateTableInventory] = []
    for row in table_rows:
        table_name = cast(str, row[0])
        count_row = connection.execute(
            f"SELECT COUNT(*) FROM {_quote_identifier(table_name)}"
        ).fetchone()
        row_count = 0 if count_row is None else int(count_row[0])
        inventories.append(
            CodexStateTableInventory(
                source_database=spec.relative_path,
                source_table=table_name,
                source_kinds=_source_kinds_for_table(table_name, spec),
                row_count=row_count,
            )
        )
    return tuple(inventories)


def _source_kinds_for_table(
    table_name: str,
    spec: CodexStateDatabaseSpec,
) -> tuple[str, ...]:
    normalized = table_name.lower()
    kinds: list[str] = []
    if "spawn" in normalized or ("edge" in normalized and "thread" in normalized):
        kinds.append("thread_spawn_edge")
    if "thread" in normalized or "conversation" in normalized or "session" in normalized:
        kinds.append("thread")
    if "goal" in normalized:
        kinds.append("thread_goal")
    if "agent" in normalized and "job" in normalized or normalized in {"jobs", "job_runs"}:
        kinds.append("agent_job")
    if "automation_run" in normalized or ("automation" in normalized and "run" in normalized):
        kinds.append("automation_run")
    elif "automation" in normalized:
        kinds.append("automation")
    if "inbox" in normalized:
        kinds.append("inbox_item")
    if "log" in normalized:
        kinds.append("log_summary")
    if kinds:
        return tuple(dict.fromkeys(kinds))
    return spec.expected_source_kinds


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _failed_database_inventory(
    spec: CodexStateDatabaseSpec,
    failure_class: str,
    failure_reason: str,
) -> CodexStateDatabaseInventory:
    return CodexStateDatabaseInventory(
        name=spec.name,
        relative_path=spec.relative_path,
        status="unreadable",
        failure_class=failure_class,
        failure_reason=failure_reason,
        tables=(),
    )


def _database_finding(
    database: CodexStateDatabaseInventory,
    observed_at: str,
) -> CodexStateReconciliationFinding:
    failure_class = database.failure_class or database.status
    failure_reason = database.failure_reason or "database could not be inventoried"
    return CodexStateReconciliationFinding(
        finding_type="database_unavailable",
        source_database=database.relative_path,
        source_table="",
        source_id=f"{database.relative_path}::__database__",
        observed_at=observed_at,
        failure_class=failure_class,
        summary=f"{database.relative_path} status={database.status}: {failure_reason}",
    )


def _table_observation(
    table: CodexStateTableInventory,
    source_kind: str,
    *,
    observed_at: str,
    linked_plan_id: str,
    linked_task_id: str,
) -> CodexStateObservation:
    source_id = f"{table.source_database}::{table.source_table}::{source_kind}"
    return CodexStateObservation(
        source_kind=source_kind,
        source_database=table.source_database,
        source_table=table.source_table,
        source_id=source_id,
        observed_at=observed_at,
        confidence="inferred",
        summary=(
            f"{table.source_database}.{table.source_table} has {table.row_count} row(s) "
            f"and maps to {source_kind} observations."
        ),
        linked_plan_id=linked_plan_id,
        linked_task_id=linked_task_id,
        raw_snapshot_hash=_metadata_hash(
            {
                "row_count": table.row_count,
                "source_database": table.source_database,
                "source_id": source_id,
                "source_kind": source_kind,
                "source_table": table.source_table,
            }
        ),
    )


def _metadata_hash(payload: dict[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(serialized).hexdigest()
