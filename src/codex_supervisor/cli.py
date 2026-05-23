"""Command line entry point for codex-supervisor."""

from __future__ import annotations

import argparse
import sqlite3
from contextlib import suppress
from pathlib import Path

from codex_supervisor.paths import default_planning_database_path
from codex_supervisor.planning import (
    PlanDecisionRecord,
    PlanningSQLiteStore,
    PlanProgressRecord,
    PlanRecord,
    initialize_planning_database,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="codex-supervisor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("plan-init", help="Initialize planning SQLite")
    init_parser.add_argument("--path", type=Path, default=None)
    init_parser.add_argument("--seed-bootstrap-plan", action="store_true", default=False)

    list_parser = subparsers.add_parser("plan-list", help="List plans")
    list_parser.add_argument("--path", type=Path, default=None)
    list_parser.add_argument("--status", default=None)

    args = parser.parse_args(argv)

    if args.command == "plan-init":
        path = args.path or default_planning_database_path()
        store = initialize_planning_database(path)
        if args.seed_bootstrap_plan:
            seed_bootstrap_plan(store)
        print(f"Initialized planning database: {path}")
        return 0

    if args.command == "plan-list":
        path = args.path or default_planning_database_path()
        store = initialize_planning_database(path)
        plans = store.list_plans(status=args.status)
        if not plans:
            print("No plans found.")
            return 0
        for plan in plans:
            print(f"{plan.plan_id}\t{plan.status}\tpriority={plan.priority}\t{plan.title}")
        return 0

    return 1


def seed_bootstrap_plan(store: PlanningSQLiteStore) -> None:
    """Seed the bootstrap plan if it is not already present."""

    store.upsert_plan(
        PlanRecord(
            plan_id="plan-bootstrap-supervisor",
            slug="bootstrap-supervisor",
            title="Bootstrap Codex Supervisor",
            goal=(
                "Create the Python-first supervisor repo with source-of-truth docs, "
                "planning SQLite, source locks, insights, skills, source clones, and handoff."
            ),
            status="active",
            priority=100,
            owner_agent="codex",
            non_goals={
                "full_runtime": "Do not implement the complete worker orchestration runtime yet.",
                "source_vendoring": "Do not vendor cloned source repositories.",
            },
            context={
                "repo_root": "<repo-root>",
                "patterns": [
                    "nlp-stock-prediction planning SQLite",
                    "codex-subagent-testing source locks",
                    "tech-resume insights wiki",
                    "observe-safety source-of-truth validation",
                ],
            },
        )
    )
    with suppress(sqlite3.IntegrityError):
        store.add_plan_decision(
            PlanDecisionRecord(
                decision_id="decision-bootstrap-python-first",
                plan_id="plan-bootstrap-supervisor",
                decision="Build the supervisor core primarily in Python.",
                rationale=(
                    "Python gives strong cross-platform filesystem, SQLite, subprocess, "
                    "and test support."
                ),
            )
        )
    with suppress(sqlite3.IntegrityError):
        store.add_plan_progress(
            PlanProgressRecord(
                progress_id="progress-bootstrap-created",
                plan_id="plan-bootstrap-supervisor",
                event_type="started",
                summary="Bootstrap repository created and initial source-of-truth documents added.",
            )
        )


if __name__ == "__main__":
    raise SystemExit(main())
