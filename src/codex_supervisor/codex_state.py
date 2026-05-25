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


@dataclass(frozen=True)
class CodexStateReconciliationProposal:
    """Dry-run action proposal for a future planning reconciliation apply step."""

    proposal_id: str
    action_type: str
    action_status: str
    source_kind: str
    source_database: str
    source_table: str
    source_id: str
    observed_at: str
    confidence: str
    linked_plan_id: str
    linked_task_id: str
    raw_snapshot_hash: str
    summary: str


@dataclass(frozen=True)
class CodexStateReconciliationDryRunReport:
    """Non-mutating reconciliation proposal report for Codex local-state observations."""

    codex_home: str
    observed_at: str
    linked_plan_id: str
    linked_task_id: str
    observations: tuple[CodexStateObservation, ...]
    proposals: tuple[CodexStateReconciliationProposal, ...]
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


def build_codex_state_reconciliation_dry_run(
    report: CodexStateObservationReport,
    *,
    known_plan_ids: tuple[str, ...] | None = None,
    known_task_ids: tuple[str, ...] | None = None,
) -> CodexStateReconciliationDryRunReport:
    """Convert observation metadata into deterministic dry-run planning proposals.

    This helper is intentionally pure: it does not open Codex databases, planning SQLite, or the
    filesystem. Callers may pass known planning IDs to surface missing-target conflicts as findings.
    """

    known_plans = None if known_plan_ids is None else frozenset(known_plan_ids)
    known_tasks = None if known_task_ids is None else frozenset(known_task_ids)
    findings = list(report.findings)
    proposals: list[CodexStateReconciliationProposal] = []

    if not report.observations:
        findings.append(
            CodexStateReconciliationFinding(
                finding_type="empty_observation_report",
                source_database="",
                source_table="",
                source_id="codex_state_observations::__report__",
                observed_at=report.observed_at,
                failure_class="empty_observation_report",
                summary="Observation report contains no table-level observations to reconcile.",
            )
        )

    for observation in _sorted_observations(report.observations):
        target_findings = _target_findings_for_observation(
            observation,
            known_plan_ids=known_plans,
            known_task_ids=known_tasks,
        )
        if target_findings:
            findings.extend(target_findings)
            continue
        proposals.extend(
            _proposal_for_observation(observation, action_type)
            for action_type in _proposal_action_types(observation)
        )

    return CodexStateReconciliationDryRunReport(
        codex_home=report.codex_home,
        observed_at=report.observed_at,
        linked_plan_id=report.linked_plan_id,
        linked_task_id=report.linked_task_id,
        observations=tuple(_sorted_observations(report.observations)),
        proposals=tuple(
            sorted(
                proposals,
                key=lambda proposal: (
                    proposal.source_database,
                    proposal.source_table,
                    proposal.source_kind,
                    proposal.source_id,
                    _proposal_action_order(proposal.action_type),
                ),
            )
        ),
        findings=tuple(
            sorted(
                findings,
                key=lambda finding: (
                    finding.source_database,
                    finding.source_table,
                    finding.source_id,
                    finding.finding_type,
                    finding.failure_class,
                ),
            )
        ),
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


def _sorted_observations(
    observations: tuple[CodexStateObservation, ...],
) -> tuple[CodexStateObservation, ...]:
    return tuple(
        sorted(
            observations,
            key=lambda observation: (
                observation.source_database,
                observation.source_table,
                observation.source_kind,
                observation.source_id,
            ),
        )
    )


def _target_findings_for_observation(
    observation: CodexStateObservation,
    *,
    known_plan_ids: frozenset[str] | None,
    known_task_ids: frozenset[str] | None,
) -> tuple[CodexStateReconciliationFinding, ...]:
    findings: list[CodexStateReconciliationFinding] = []
    if (
        observation.linked_plan_id
        and known_plan_ids is not None
        and observation.linked_plan_id not in known_plan_ids
    ):
        findings.append(
            CodexStateReconciliationFinding(
                finding_type="missing_linked_plan",
                source_database=observation.source_database,
                source_table=observation.source_table,
                source_id=observation.source_id,
                observed_at=observation.observed_at,
                failure_class="missing_linked_plan",
                summary=(
                    f"{observation.source_id} references missing plan "
                    f"{observation.linked_plan_id!r}; no dry-run actions were proposed."
                ),
            )
        )
    if (
        observation.linked_task_id
        and known_task_ids is not None
        and observation.linked_task_id not in known_task_ids
    ):
        findings.append(
            CodexStateReconciliationFinding(
                finding_type="missing_linked_task",
                source_database=observation.source_database,
                source_table=observation.source_table,
                source_id=observation.source_id,
                observed_at=observation.observed_at,
                failure_class="missing_linked_task",
                summary=(
                    f"{observation.source_id} references missing task "
                    f"{observation.linked_task_id!r}; no dry-run actions were proposed."
                ),
            )
        )
    return tuple(findings)


def _proposal_action_types(observation: CodexStateObservation) -> tuple[str, ...]:
    action_types = ["follow-up-finding"]
    if observation.linked_plan_id:
        action_types.append("progress-event")
    return tuple(action_types)


def _proposal_action_order(action_type: str) -> int:
    order = {
        "follow-up-finding": 0,
        "progress-event": 1,
    }
    return order[action_type]


def _proposal_for_observation(
    observation: CodexStateObservation,
    action_type: str,
) -> CodexStateReconciliationProposal:
    return CodexStateReconciliationProposal(
        proposal_id=_proposal_id(observation, action_type),
        action_type=action_type,
        action_status="proposed",
        source_kind=observation.source_kind,
        source_database=observation.source_database,
        source_table=observation.source_table,
        source_id=observation.source_id,
        observed_at=observation.observed_at,
        confidence=observation.confidence,
        linked_plan_id=observation.linked_plan_id,
        linked_task_id=observation.linked_task_id,
        raw_snapshot_hash=observation.raw_snapshot_hash,
        summary=_proposal_summary(observation, action_type),
    )


def _proposal_id(observation: CodexStateObservation, action_type: str) -> str:
    digest = _metadata_hash(
        {
            "action_type": action_type,
            "linked_plan_id": observation.linked_plan_id,
            "linked_task_id": observation.linked_task_id,
            "raw_snapshot_hash": observation.raw_snapshot_hash,
            "source_database": observation.source_database,
            "source_id": observation.source_id,
            "source_kind": observation.source_kind,
            "source_table": observation.source_table,
        }
    )
    return f"codex-state-{digest[:24]}"


def _proposal_summary(observation: CodexStateObservation, action_type: str) -> str:
    if action_type == "artifact-link":
        return (
            f"Propose linking metadata snapshot {observation.raw_snapshot_hash} for "
            f"{observation.source_id} as planning evidence."
        )
    if action_type == "progress-event":
        target = observation.linked_task_id or observation.linked_plan_id
        return f"Propose recording a planning progress event for {target}: {observation.summary}"
    if action_type == "follow-up-finding":
        return (
            f"Propose creating a follow-up reconciliation finding for "
            f"{observation.source_kind} observation {observation.source_id}."
        )
    raise ValueError(f"unknown reconciliation proposal action type: {action_type}")


def _metadata_hash(payload: dict[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(serialized).hexdigest()
