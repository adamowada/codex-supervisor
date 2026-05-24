"""Command line entry point for codex-supervisor."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, cast

from codex_supervisor.goal_contracts import (
    render_goal_contract,
    render_goal_contract_markdown,
)
from codex_supervisor.paths import default_planning_database_path
from codex_supervisor.planning import (
    CLAIM_WORKER_RUN_STATUSES,
    CRITERION_STATUSES,
    CURRENT_QUEUE_PLAN_STATUSES,
    MILESTONE_STATUSES,
    PLAN_STATUSES,
    TASK_STATUSES,
    TASK_TYPES,
    WORKER_RUN_STATUSES,
    PlanAcceptanceCriterionRecord,
    PlanArtifactLinkRecord,
    PlanCommitLinkRecord,
    PlanDecisionRecord,
    PlanMilestoneRecord,
    PlanningSQLiteStore,
    PlanProgressRecord,
    PlanRecord,
    SupervisorTaskRecord,
    SupervisorTaskSummaryRecord,
    WorkerRunRecord,
    has_nonterminal_worker_run,
    initialize_planning_database,
    missing_execution_contract_fields,
    open_existing_planning_database,
    unresolved_task_blockers,
)
from codex_supervisor.story_loop import (
    build_story_loop_status,
    record_story_loop_progress,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="codex-supervisor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("plan-init", help="Initialize planning SQLite")
    init_parser.add_argument("--path", type=Path, default=None)
    init_parser.add_argument("--seed-bootstrap-plan", action="store_true", default=False)

    list_parser = subparsers.add_parser("plan-list", help="List plans")
    list_parser.add_argument("--path", type=Path, default=None)
    list_parser.add_argument("--status", choices=sorted(PLAN_STATUSES), default=None)
    list_parser.add_argument("--json", action="store_true", default=False)

    summary_parser = subparsers.add_parser(
        "plan-summary",
        help="Summarize plans, milestones, decisions, progress, and tasks",
    )
    summary_parser.add_argument("--path", type=Path, default=None)
    summary_parser.add_argument("--plan-id", default=None)
    summary_parser.add_argument("--active-only", action="store_true", default=False)
    summary_parser.add_argument(
        "--current-queue",
        action="store_true",
        default=False,
        help="Summarize active and blocked current-queue plans.",
    )
    summary_parser.add_argument("--json", action="store_true", default=False)

    task_list_parser = subparsers.add_parser("task-list", help="List supervisor tasks")
    task_list_parser.add_argument("--path", type=Path, default=None)
    task_list_parser.add_argument("--status", choices=sorted(TASK_STATUSES), default=None)
    task_list_parser.add_argument("--active-plans-only", action="store_true", default=False)
    task_list_parser.add_argument(
        "--current-queue-plans-only",
        action="store_true",
        default=False,
        help="List tasks attached to active and blocked current-queue plans.",
    )
    task_list_parser.add_argument("--json", action="store_true", default=False)

    task_show_parser = subparsers.add_parser("task-show", help="Show one supervisor task")
    task_show_parser.add_argument("task_id")
    task_show_parser.add_argument("--path", type=Path, default=None)
    task_show_parser.add_argument("--json", action="store_true", default=False)

    worker_list_parser = subparsers.add_parser("worker-run-list", help="List worker runs")
    worker_list_parser.add_argument("--path", type=Path, default=None)
    worker_list_parser.add_argument("--task-id", default=None)
    worker_list_parser.add_argument("--json", action="store_true", default=False)

    worker_show_parser = subparsers.add_parser("worker-run-show", help="Show one worker run")
    worker_show_parser.add_argument("worker_run_id")
    worker_show_parser.add_argument("--path", type=Path, default=None)
    worker_show_parser.add_argument("--json", action="store_true", default=False)

    current_task_parser = subparsers.add_parser(
        "task-current",
        help="Show the highest-priority unblocked ready AFK task attached to an active plan",
    )
    current_task_parser.add_argument("--path", type=Path, default=None)
    current_task_parser.add_argument("--json", action="store_true", default=False)

    task_claim_parser = subparsers.add_parser(
        "task-claim",
        help="Atomically claim the current ready AFK task and create a worker run",
    )
    task_claim_parser.add_argument("--path", type=Path, default=None)
    task_claim_parser.add_argument("--worker-run-id", required=True)
    task_claim_parser.add_argument("--backend", default="codex_exec")
    task_claim_parser.add_argument(
        "--status",
        choices=sorted(CLAIM_WORKER_RUN_STATUSES),
        default="running",
    )
    task_claim_parser.add_argument("--worktree-path", default=None)
    task_claim_parser.add_argument("--prompt-path", default=None)
    task_claim_parser.add_argument("--jsonl-path", default=None)
    task_claim_parser.add_argument("--metadata-json", type=_json_object_arg, default={})
    task_claim_parser.add_argument("--json", action="store_true", default=False)

    goal_contract_parser = subparsers.add_parser(
        "goal-contract-render",
        help="Render a worker-ready Goal Contract for a supervisor task",
    )
    goal_contract_parser.add_argument("--path", type=Path, default=None)
    goal_contract_parser.add_argument(
        "--task-id",
        default=None,
        help="Task to render. Defaults to the current ready AFK task.",
    )
    goal_contract_parser.add_argument("--json", action="store_true", default=False)

    story_status_parser = subparsers.add_parser(
        "story-loop-status",
        help="Report Story Loop status from canonical planning state",
    )
    story_status_parser.add_argument("--path", type=Path, default=None)
    story_status_parser.add_argument("--plan-id", default=None)
    story_status_parser.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Include completed, abandoned, and superseded historical plans.",
    )
    story_status_parser.add_argument("--json", action="store_true", default=False)

    story_record_parser = subparsers.add_parser(
        "story-loop-record",
        help="Record Story Loop progress and artifact links",
    )
    story_record_parser.add_argument("--path", type=Path, default=None)
    story_record_parser.add_argument("--progress-id", required=True)
    story_record_parser.add_argument("--plan-id", required=True)
    story_record_parser.add_argument("--event-type", default="story-loop-iteration")
    story_record_parser.add_argument("--summary", required=True)
    story_record_parser.add_argument("--details", default=None)
    story_record_parser.add_argument("--task-id", default=None)
    story_record_parser.add_argument("--worker-run-id", default=None)
    story_record_parser.add_argument("--artifact-id", action="append", default=[])
    story_record_parser.add_argument(
        "--artifact-relationship",
        default="story-loop-evidence",
    )
    story_record_parser.add_argument("--linked-artifact-id", default=None)
    story_record_parser.add_argument("--json", action="store_true", default=False)

    decision_add_parser = subparsers.add_parser("decision-add", help="Record a plan decision")
    decision_add_parser.add_argument("--path", type=Path, default=None)
    decision_add_parser.add_argument("--decision-id", required=True)
    decision_add_parser.add_argument("--plan-id", required=True)
    decision_add_parser.add_argument("--decision", required=True)
    decision_add_parser.add_argument("--rationale", required=True)
    decision_add_parser.add_argument("--alternatives-considered", default=None)
    decision_add_parser.add_argument("--consequences", default=None)
    decision_add_parser.add_argument("--json", action="store_true", default=False)

    progress_add_parser = subparsers.add_parser("progress-add", help="Record plan progress")
    progress_add_parser.add_argument("--path", type=Path, default=None)
    progress_add_parser.add_argument("--progress-id", required=True)
    progress_add_parser.add_argument("--plan-id", required=True)
    progress_add_parser.add_argument("--event-type", required=True)
    progress_add_parser.add_argument("--summary", required=True)
    progress_add_parser.add_argument("--details", default=None)
    progress_add_parser.add_argument("--linked-artifact-id", default=None)
    progress_add_parser.add_argument("--json", action="store_true", default=False)

    artifact_add_parser = subparsers.add_parser("artifact-link-add", help="Link a plan artifact")
    artifact_add_parser.add_argument("--path", type=Path, default=None)
    artifact_add_parser.add_argument("--plan-id", required=True)
    artifact_add_parser.add_argument("--artifact-id", required=True)
    artifact_add_parser.add_argument("--relationship", required=True)
    artifact_add_parser.add_argument("--json", action="store_true", default=False)

    commit_add_parser = subparsers.add_parser("commit-link-add", help="Link a plan commit")
    commit_add_parser.add_argument("--path", type=Path, default=None)
    commit_add_parser.add_argument("--plan-id", required=True)
    commit_add_parser.add_argument("--commit-sha", required=True)
    commit_add_parser.add_argument("--relationship", required=True)
    commit_add_parser.add_argument("--json", action="store_true", default=False)

    commit_delete_parser = subparsers.add_parser("commit-link-delete", help="Unlink a plan commit")
    commit_delete_parser.add_argument("--path", type=Path, default=None)
    commit_delete_parser.add_argument("--plan-id", required=True)
    commit_delete_parser.add_argument("--commit-sha", required=True)
    commit_delete_parser.add_argument("--relationship", required=True)
    commit_delete_parser.add_argument("--json", action="store_true", default=False)

    task_upsert_parser = subparsers.add_parser(
        "task-upsert",
        help="Create a task or safely update one while preserving omitted optional fields",
    )
    task_upsert_parser.add_argument("--path", type=Path, default=None)
    task_upsert_parser.add_argument("--task-id", required=True)
    task_upsert_parser.add_argument("--plan-id", required=True)
    task_upsert_parser.add_argument("--title", required=True)
    task_upsert_parser.add_argument("--goal", required=True)
    task_upsert_parser.add_argument("--task-type", choices=sorted(TASK_TYPES), required=True)
    task_upsert_parser.add_argument("--status", choices=sorted(TASK_STATUSES), required=True)
    task_upsert_parser.add_argument("--scope-json", type=_json_object_arg, default=None)
    task_upsert_parser.add_argument("--out-of-scope-json", type=_json_object_arg, default=None)
    task_upsert_parser.add_argument("--acceptance-criterion", action="append", default=None)
    task_upsert_parser.add_argument("--verification-command", action="append", default=None)
    task_upsert_parser.add_argument("--allowed-path", action="append", default=None)
    task_upsert_parser.add_argument("--blocked-by", action="append", default=None)
    task_upsert_parser.add_argument("--worker-backend", default=None)
    task_upsert_parser.add_argument(
        "--review-required",
        dest="review_required",
        action="store_true",
    )
    task_upsert_parser.add_argument(
        "--no-review-required",
        dest="review_required",
        action="store_false",
    )
    task_upsert_parser.set_defaults(review_required=None)
    task_upsert_parser.add_argument(
        "--replace",
        action="store_true",
        default=False,
        help="Reset omitted optional fields instead of preserving them.",
    )
    task_upsert_parser.add_argument("--json", action="store_true", default=False)

    worker_upsert_parser = subparsers.add_parser(
        "worker-run-upsert",
        help="Create a run or safely update one while preserving omitted evidence fields",
    )
    worker_upsert_parser.add_argument("--path", type=Path, default=None)
    worker_upsert_parser.add_argument("--worker-run-id", required=True)
    worker_upsert_parser.add_argument("--task-id", required=True)
    worker_upsert_parser.add_argument("--backend", required=True)
    worker_upsert_parser.add_argument(
        "--status", choices=sorted(WORKER_RUN_STATUSES), required=True
    )
    worker_upsert_parser.add_argument("--worktree-path", default=None)
    worker_upsert_parser.add_argument("--prompt-path", default=None)
    worker_upsert_parser.add_argument("--jsonl-path", default=None)
    worker_upsert_parser.add_argument("--result-path", default=None)
    worker_upsert_parser.add_argument("--started-at", default=None)
    worker_upsert_parser.add_argument("--completed-at", default=None)
    worker_upsert_parser.add_argument("--failure-class", default=None)
    worker_upsert_parser.add_argument("--metadata-json", type=_json_object_arg, default=None)
    worker_upsert_parser.add_argument(
        "--replace",
        action="store_true",
        default=False,
        help="Replace omitted optional fields with null/default values instead of preserving them.",
    )
    worker_upsert_parser.add_argument("--json", action="store_true", default=False)

    plan_upsert_parser = subparsers.add_parser("plan-upsert", help="Create or update a plan")
    plan_upsert_parser.add_argument("--path", type=Path, default=None)
    plan_upsert_parser.add_argument("--plan-id", required=True)
    plan_upsert_parser.add_argument("--slug", required=True)
    plan_upsert_parser.add_argument("--title", required=True)
    plan_upsert_parser.add_argument("--goal", required=True)
    plan_upsert_parser.add_argument("--status", choices=sorted(PLAN_STATUSES), required=True)
    plan_upsert_parser.add_argument("--priority", type=int, default=0)
    plan_upsert_parser.add_argument("--owner-agent", default=None)
    plan_upsert_parser.add_argument("--non-goals-json", type=_json_object_arg, default={})
    plan_upsert_parser.add_argument("--context-json", type=_json_object_arg, default={})
    plan_upsert_parser.add_argument("--superseded-by-plan-id", default=None)
    plan_upsert_parser.add_argument("--json", action="store_true", default=False)

    milestone_upsert_parser = subparsers.add_parser(
        "milestone-upsert", help="Create or update a milestone"
    )
    milestone_upsert_parser.add_argument("--path", type=Path, default=None)
    milestone_upsert_parser.add_argument("--milestone-id", required=True)
    milestone_upsert_parser.add_argument("--plan-id", required=True)
    milestone_upsert_parser.add_argument("--title", required=True)
    milestone_upsert_parser.add_argument(
        "--status", choices=sorted(MILESTONE_STATUSES), required=True
    )
    milestone_upsert_parser.add_argument("--sort-order", type=int, default=0)
    milestone_upsert_parser.add_argument("--details-json", type=_json_object_arg, default={})
    milestone_upsert_parser.add_argument("--json", action="store_true", default=False)

    criterion_upsert_parser = subparsers.add_parser(
        "criterion-upsert", help="Create or update an acceptance criterion"
    )
    criterion_upsert_parser.add_argument("--path", type=Path, default=None)
    criterion_upsert_parser.add_argument("--criterion-id", required=True)
    criterion_upsert_parser.add_argument("--plan-id", required=True)
    criterion_upsert_parser.add_argument("--description", required=True)
    criterion_upsert_parser.add_argument(
        "--status", choices=sorted(CRITERION_STATUSES), required=True
    )
    criterion_upsert_parser.add_argument("--verification-command", default=None)
    criterion_upsert_parser.add_argument("--json", action="store_true", default=False)

    plan_status_parser = subparsers.add_parser("plan-status", help="Update a plan status")
    plan_status_parser.add_argument("--path", type=Path, default=None)
    plan_status_parser.add_argument("--plan-id", required=True)
    plan_status_parser.add_argument("--status", choices=sorted(PLAN_STATUSES), required=True)
    plan_status_parser.add_argument("--superseded-by-plan-id", default=None)

    milestone_status_parser = subparsers.add_parser(
        "milestone-status", help="Update a milestone status"
    )
    milestone_status_parser.add_argument("--path", type=Path, default=None)
    milestone_status_parser.add_argument("--milestone-id", required=True)
    milestone_status_parser.add_argument(
        "--status", choices=sorted(MILESTONE_STATUSES), required=True
    )

    criterion_status_parser = subparsers.add_parser(
        "criterion-status", help="Update an acceptance criterion status"
    )
    criterion_status_parser.add_argument("--path", type=Path, default=None)
    criterion_status_parser.add_argument("--criterion-id", required=True)
    criterion_status_parser.add_argument(
        "--status", choices=sorted(CRITERION_STATUSES), required=True
    )

    task_status_parser = subparsers.add_parser("task-status", help="Update a task status")
    task_status_parser.add_argument("--path", type=Path, default=None)
    task_status_parser.add_argument("--task-id", required=True)
    task_status_parser.add_argument("--status", choices=sorted(TASK_STATUSES), required=True)

    worker_status_parser = subparsers.add_parser("worker-run-status", help="Update run status")
    worker_status_parser.add_argument("--path", type=Path, default=None)
    worker_status_parser.add_argument("--worker-run-id", required=True)
    worker_status_parser.add_argument(
        "--status", choices=sorted(WORKER_RUN_STATUSES), required=True
    )
    worker_status_parser.add_argument("--failure-class", default=None)
    worker_status_parser.add_argument("--completed-at", default=None)
    worker_status_parser.add_argument("--result-path", default=None)

    args = parser.parse_args(argv)

    if args.command == "plan-init":
        path = _planning_path_or_report(args.path)
        if path is None:
            return 1
        store = initialize_planning_database(path)
        if args.seed_bootstrap_plan:
            seed_bootstrap_plan(store)
        print(f"Initialized planning database: {path}")
        return 0

    if args.command == "plan-list":
        read_store = _open_read_store(args.path)
        if read_store is None:
            return 1
        plan_store = read_store
        plans = _read_or_report(lambda: plan_store.list_plans(status=args.status))
        if plans is None:
            return 1
        if not plans:
            if args.json:
                _print_json(())
                return 0
            print("No plans found.")
            return 0
        if args.json:
            _print_json(plans)
            return 0
        for plan in plans:
            print(f"{plan.plan_id}\t{plan.status}\tpriority={plan.priority}\t{plan.title}")
        return 0

    if args.command == "plan-summary":
        read_store = _open_read_store(args.path)
        if read_store is None:
            return 1
        all_plans = _read_or_report(read_store.list_plans)
        if all_plans is None:
            return 1
        if args.plan_id is not None:
            plans = tuple(plan for plan in all_plans if plan.plan_id == args.plan_id)
            if not plans:
                if args.json:
                    _print_json(())
                else:
                    print(f"No plan found: {args.plan_id}")
                return 1
        elif args.active_only and args.current_queue:
            print("--active-only and --current-queue are mutually exclusive", file=sys.stderr)
            return 1
        elif args.current_queue:
            plans = tuple(plan for plan in all_plans if plan.status in CURRENT_QUEUE_PLAN_STATUSES)
        elif args.active_only:
            plans = tuple(plan for plan in all_plans if plan.status == "active")
        else:
            plans = all_plans
        summary_store = read_store
        summaries = _read_or_report(
            lambda: tuple(_build_plan_summary_entry(summary_store, plan) for plan in plans)
        )
        if summaries is None:
            return 1
        if args.json:
            _print_json(summaries)
            return 0
        for summary in summaries:
            _print_plan_summary(summary)
        return 0

    if args.command == "task-list":
        read_store = _open_read_store(args.path)
        if read_store is None:
            return 1
        if args.active_plans_only and args.current_queue_plans_only:
            print(
                "--active-plans-only and --current-queue-plans-only are mutually exclusive",
                file=sys.stderr,
            )
            return 1
        task_store = read_store
        tasks = _read_or_report(
            lambda: task_store.list_supervisor_tasks(
                status=args.status,
                active_plans_only=args.active_plans_only,
                current_queue_plans_only=args.current_queue_plans_only,
            )
        )
        if tasks is None:
            return 1
        if not tasks:
            if args.json:
                _print_json(())
                return 0
            print("No supervisor tasks found.")
            return 0
        if args.json:
            _print_json(tasks)
            return 0
        for task in tasks:
            print(
                f"{task.task_id}\t{task.status}\t{task.task_type}\t"
                f"plan={task.plan_id}({task.plan_status})\t{task.title}"
            )
        return 0

    if args.command == "task-show":
        read_store = _open_read_store(args.path)
        if read_store is None:
            return 1
        task_store = read_store
        tasks = _read_or_report(
            lambda: tuple(
                task for task in task_store.list_supervisor_tasks() if task.task_id == args.task_id
            )
        )
        if tasks is None:
            return 1
        if not tasks:
            if args.json:
                _print_json(None)
                return 1
            print(f"No supervisor task found: {args.task_id}")
            return 1
        if args.json:
            _print_json(tasks[0])
        else:
            _print_task_detail(tasks[0])
        return 0

    if args.command == "worker-run-list":
        read_store = _open_read_store(args.path)
        if read_store is None:
            return 1
        worker_store = read_store
        runs = _read_or_report(lambda: worker_store.list_worker_runs(task_id=args.task_id))
        if runs is None:
            return 1
        if not runs:
            if args.json:
                _print_json(())
                return 0
            print("No worker runs found.")
            return 0
        if args.json:
            _print_json(runs)
            return 0
        for run in runs:
            print(f"{run.worker_run_id}\t{run.status}\t{run.backend}\ttask={run.task_id}")
        return 0

    if args.command == "worker-run-show":
        read_store = _open_read_store(args.path)
        if read_store is None:
            return 1
        worker_store = read_store
        runs = _read_or_report(
            lambda: tuple(
                run
                for run in worker_store.list_worker_runs()
                if run.worker_run_id == args.worker_run_id
            )
        )
        if runs is None:
            return 1
        if not runs:
            if args.json:
                _print_json(None)
                return 1
            print(f"No worker run found: {args.worker_run_id}")
            return 1
        if args.json:
            _print_json(runs[0])
        else:
            run = runs[0]
            print(f"worker_run_id: {run.worker_run_id}")
            print(f"task_id: {run.task_id}")
            print(f"backend: {run.backend}")
            print(f"status: {run.status}")
            if run.result_path:
                print(f"result_path: {run.result_path}")
        return 0

    if args.command == "task-current":
        read_store = _open_read_store(args.path)
        if read_store is None:
            return 1
        task_store = read_store
        current_task = _read_or_report(task_store.next_ready_afk_task)
        if current_task is None and _last_read_failed:
            return 1
        if current_task is not None:
            if args.json:
                _print_json(current_task)
            else:
                _print_task_detail(current_task)
            return 0
        if args.json:
            _print_json(None)
            return 0
        queue_snapshot = _read_or_report(
            lambda: (
                task_store.list_supervisor_tasks(),
                task_store.list_worker_runs(),
            )
        )
        if queue_snapshot is None:
            return 1
        ready_all_tasks, worker_runs = queue_snapshot
        all_ready_tasks = tuple(task for task in ready_all_tasks if task.status == "ready")
        if all_ready_tasks:
            print("No unblocked ready AFK tasks are attached to active plans.")
            print(
                "Run `uv run codex-supervisor story-loop-status` to distinguish HITL, blocked, "
                "completed, and empty queue states."
            )
            print("Other ready tasks:")
            for task in all_ready_tasks:
                blocked = _task_claimability_reason(task, ready_all_tasks, worker_runs)
                print(
                    f"{task.task_id}\t{task.task_type}\t{blocked}\t"
                    f"plan={task.plan_id}({task.plan_status})\t{task.title}"
                )
            return 0
        print("No ready supervisor tasks found.")
        print(
            "Run `uv run codex-supervisor story-loop-status` to confirm whether the queue is "
            "blocked, completed, or empty."
        )
        return 0

    if args.command == "task-claim":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        try:
            claim = write_store.claim_next_ready_afk_task(
                worker_run_id=args.worker_run_id,
                backend=args.backend,
                status=args.status,
                worktree_path=args.worktree_path,
                prompt_path=args.prompt_path,
                jsonl_path=args.jsonl_path,
                metadata=args.metadata_json,
            )
        except (KeyError, ValueError, sqlite3.Error) as exc:
            print(f"Could not claim current task: {exc}", file=sys.stderr)
            return 1
        if claim is None:
            if args.json:
                _print_json(None)
            else:
                print("No claimable ready AFK task found.")
                print("Run: uv run codex-supervisor story-loop-status --json")
            return 0
        if args.json:
            _print_json(claim)
        else:
            print(f"Claimed task: {claim.task.task_id}")
            print(f"worker_run_id: {claim.worker_run.worker_run_id}")
            print(f"worker_status: {claim.worker_run.status}")
        return 0

    if args.command == "goal-contract-render":
        read_store = _open_read_store(args.path)
        if read_store is None:
            return 1
        contract_task = _select_goal_contract_task(read_store, task_id=args.task_id)
        if contract_task is None and _last_read_failed:
            return 1
        if contract_task is None:
            if args.json:
                _print_json(None)
            elif args.task_id is None:
                print("No current ready AFK task found.")
                print("Run: uv run codex-supervisor story-loop-status")
            else:
                print(f"No supervisor task found: {args.task_id}")
            return 1
        all_tasks = _read_or_report(read_store.list_supervisor_tasks)
        if all_tasks is None:
            return 1
        contract = render_goal_contract(
            contract_task,
            unresolved_blockers=unresolved_task_blockers(contract_task, all_tasks),
        )
        if args.json:
            _print_json(contract)
        else:
            print(render_goal_contract_markdown(contract))
        return 0

    if args.command == "story-loop-status":
        read_store = _open_read_store(args.path)
        if read_store is None:
            return 1
        if args.plan_id is not None:
            matching_plans = _read_or_report(
                lambda: tuple(
                    plan for plan in read_store.list_plans() if plan.plan_id == args.plan_id
                )
            )
            if matching_plans is None:
                return 1
            if not matching_plans:
                print(f"No plan found: {args.plan_id}", file=sys.stderr)
                return 1
            selected_plan = matching_plans[0]
            if not args.all and selected_plan.status not in CURRENT_QUEUE_PLAN_STATUSES:
                print(
                    f"Plan {args.plan_id} is {selected_plan.status}; rerun with --all to inspect "
                    "historical plans.",
                    file=sys.stderr,
                )
                return 1
        status = _read_or_report(
            lambda: build_story_loop_status(
                read_store,
                active_only=not args.all,
                plan_id=args.plan_id,
            )
        )
        if status is None:
            return 1
        if args.json:
            _print_json(status)
        else:
            _print_story_loop_status(status)
        return 0

    if args.command == "story-loop-record":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        result = _write_story_loop_record_or_report(
            write_store,
            progress_id=args.progress_id,
            plan_id=args.plan_id,
            event_type=args.event_type,
            summary=args.summary,
            details=args.details,
            artifact_ids=tuple(args.artifact_id),
            artifact_relationship=args.artifact_relationship,
            task_id=args.task_id,
            worker_run_id=args.worker_run_id,
            linked_artifact_id=args.linked_artifact_id,
        )
        if result is None:
            return 1
        _print_mutation_result("story_loop_progress", args.progress_id, result, args.json)
        return 0

    if args.command == "decision-add":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        decision_store = write_store
        decision_record = PlanDecisionRecord(
            decision_id=args.decision_id,
            plan_id=args.plan_id,
            decision=args.decision,
            rationale=args.rationale,
            alternatives_considered=args.alternatives_considered,
            consequences=args.consequences,
        )
        if not _write_or_report(lambda: decision_store.add_plan_decision(decision_record)):
            return 1
        _print_mutation_result("decision", decision_record.decision_id, decision_record, args.json)
        return 0

    if args.command == "progress-add":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        progress_store = write_store
        progress_record = PlanProgressRecord(
            progress_id=args.progress_id,
            plan_id=args.plan_id,
            event_type=args.event_type,
            summary=args.summary,
            details=args.details,
            linked_artifact_id=args.linked_artifact_id,
        )
        if not _write_or_report(lambda: progress_store.add_plan_progress(progress_record)):
            return 1
        _print_mutation_result("progress", progress_record.progress_id, progress_record, args.json)
        return 0

    if args.command == "artifact-link-add":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        artifact_store = write_store
        artifact_record = PlanArtifactLinkRecord(
            plan_id=args.plan_id,
            artifact_id=args.artifact_id,
            relationship=args.relationship,
        )
        if not _write_or_report(lambda: artifact_store.add_plan_artifact_link(artifact_record)):
            return 1
        _print_mutation_result(
            "artifact_link",
            artifact_record.artifact_id,
            artifact_record,
            args.json,
        )
        return 0

    if args.command == "commit-link-add":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        commit_store = write_store
        commit_record = PlanCommitLinkRecord(
            plan_id=args.plan_id,
            commit_sha=args.commit_sha,
            relationship=args.relationship,
        )
        if not _write_or_report(lambda: commit_store.add_plan_commit_link(commit_record)):
            return 1
        _print_mutation_result("commit_link", commit_record.commit_sha, commit_record, args.json)
        return 0

    if args.command == "commit-link-delete":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        commit_store = write_store
        commit_record = PlanCommitLinkRecord(
            plan_id=args.plan_id,
            commit_sha=args.commit_sha,
            relationship=args.relationship,
        )
        deleted = _write_value_or_report(
            lambda: commit_store.delete_plan_commit_link(commit_record)
        )
        if deleted is None:
            return 1
        if args.json:
            _print_json({"deleted": deleted, "commit_link": commit_record})
        else:
            action = "Deleted" if deleted else "No matching"
            print(f"{action} commit_link: {commit_record.commit_sha}")
        return 0

    if args.command == "task-upsert":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        task_store = write_store
        task_record = _write_value_or_report(
            lambda: _build_task_upsert_record(
                task_store,
                task_id=args.task_id,
                plan_id=args.plan_id,
                title=args.title,
                goal=args.goal,
                task_type=args.task_type,
                status=args.status,
                scope=args.scope_json,
                out_of_scope=args.out_of_scope_json,
                acceptance_criteria=args.acceptance_criterion,
                verification_commands=args.verification_command,
                allowed_paths=args.allowed_path,
                blocked_by=args.blocked_by,
                worker_backend=args.worker_backend,
                review_required=args.review_required,
                replace=args.replace,
            )
        )
        if task_record is None:
            return 1
        if not _write_or_report(
            lambda: task_store.upsert_supervisor_task(
                task_record,
                validate_current_queue_contract=True,
            )
        ):
            return 1
        _print_mutation_result("task", task_record.task_id, task_record, args.json)
        return 0

    if args.command == "worker-run-upsert":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        worker_store = write_store
        worker_record = _write_value_or_report(
            lambda: _build_worker_run_upsert_record(
                worker_store,
                worker_run_id=args.worker_run_id,
                task_id=args.task_id,
                backend=args.backend,
                status=args.status,
                worktree_path=args.worktree_path,
                prompt_path=args.prompt_path,
                jsonl_path=args.jsonl_path,
                result_path=args.result_path,
                started_at=args.started_at,
                completed_at=args.completed_at,
                failure_class=args.failure_class,
                metadata=args.metadata_json,
                replace=args.replace,
            )
        )
        if worker_record is None:
            return 1
        if not _write_or_report(lambda: worker_store.upsert_worker_run(worker_record)):
            return 1
        _print_mutation_result("worker_run", worker_record.worker_run_id, worker_record, args.json)
        return 0

    if args.command == "plan-upsert":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        plan_store = write_store
        plan_record = PlanRecord(
            plan_id=args.plan_id,
            slug=args.slug,
            title=args.title,
            goal=args.goal,
            status=args.status,
            priority=args.priority,
            owner_agent=args.owner_agent,
            non_goals=args.non_goals_json,
            context=args.context_json,
            superseded_by_plan_id=args.superseded_by_plan_id,
        )
        if not _write_or_report(lambda: plan_store.upsert_plan(plan_record)):
            return 1
        _print_mutation_result("plan", plan_record.plan_id, plan_record, args.json)
        return 0

    if args.command == "milestone-upsert":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        milestone_store = write_store
        milestone_record = PlanMilestoneRecord(
            milestone_id=args.milestone_id,
            plan_id=args.plan_id,
            title=args.title,
            status=args.status,
            sort_order=args.sort_order,
            details=args.details_json,
        )
        if not _write_or_report(lambda: milestone_store.upsert_plan_milestone(milestone_record)):
            return 1
        _print_mutation_result(
            "milestone",
            milestone_record.milestone_id,
            milestone_record,
            args.json,
        )
        return 0

    if args.command == "criterion-upsert":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        criterion_store = write_store
        criterion_record = PlanAcceptanceCriterionRecord(
            criterion_id=args.criterion_id,
            plan_id=args.plan_id,
            description=args.description,
            status=args.status,
            verification_command=args.verification_command,
        )
        if not _write_or_report(
            lambda: criterion_store.upsert_plan_acceptance_criterion(criterion_record)
        ):
            return 1
        _print_mutation_result(
            "criterion",
            criterion_record.criterion_id,
            criterion_record,
            args.json,
        )
        return 0

    if args.command == "plan-status":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        plan_store = write_store
        if not _write_or_report(
            lambda: plan_store.update_plan_status(
                args.plan_id,
                args.status,
                superseded_by_plan_id=args.superseded_by_plan_id,
            )
        ):
            return 1
        print(f"Updated plan {args.plan_id} -> {args.status}")
        return 0

    if args.command == "milestone-status":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        milestone_store = write_store
        if not _write_or_report(
            lambda: milestone_store.update_plan_milestone_status(args.milestone_id, args.status)
        ):
            return 1
        print(f"Updated milestone {args.milestone_id} -> {args.status}")
        return 0

    if args.command == "criterion-status":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        criterion_store = write_store
        if not _write_or_report(
            lambda: criterion_store.update_plan_acceptance_criterion_status(
                args.criterion_id,
                args.status,
            )
        ):
            return 1
        print(f"Updated criterion {args.criterion_id} -> {args.status}")
        return 0

    if args.command == "task-status":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        task_store = write_store
        if not _write_or_report(
            lambda: task_store.update_supervisor_task_status(args.task_id, args.status)
        ):
            return 1
        print(f"Updated task {args.task_id} -> {args.status}")
        return 0

    if args.command == "worker-run-status":
        write_store = _open_write_store(args.path)
        if write_store is None:
            return 1
        worker_store = write_store
        if not _write_or_report(
            lambda: worker_store.update_worker_run_status(
                args.worker_run_id,
                args.status,
                failure_class=args.failure_class,
                completed_at=args.completed_at,
                result_path=args.result_path,
            )
        ):
            return 1
        print(f"Updated worker_run {args.worker_run_id} -> {args.status}")
        return 0

    return 1


_last_read_failed = False


def _planning_path_or_report(path: Path | None) -> Path | None:
    if path is not None:
        return path
    try:
        return default_planning_database_path()
    except RuntimeError as exc:
        print(f"Could not locate planning database: {exc}", file=sys.stderr)
        print(
            "Run from a codex-supervisor/supervised project root or pass "
            "--path <repo>/plans/planning.sqlite3.",
            file=sys.stderr,
        )
        return None


def _open_read_store(path: Path | None) -> PlanningSQLiteStore | None:
    resolved_path = _planning_path_or_report(path)
    if resolved_path is None:
        return None
    path = resolved_path
    if not path.exists():
        print(
            f"Planning database is not initialized: {path}",
            file=sys.stderr,
        )
        print(
            "Run: uv run codex-supervisor plan-init --seed-bootstrap-plan",
            file=sys.stderr,
        )
        return None
    try:
        return open_existing_planning_database(path, validate=True)
    except (ValueError, sqlite3.Error) as exc:
        print(f"Planning database schema is not valid: {exc}", file=sys.stderr)
        print(
            "Run: uv run python -B scripts/check_planning_integrity.py",
            file=sys.stderr,
        )
        return None


def _open_write_store(path: Path | None) -> PlanningSQLiteStore | None:
    resolved_path = _planning_path_or_report(path)
    if resolved_path is None:
        return None
    path = resolved_path
    if not path.exists():
        print(
            f"Planning database is not initialized: {path}",
            file=sys.stderr,
        )
        print(
            "Run: uv run codex-supervisor plan-init --seed-bootstrap-plan",
            file=sys.stderr,
        )
        return None
    try:
        return open_existing_planning_database(path, read_only=False, validate=True)
    except (ValueError, sqlite3.Error) as exc:
        print(f"Planning database schema is not valid: {exc}", file=sys.stderr)
        print(
            "Run: uv run python -B scripts/check_planning_integrity.py",
            file=sys.stderr,
        )
        return None


def _read_or_report[T](operation: Callable[[], T]) -> T | None:
    global _last_read_failed
    _last_read_failed = False
    try:
        return operation()
    except (KeyError, ValueError, sqlite3.Error) as exc:
        _last_read_failed = True
        print(f"Could not read planning database: {exc}", file=sys.stderr)
        print(
            "Run: uv run python -B scripts/check_planning_integrity.py",
            file=sys.stderr,
        )
        return None


def _write_or_report(operation: Callable[[], None]) -> bool:
    try:
        operation()
    except (KeyError, ValueError, sqlite3.Error) as exc:
        print(f"Could not update planning database: {exc}", file=sys.stderr)
        return False
    return True


def _write_value_or_report[T](operation: Callable[[], T]) -> T | None:
    try:
        return operation()
    except (KeyError, ValueError, sqlite3.Error) as exc:
        print(f"Could not update planning database: {exc}", file=sys.stderr)
        return None


def _write_story_loop_record_or_report(
    store: PlanningSQLiteStore,
    *,
    progress_id: str,
    plan_id: str,
    event_type: str,
    summary: str,
    details: str | None,
    artifact_ids: tuple[str, ...],
    artifact_relationship: str,
    task_id: str | None,
    worker_run_id: str | None,
    linked_artifact_id: str | None,
) -> object | None:
    try:
        return record_story_loop_progress(
            store,
            progress_id=progress_id,
            plan_id=plan_id,
            event_type=event_type,
            summary=summary,
            details=details,
            artifact_ids=artifact_ids,
            artifact_relationship=artifact_relationship,
            task_id=task_id,
            worker_run_id=worker_run_id,
            linked_artifact_id=linked_artifact_id,
        )
    except (KeyError, ValueError, sqlite3.Error) as exc:
        print(f"Could not update planning database: {exc}", file=sys.stderr)
        return None


def _select_goal_contract_task(
    store: PlanningSQLiteStore,
    *,
    task_id: str | None,
) -> SupervisorTaskSummaryRecord | None:
    if task_id is None:
        return _read_or_report(store.next_ready_afk_task)
    tasks = _read_or_report(
        lambda: tuple(task for task in store.list_supervisor_tasks() if task.task_id == task_id)
    )
    if tasks is None:
        return None
    if not tasks:
        return None
    return tasks[0]


def _build_task_upsert_record(
    store: PlanningSQLiteStore,
    *,
    task_id: str,
    plan_id: str,
    title: str,
    goal: str,
    task_type: str,
    status: str,
    scope: dict[str, Any] | None,
    out_of_scope: dict[str, Any] | None,
    acceptance_criteria: list[str] | None,
    verification_commands: list[str] | None,
    allowed_paths: list[str] | None,
    blocked_by: list[str] | None,
    worker_backend: str | None,
    review_required: bool | None,
    replace: bool,
) -> SupervisorTaskRecord:
    existing = None if replace else _find_task(store, task_id)
    return SupervisorTaskRecord(
        task_id=task_id,
        plan_id=plan_id,
        title=title,
        goal=goal,
        task_type=task_type,
        status=status,
        scope=_preserve_or_default(scope, existing.scope if existing else {}, {}),
        out_of_scope=_preserve_or_default(
            out_of_scope,
            existing.out_of_scope if existing else {},
            {},
        ),
        acceptance_criteria=_preserve_or_default(
            acceptance_criteria,
            existing.acceptance_criteria if existing else [],
            [],
        ),
        verification_commands=_preserve_or_default(
            verification_commands,
            existing.verification_commands if existing else [],
            [],
        ),
        allowed_paths=_preserve_or_default(
            allowed_paths,
            existing.allowed_paths if existing else [],
            [],
        ),
        blocked_by=_preserve_or_default(blocked_by, existing.blocked_by if existing else [], []),
        worker_backend=_preserve_or_default(
            worker_backend,
            existing.worker_backend if existing else "codex_exec",
            "codex_exec",
        ),
        review_required=_preserve_or_default(
            review_required,
            existing.review_required if existing else True,
            True,
        ),
    )


def _build_worker_run_upsert_record(
    store: PlanningSQLiteStore,
    *,
    worker_run_id: str,
    task_id: str,
    backend: str,
    status: str,
    worktree_path: str | None,
    prompt_path: str | None,
    jsonl_path: str | None,
    result_path: str | None,
    started_at: str | None,
    completed_at: str | None,
    failure_class: str | None,
    metadata: dict[str, Any] | None,
    replace: bool,
) -> WorkerRunRecord:
    existing = None if replace else _find_worker_run(store, worker_run_id)
    return WorkerRunRecord(
        worker_run_id=worker_run_id,
        task_id=task_id,
        backend=backend,
        status=status,
        worktree_path=_preserve_or_default(
            worktree_path,
            existing.worktree_path if existing else None,
            None,
        ),
        prompt_path=_preserve_or_default(
            prompt_path,
            existing.prompt_path if existing else None,
            None,
        ),
        jsonl_path=_preserve_or_default(
            jsonl_path, existing.jsonl_path if existing else None, None
        ),
        result_path=_preserve_or_default(
            result_path,
            existing.result_path if existing else None,
            None,
        ),
        started_at=_preserve_or_default(
            started_at, existing.started_at if existing else None, None
        ),
        completed_at=_preserve_or_default(
            completed_at,
            existing.completed_at if existing else None,
            None,
        ),
        failure_class=_preserve_or_default(
            failure_class,
            existing.failure_class if existing else None,
            None,
        ),
        metadata=_preserve_or_default(metadata, existing.metadata if existing else {}, {}),
    )


def _find_task(
    store: PlanningSQLiteStore,
    task_id: str,
) -> SupervisorTaskSummaryRecord | None:
    tasks = store.list_supervisor_tasks()
    return next((task for task in tasks if task.task_id == task_id), None)


def _find_worker_run(
    store: PlanningSQLiteStore,
    worker_run_id: str,
) -> WorkerRunRecord | None:
    runs = store.list_worker_runs()
    return next((run for run in runs if run.worker_run_id == worker_run_id), None)


def _preserve_or_default[T](new_value: T | None, existing_value: T, default_value: T) -> T:
    if new_value is not None:
        return new_value
    if existing_value is not None:
        return existing_value
    return default_value


def _json_object_arg(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        msg = f"Expected JSON object: {exc.msg}"
        raise argparse.ArgumentTypeError(msg) from exc
    if not isinstance(parsed, dict):
        msg = "Expected JSON object"
        raise argparse.ArgumentTypeError(msg)
    return cast(dict[str, Any], parsed)


def _print_mutation_result(label: str, identifier: str, record: object, as_json: bool) -> None:
    if as_json:
        _print_json(record)
        return
    print(f"Recorded {label}: {identifier}")


def _print_task_detail(task: SupervisorTaskSummaryRecord) -> None:
    print(f"task_id: {task.task_id}")
    print(f"title: {task.title}")
    print(f"status: {task.status}")
    print(f"type: {task.task_type}")
    print(f"plan: {task.plan_id} ({task.plan_status}, priority={task.plan_priority})")
    print(f"plan_title: {task.plan_title}")
    print(f"goal: {task.goal}")
    print(f"worker_backend: {task.worker_backend}")
    print(f"review_required: {task.review_required}")
    _print_json_section("scope", task.scope)
    _print_json_section("out_of_scope", task.out_of_scope)
    _print_json_list("acceptance_criteria", task.acceptance_criteria)
    _print_json_list("blocked_by", task.blocked_by)
    _print_json_list("allowed_paths", task.allowed_paths)
    _print_json_list("verification", task.verification_commands)


def _print_story_loop_status(status: object) -> None:
    status_json = _to_jsonable(status)
    if not isinstance(status_json, dict):
        _print_json(status)
        return
    queue_state = status_json.get("queue_state")
    if queue_state:
        print(f"queue_state: {queue_state}")
    current_task_id = status_json.get("current_task_id")
    if current_task_id:
        print(f"current_task_id: {current_task_id}")
    current_running_task_id = status_json.get("current_running_task_id")
    if current_running_task_id:
        print(f"current_running_task_id: {current_running_task_id}")
    current_hitl_task_id = status_json.get("current_hitl_task_id")
    if current_hitl_task_id:
        print(f"current_hitl_task_id: {current_hitl_task_id}")
    current_afk_task = status_json.get("current_afk_task")
    if isinstance(current_afk_task, dict):
        print(f"current_afk_task: {current_afk_task['task_id']}")
    else:
        print("current_afk_task: none")
    current_task = status_json.get("current_task")
    if isinstance(current_task, dict):
        print(f"current_task: {current_task['task_id']}")
    else:
        print("current_task: none")
    print("plans:")
    plans = status_json.get("plans", [])
    if not plans:
        print("- none")
        return
    if not isinstance(plans, list):
        _print_json(status)
        return
    for plan in plans:
        if not isinstance(plan, dict):
            continue
        print(f"- {plan['plan_id']}\t{plan['state']}\tpriority={plan['priority']}\t{plan['title']}")
        print(f"  summary: {plan['summary']}")
        if plan.get("current_task_id"):
            print(f"  current_task_id: {plan['current_task_id']}")
        if plan.get("running_task_ids"):
            print(f"  running_task_ids: {', '.join(plan['running_task_ids'])}")
        if plan.get("blocked_task_ids"):
            print(f"  blocked_task_ids: {', '.join(plan['blocked_task_ids'])}")
        if plan.get("hitl_task_ids"):
            print(f"  hitl_task_ids: {', '.join(plan['hitl_task_ids'])}")
        if plan.get("pending_criterion_ids"):
            print(f"  pending_criterion_ids: {', '.join(plan['pending_criterion_ids'])}")


def _print_json_list(label: str, values: Sequence[object]) -> None:
    print(f"{label}:")
    if not values:
        print("- none")
        return
    for value in values:
        print(f"- {value}")


def _print_json_section(label: str, value: object) -> None:
    print(f"{label}:")
    print(json.dumps(_to_jsonable(value), indent=2, sort_keys=True))


def _print_json(value: object) -> None:
    print(json.dumps(_to_jsonable(value), indent=2, sort_keys=True, default=str))


def _to_jsonable(value: object) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        dataclass_value = cast(Any, value)
        return {
            field.name: _to_jsonable(getattr(dataclass_value, field.name))
            for field in fields(dataclass_value)
        }
    if isinstance(value, tuple | list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    return value


def _build_plan_summary_entry(
    store: PlanningSQLiteStore,
    plan: PlanRecord,
) -> dict[str, object]:
    tasks = tuple(task for task in store.list_supervisor_tasks() if task.plan_id == plan.plan_id)
    task_ids = {task.task_id for task in tasks}
    return {
        "plan": plan,
        "milestones": store.list_plan_milestones(plan_id=plan.plan_id),
        "acceptance_criteria": store.list_plan_acceptance_criteria(plan_id=plan.plan_id),
        "decisions": store.list_plan_decisions(plan_id=plan.plan_id),
        "progress": store.list_plan_progress(plan_id=plan.plan_id),
        "tasks": tasks,
        "commit_links": store.list_plan_commit_links(plan_id=plan.plan_id),
        "artifact_links": store.list_plan_artifact_links(plan_id=plan.plan_id),
        "worker_runs": tuple(run for run in store.list_worker_runs() if run.task_id in task_ids),
    }


def _print_plan_summary(summary: dict[str, object]) -> None:
    plan = cast(PlanRecord, summary["plan"])
    print(f"{plan.plan_id}\t{plan.status}\tpriority={plan.priority}\t{plan.title}")
    print("milestones:")
    for milestone in cast(tuple[PlanMilestoneRecord, ...], summary["milestones"]):
        print(f"- {milestone.milestone_id}\t{milestone.status}\t{milestone.title}")
    print("acceptance_criteria:")
    for criterion in cast(
        tuple[PlanAcceptanceCriterionRecord, ...],
        summary["acceptance_criteria"],
    ):
        print(f"- {criterion.criterion_id}\t{criterion.status}\t{criterion.description}")
    print("decisions:")
    for decision in cast(tuple[PlanDecisionRecord, ...], summary["decisions"]):
        print(f"- {decision.decision_id}\t{decision.decision}")
    print("progress:")
    for progress in cast(tuple[PlanProgressRecord, ...], summary["progress"]):
        print(f"- {progress.progress_id}\t{progress.event_type}\t{progress.summary}")
    print("tasks:")
    for task in cast(tuple[SupervisorTaskSummaryRecord, ...], summary["tasks"]):
        print(f"- {task.task_id}\t{task.status}\t{task.task_type}\t{task.title}")
    print("")


def seed_bootstrap_plan(store: PlanningSQLiteStore) -> None:
    """Seed the bootstrap plan if it is not already present."""

    existing_plans = {plan.plan_id: plan for plan in store.list_plans()}
    bootstrap_plan = existing_plans.get("plan-bootstrap-supervisor")
    bootstrap_plan = PlanRecord(
        plan_id="plan-bootstrap-supervisor",
        slug="bootstrap-supervisor",
        title="Bootstrap Codex Supervisor",
        goal=(
            "Create the Python-first supervisor repo with source-of-truth docs, "
            "planning SQLite, source locks, insights, skills, source clones, and handoff."
        ),
        status=bootstrap_plan.status if bootstrap_plan else "active",
        priority=100,
        owner_agent="codex",
        non_goals={
            "full_runtime": "Do not implement the complete worker orchestration runtime yet.",
            "source_vendoring": "Do not vendor cloned source repositories.",
        },
        context={
            "patterns": [
                "nlp-stock-prediction planning SQLite",
                "codex-subagent-testing source locks",
                "tech-resume insights wiki",
                "observe-safety source-of-truth validation",
            ],
            "repo_root": "<repo-root>",
        },
        superseded_by_plan_id=bootstrap_plan.superseded_by_plan_id if bootstrap_plan else None,
    )
    store.upsert_plan(bootstrap_plan)
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
    existing_tasks = {task.task_id: task for task in store.list_supervisor_tasks()}
    existing_bootstrap_task = existing_tasks.get("task-bootstrap-orient-and-plan")
    if bootstrap_plan.status == "active":
        store.upsert_supervisor_task(
            SupervisorTaskRecord(
                task_id="task-bootstrap-orient-and-plan",
                plan_id="plan-bootstrap-supervisor",
                title="Orient and continue bootstrap implementation",
                goal=(
                    "Read the source-of-truth docs, inspect planning SQLite, and continue the "
                    "highest-priority bootstrap work with verification and handoff updates."
                ),
                task_type="AFK",
                status=existing_bootstrap_task.status if existing_bootstrap_task else "ready",
                scope={
                    "read_first": [
                        "README.md",
                        "AGENTS.md",
                        "PLANS.md",
                        "ROADMAP.md",
                        "HANDOFF.md",
                    ],
                    "workflow": "Use typed planning helpers and update durable state.",
                },
                out_of_scope={
                    "source_clones": "Do not vendor ignored source clones.",
                    "codex_databases": "Do not write directly to local Codex internal databases.",
                },
                acceptance_criteria=[
                    "Fresh thread can discover this task with story-loop-status.",
                    "Implementation work follows the active source-of-truth docs.",
                    "Default verification passes before handoff.",
                ],
                verification_commands=["uv run python -B scripts/verify.py"],
                allowed_paths=[
                    "src/**",
                    "tests/**",
                    "scripts/**",
                    "plans/planning.sqlite3",
                    "README.md",
                    "AGENTS.md",
                    "PLANS.md",
                    "ROADMAP.md",
                    "HANDOFF.md",
                ],
            ),
            validate_current_queue_contract=True,
        )


def _task_claimability_reason(
    task: SupervisorTaskSummaryRecord,
    all_tasks: tuple[SupervisorTaskSummaryRecord, ...],
    worker_runs: tuple[WorkerRunRecord, ...],
) -> str:
    reasons: list[str] = []
    if task.plan_status != "active":
        reasons.append(f"plan-{task.plan_status}")
    if task.task_type != "AFK":
        reasons.append("hitl")
    blockers = unresolved_task_blockers(task, all_tasks)
    if blockers:
        reasons.append("blocked-by=" + ",".join(blockers))
    if task.task_type == "AFK":
        missing_fields = missing_execution_contract_fields(task)
        if missing_fields:
            reasons.append("missing=" + ",".join(missing_fields))
    if has_nonterminal_worker_run(task.task_id, worker_runs):
        reasons.append("worker-run-active")
    return ";".join(reasons) if reasons else "unblocked"


if __name__ == "__main__":
    raise SystemExit(main())
