"""GitHub PR and CI lifecycle helpers for supervisor-owned automation."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codex_supervisor.planning import PlanningSQLiteStore, SupervisorTaskRecord

JsonObject = dict[str, Any]
CommandRunner = Callable[[tuple[str, ...], Path | None], subprocess.CompletedProcess[str]]

FAILED_STATES = frozenset({"ACTION_REQUIRED", "CANCELLED", "FAILURE", "SKIPPED", "TIMED_OUT"})
SUCCESS_STATES = frozenset({"SUCCESS", "NEUTRAL"})


@dataclass(frozen=True)
class GithubCommandResult:
    """Result from a GitHub lifecycle command."""

    argv: tuple[str, ...]
    executed: bool
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class GithubCheckFailure:
    """One failed or indeterminate GitHub check."""

    name: str
    state: str
    url: str | None = None
    details: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class GithubCiClassification:
    """Classified CI state for a PR head."""

    status: str
    failed_checks: tuple[GithubCheckFailure, ...]
    pending_checks: tuple[str, ...]
    successful_checks: tuple[str, ...]


@dataclass(frozen=True)
class GithubMergePolicyDecision:
    """Deterministic merge decision from checks and policy inputs."""

    allowed: bool
    reason: str
    method: str = "squash"


def create_or_update_pr(
    *,
    repository: str,
    head: str,
    base: str,
    title: str,
    body: str,
    pr_number: int | None = None,
    draft: bool = True,
    execute: bool = False,
    cwd: Path | None = None,
    runner: CommandRunner | None = None,
) -> GithubCommandResult:
    """Create a PR, or update an existing PR when ``pr_number`` is supplied."""

    if pr_number is None:
        argv = (
            "gh",
            "pr",
            "create",
            "--repo",
            repository,
            "--head",
            head,
            "--base",
            base,
            "--title",
            title,
            "--body",
            body,
            *(("--draft",) if draft else ()),
        )
    else:
        argv = (
            "gh",
            "pr",
            "edit",
            str(pr_number),
            "--repo",
            repository,
            "--title",
            title,
            "--body",
            body,
            "--base",
            base,
        )
    return _maybe_run(argv, execute=execute, cwd=cwd, runner=runner)


def monitor_pr_checks(
    *,
    repository: str,
    pr_number: int,
    execute: bool = False,
    cwd: Path | None = None,
    runner: CommandRunner | None = None,
) -> GithubCommandResult:
    """Fetch GitHub PR checks through the GitHub CLI."""

    argv = (
        "gh",
        "pr",
        "checks",
        str(pr_number),
        "--repo",
        repository,
        "--json",
        "name,state,link,bucket,description,startedAt,completedAt",
    )
    return _maybe_run(argv, execute=execute, cwd=cwd, runner=runner)


def classify_github_checks(checks_json: str) -> GithubCiClassification:
    """Classify ``gh pr checks --json`` output into success, pending, or repair."""

    payload = json.loads(checks_json)
    if not isinstance(payload, list):
        msg = "GitHub checks payload must be a JSON array"
        raise ValueError(msg)
    failures: list[GithubCheckFailure] = []
    pending: list[str] = []
    successful: list[str] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("workflowName") or "unnamed-check")
        state = str(item.get("state") or item.get("conclusion") or item.get("status") or "")
        normalized_state = state.upper()
        if normalized_state in FAILED_STATES:
            failures.append(
                GithubCheckFailure(
                    name=name,
                    state=normalized_state,
                    url=str(item["link"]) if item.get("link") else None,
                    details={key: value for key, value in item.items() if key not in {"name"}},
                )
            )
        elif normalized_state in SUCCESS_STATES:
            successful.append(name)
        else:
            pending.append(name)
    status = "failed" if failures else "pending" if pending else "successful"
    return GithubCiClassification(
        status=status,
        failed_checks=tuple(failures),
        pending_checks=tuple(pending),
        successful_checks=tuple(successful),
    )


def repair_tasks_from_failed_checks(
    *,
    plan_id: str,
    source_task_id: str,
    failed_checks: tuple[GithubCheckFailure, ...],
    allowed_paths: tuple[str, ...],
    verification_commands: tuple[str, ...],
    task_id_prefix: str = "task-ci-repair",
) -> tuple[SupervisorTaskRecord, ...]:
    """Create bounded AFK repair-task drafts from failed GitHub checks."""

    return tuple(
        SupervisorTaskRecord(
            task_id=f"{task_id_prefix}-{_safe_id(check.name)}-{index}",
            plan_id=plan_id,
            title=f"Repair failing CI check: {check.name}",
            goal=(
                f"Repair the failing GitHub CI check `{check.name}` for source task "
                f"`{source_task_id}`. Use the check state and URL as evidence, keep edits "
                "inside the allowed paths, and rerun the relevant verification."
            ),
            task_type="AFK",
            status="ready",
            scope={
                "compiled_from": "github_ci_failure",
                "source_task_id": source_task_id,
                "check_name": check.name,
                "check_state": check.state,
                "check_url": check.url,
            },
            out_of_scope={
                "merge_policy": "Do not merge the PR from a repair task.",
            },
            acceptance_criteria=[
                f"GitHub check `{check.name}` is no longer failing.",
                "Repair evidence is recorded back into planning SQLite.",
            ],
            verification_commands=list(verification_commands),
            allowed_paths=list(allowed_paths),
            blocked_by=[source_task_id],
            worker_backend="codex_exec",
            review_required=True,
        )
        for index, check in enumerate(failed_checks, start=1)
    )


def enqueue_repair_tasks(
    store: PlanningSQLiteStore,
    tasks: tuple[SupervisorTaskRecord, ...],
) -> tuple[str, ...]:
    """Persist CI repair tasks and return created or updated IDs."""

    for task in tasks:
        store.upsert_supervisor_task(task, validate_current_queue_contract=True)
    return tuple(task.task_id for task in tasks)


def decide_merge_policy(
    classification: GithubCiClassification,
    *,
    release_approved: bool,
    method: str = "squash",
) -> GithubMergePolicyDecision:
    """Decide whether merge is allowed from CI classification and release approval."""

    if not release_approved:
        return GithubMergePolicyDecision(False, "release_not_approved", method=method)
    if classification.failed_checks:
        return GithubMergePolicyDecision(False, "ci_failed", method=method)
    if classification.pending_checks:
        return GithubMergePolicyDecision(False, "ci_pending", method=method)
    return GithubMergePolicyDecision(True, "ci_successful_and_release_approved", method=method)


def merge_pr(
    *,
    repository: str,
    pr_number: int,
    decision: GithubMergePolicyDecision,
    execute: bool = False,
    cwd: Path | None = None,
    runner: CommandRunner | None = None,
) -> GithubCommandResult:
    """Merge a PR only when the deterministic policy allows it."""

    if not decision.allowed:
        return GithubCommandResult(
            argv=(),
            executed=False,
            exit_code=1,
            stderr=f"merge blocked by policy: {decision.reason}",
        )
    argv = (
        "gh",
        "pr",
        "merge",
        str(pr_number),
        "--repo",
        repository,
        f"--{decision.method}",
        "--delete-branch",
    )
    return _maybe_run(argv, execute=execute, cwd=cwd, runner=runner)


def _maybe_run(
    argv: tuple[str, ...],
    *,
    execute: bool,
    cwd: Path | None,
    runner: CommandRunner | None,
) -> GithubCommandResult:
    if not execute:
        return GithubCommandResult(argv=argv, executed=False)
    active_runner = runner or _default_runner
    completed = active_runner(argv, cwd)
    return GithubCommandResult(
        argv=argv,
        executed=True,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _default_runner(argv: tuple[str, ...], cwd: Path | None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, text=True, capture_output=True, check=False)


def _safe_id(value: str) -> str:
    return (
        "".join(character.lower() if character.isalnum() else "-" for character in value).strip(
            "-"
        )[:48]
        or "check"
    )
