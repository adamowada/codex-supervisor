"""Worker Result ingestion interface shared by CLI, MCP, and Story Loop callers."""

from __future__ import annotations

from typing import Protocol

from codex_supervisor.planning import WorkerResultRecord


class WorkerResultIngestionStore(Protocol):
    """Planning-store surface needed to complete worker runs from result evidence."""

    def ingest_worker_result(
        self,
        worker_run_id: str,
        result_path: str,
        *,
        failure_class: str = "worker_result_invalid",
    ) -> WorkerResultRecord: ...

    def update_worker_run_status(
        self,
        worker_run_id: str,
        status: str,
        *,
        failure_class: str | None = None,
        completed_at: str | None = None,
        result_path: str | None = None,
        result_id: str | None = None,
    ) -> None: ...


def ingest_worker_result_path(
    store: WorkerResultIngestionStore,
    worker_run_id: str,
    result_path: str,
    *,
    failure_class: str = "worker_result_invalid",
) -> WorkerResultRecord:
    """Validate and ingest one Worker Result JSON path for a worker run."""

    return store.ingest_worker_result(
        worker_run_id,
        result_path,
        failure_class=failure_class,
    )


def complete_worker_run_with_existing_result_id(
    store: WorkerResultIngestionStore,
    worker_run_id: str,
    result_id: str,
) -> None:
    """Complete a worker run with an already-ingested Worker Result record."""

    store.update_worker_run_status(worker_run_id, "completed", result_id=result_id)


def complete_worker_run_with_result(
    store: WorkerResultIngestionStore,
    worker_run_id: str,
    *,
    result_path: str | None = None,
    result_id: str | None = None,
) -> WorkerResultRecord | None:
    """Complete a run from either a transient result path or an existing result id."""

    if result_path is None and result_id is None:
        msg = "completed worker runs require result_path or result_id"
        raise ValueError(msg)
    if result_path is not None:
        return ingest_worker_result_path(store, worker_run_id, result_path)
    if result_id is None:
        msg = "completed worker runs require result_path or result_id"
        raise ValueError(msg)
    complete_worker_run_with_existing_result_id(store, worker_run_id, result_id)
    return None
