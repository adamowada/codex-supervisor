"""Compact command line interface for codex-supervisor."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path

from codex_supervisor.compact_planning import (
    initialize_compact_planning_database,
    seed_compact_bootstrap_plan,
)
from codex_supervisor.paths import default_planning_database_path
from codex_supervisor.small_interface import attempt_transition, queue_next


def main(argv: list[str] | None = None) -> int:
    """Run the compact CLI."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        payload = _dispatch(args)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if payload is not None:
        _print_payload(payload, json_output=bool(getattr(args, "json", False)))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex-supervisor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_init = subparsers.add_parser("plan-init", help="Initialize compact planning SQLite")
    _add_path_arg(plan_init)
    plan_init.add_argument("--seed-bootstrap-plan", action="store_true", default=False)

    queue = subparsers.add_parser("queue-next", help="Inspect the next compact queue task")
    _add_path_arg(queue)
    queue.add_argument("--json", action="store_true", default=False)

    transition = subparsers.add_parser("attempt-transition", help="Run one attempt transition")
    _add_path_arg(transition)
    transition.add_argument("--task-id", required=True)
    transition.add_argument("--attempt-id", default=None)
    transition.add_argument("--executor", default="manual")
    transition.add_argument(
        "--status",
        required=True,
        choices=("planned", "running", "succeeded", "failed", "blocked"),
    )
    transition.add_argument("--summary", required=True)
    transition.add_argument("--check", action="append", default=[])
    transition.add_argument("--artifact", action="append", default=[])
    transition.add_argument("--acceptance-result", action="append", default=[])
    transition.add_argument("--risk", action="append", default=[])
    transition.add_argument("--gap", action="append", default=[])
    transition.add_argument("--next-action", action="append", default=[])
    transition.add_argument("--review-evidence", action="append", default=[])
    transition.add_argument("--json", action="store_true", default=False)
    return parser


def _dispatch(args: argparse.Namespace) -> object | None:
    database_path = _database_path(args)
    if args.command == "plan-init":
        initialize_compact_planning_database(database_path)
        if args.seed_bootstrap_plan:
            seed_compact_bootstrap_plan(database_path, created_at=_now())
        return None
    if args.command == "queue-next":
        return queue_next(database_path)
    if args.command == "attempt-transition":
        return attempt_transition(
            database_path,
            task_id=args.task_id,
            attempt_id=args.attempt_id,
            executor=args.executor,
            status=args.status,
            summary=args.summary,
            checks=tuple(args.check),
            artifacts=tuple(args.artifact),
            acceptance_results=_parse_acceptance_results(tuple(args.acceptance_result)),
            risks=tuple(args.risk),
            gaps=tuple(args.gap),
            next_actions=tuple(args.next_action),
            review_evidence=tuple(args.review_evidence),
        )
    raise AssertionError(f"Unhandled command: {args.command}")


def _add_path_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--path", type=Path, default=None, help="Planning SQLite path")


def _database_path(args: argparse.Namespace) -> Path:
    return args.path if args.path is not None else default_planning_database_path()


def _parse_acceptance_results(raw_items: tuple[str, ...]) -> dict[str, bool] | None:
    if not raw_items:
        return None
    parsed: dict[str, bool] = {}
    for raw_item in raw_items:
        if "=" not in raw_item:
            raise ValueError("--acceptance-result must use NAME=pass or NAME=fail")
        name, raw_value = raw_item.split("=", 1)
        criterion = name.strip()
        value = raw_value.strip().casefold()
        if not criterion:
            raise ValueError("--acceptance-result criterion cannot be blank")
        if value not in {"pass", "passed", "true", "fail", "failed", "false"}:
            raise ValueError("--acceptance-result value must be pass or fail")
        parsed[criterion] = value in {"pass", "passed", "true"}
    return parsed


def _print_payload(payload: object, *, json_output: bool) -> None:
    normalized = _jsonable(payload)
    if json_output:
        print(json.dumps(normalized, indent=2, sort_keys=True))
        return
    if isinstance(normalized, list | tuple):
        for item in normalized:
            print(_compact_line(item))
        return
    print(_compact_line(normalized))


def _jsonable(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    return value


def _compact_line(value: object) -> str:
    if isinstance(value, dict):
        for key in ("task_id", "plan_id", "attempt_id", "bundle_id", "decision_id"):
            item = value.get(key)
            if item is not None:
                status = value.get("status")
                title = value.get("title") or value.get("summary") or ""
                return "\t".join(str(part) for part in (item, status, title) if part is not None)
    return json.dumps(value, sort_keys=True)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
