from __future__ import annotations

import json

from codex_supervisor.github_lifecycle import (
    classify_github_checks,
    create_or_update_pr,
    decide_merge_policy,
    repair_tasks_from_failed_checks,
)


def test_create_pr_lifecycle_dry_run_builds_gh_command():
    result = create_or_update_pr(
        repository="owner/repo",
        head="feature",
        base="main",
        title="Ship feature",
        body="Body",
        execute=False,
    )

    assert result.executed is False
    assert result.argv[:5] == ("gh", "pr", "create", "--repo", "owner/repo")
    assert "--draft" in result.argv


def test_github_check_classification_and_repair_tasks():
    classification = classify_github_checks(
        json.dumps(
            [
                {"name": "unit", "state": "SUCCESS"},
                {"name": "lint", "state": "FAILURE", "link": "https://example.test/lint"},
                {"name": "deploy", "state": "PENDING"},
            ]
        )
    )

    assert classification.status == "failed"
    assert [check.name for check in classification.failed_checks] == ["lint"]
    assert classification.pending_checks == ("deploy",)

    tasks = repair_tasks_from_failed_checks(
        plan_id="plan-ci",
        source_task_id="task-source",
        failed_checks=classification.failed_checks,
        allowed_paths=("src/**", "tests/**"),
        verification_commands=("uv run --no-sync python -B scripts/verify.py",),
    )

    assert len(tasks) == 1
    assert tasks[0].task_id == "task-ci-repair-lint-1"
    assert tasks[0].status == "ready"
    assert tasks[0].scope["check_url"] == "https://example.test/lint"


def test_merge_policy_requires_release_approval_and_clean_ci():
    clean = classify_github_checks(json.dumps([{"name": "unit", "state": "SUCCESS"}]))
    blocked = decide_merge_policy(clean, release_approved=False)
    allowed = decide_merge_policy(clean, release_approved=True)

    assert blocked.allowed is False
    assert blocked.reason == "release_not_approved"
    assert allowed.allowed is True
    assert allowed.reason == "ci_successful_and_release_approved"
