from __future__ import annotations

import json
from pathlib import Path

from codex_supervisor.cli import main
from codex_supervisor.planning import initialize_planning_database
from codex_supervisor.runtime_preflight import build_runtime_preflight_report


def test_runtime_preflight_passes_for_linked_full_afk_supervisor_modes(tmp_path: Path) -> None:
    initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")

    report = build_runtime_preflight_report(
        repo_root=tmp_path,
        full_afk=True,
        plugin_invocation=True,
        plugin_full_afk=True,
        supervisor_backend="mcp",
        mcp_tools=(
            "codex_supervisor.runtime_preflight",
            "codex_supervisor.story_loop_status",
            "codex_supervisor.task_current",
            "codex_supervisor.task_next_afk",
            "codex_supervisor.task_claim",
            "codex_supervisor.story_loop_run_once",
            "codex_supervisor.story_loop_start",
            "codex_supervisor.story_loop_poll",
        ),
        worker_execution="codex_exec",
        native_goal_mode=True,
        supervisor_task_id="task-ready",
        goal_contract_linked=True,
        story_loop_status_checked=True,
        task_current_requested=True,
        scaffold_tier="supervisor_managed",
        database_mode="persistent_mongodb",
        evidence_mode="strict_jsonl",
    )

    assert report.ok is True
    assert report.status == "passed"
    assert report.ledger.entrypoint == "desktop_plugin"
    assert report.ledger.required_surface == "live_mcp"
    assert report.ledger.decision_source == "live_mcp"
    assert report.ledger.goal_contract == "native_goal_linked_to_supervisor_contract"
    assert report.ledger.queue_discovery == "story_loop_status_then_task_next_afk"


def test_runtime_preflight_normalizes_desktop_callable_mcp_tool_names(tmp_path: Path) -> None:
    initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")

    report = build_runtime_preflight_report(
        repo_root=tmp_path,
        full_afk=True,
        plugin_invocation=True,
        plugin_full_afk=True,
        supervisor_backend="mcp",
        mcp_tools=(
            "mcp__codex_supervisor__.codex_supervisor_runtime_preflight",
            "codex_supervisor_story_loop_status",
            "codex_supervisor_task_current",
            "codex_supervisor_task_next_afk",
            "codex_supervisor_task_claim",
            "codex_supervisor_story_loop_run_once",
            "codex_supervisor_story_loop_start",
            "codex_supervisor_story_loop_poll",
        ),
        worker_execution="codex_exec",
        story_loop_status_checked=True,
        task_current_requested=True,
        evidence_mode="strict_jsonl",
    )

    assert report.ok is True
    assert report.diagnostics["missing_mcp_tools"] == []
    assert report.diagnostics["normalized_mcp_tools"] == [
        "codex_supervisor.runtime_preflight",
        "codex_supervisor.story_loop_poll",
        "codex_supervisor.story_loop_run_once",
        "codex_supervisor.story_loop_start",
        "codex_supervisor.story_loop_status",
        "codex_supervisor.task_claim",
        "codex_supervisor.task_current",
        "codex_supervisor.task_next_afk",
    ]
    assert (
        report.diagnostics["mcp_tool_aliases"]["codex_supervisor_story_loop_status"]
        == "codex_supervisor.story_loop_status"
    )


def test_runtime_preflight_blocks_memory_database_and_current_thread(tmp_path: Path) -> None:
    initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")

    report = build_runtime_preflight_report(
        repo_root=tmp_path,
        full_afk=True,
        plugin_invocation=True,
        supervisor_backend="skill_only",
        mcp_tools=(),
        cli_available=False,
        worker_execution="current_thread",
        database_mode="memory_mongodb",
        task_current_requested=True,
    )

    assert report.ok is False
    assert report.status == "blocked"
    issue_codes = {issue.code for issue in report.issues}
    assert "supervisor_backend_unavailable" in issue_codes
    assert "current_thread_fallback_blocked" in issue_codes
    assert "memory_database_fallback_forbidden" in issue_codes
    assert "story_loop_status_required" in issue_codes


def test_runtime_preflight_blocks_manual_worker_execution_for_full_afk(tmp_path: Path) -> None:
    initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")

    report = build_runtime_preflight_report(
        repo_root=tmp_path,
        full_afk=True,
        plugin_invocation=True,
        plugin_full_afk=True,
        supervisor_backend="mcp",
        mcp_tools=(
            "codex_supervisor.runtime_preflight",
            "codex_supervisor.story_loop_status",
            "codex_supervisor.task_current",
            "codex_supervisor.task_next_afk",
            "codex_supervisor.task_claim",
            "codex_supervisor.story_loop_run_once",
            "codex_supervisor.story_loop_start",
            "codex_supervisor.story_loop_poll",
        ),
        worker_execution="manual",
        story_loop_status_checked=True,
        task_next_afk_requested=True,
        database_mode="persistent_mongodb",
        evidence_mode="strict_jsonl",
    )

    assert report.ok is False
    assert report.status == "blocked"
    assert {issue.code for issue in report.issues} == {"manual_worker_fallback_blocked"}
    assert report.ledger.worker_execution == "manual"


def test_runtime_preflight_cli_is_diagnostic_only_for_plugin_full_afk(
    tmp_path: Path,
    capsys,
) -> None:
    initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")

    assert (
        main(
            [
                "runtime-preflight",
                "--repo-root",
                str(tmp_path),
                "--path",
                str(tmp_path / "plans" / "planning.sqlite3"),
                "--full-afk",
                "--plugin-invocation",
                "--plugin-full-afk",
                "--story-loop-status-checked",
                "--task-next-afk-requested",
                "--mcp-tool",
                "codex_supervisor.runtime_preflight",
                "--mcp-tool",
                "codex_supervisor.story_loop_status",
                "--mcp-tool",
                "codex_supervisor.task_current",
                "--mcp-tool",
                "codex_supervisor.task_next_afk",
                "--mcp-tool",
                "codex_supervisor.task_claim",
                "--mcp-tool",
                "codex_supervisor.story_loop_run_once",
                "--mcp-tool",
                "codex_supervisor.story_loop_start",
                "--mcp-tool",
                "codex_supervisor.story_loop_poll",
                "--evidence-mode",
                "strict_jsonl",
                "--json",
            ]
        )
        == 1
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["ledger"]["entrypoint"] == "desktop_plugin"
    assert payload["ledger"]["required_surface"] == "live_mcp"
    assert payload["ledger"]["decision_source"] == "cli_diagnostic"
    assert payload["diagnostics"]["missing_mcp_tools"] == []
    assert {issue["code"] for issue in payload["issues"]} == {
        "cli_diagnostic_not_plugin_full_afk_authority"
    }


def test_runtime_preflight_requires_explicit_strict_evidence_for_full_afk(
    tmp_path: Path,
) -> None:
    initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")

    report = build_runtime_preflight_report(
        repo_root=tmp_path,
        full_afk=True,
        plugin_invocation=True,
        plugin_full_afk=True,
        supervisor_backend="mcp",
        mcp_tools=(
            "codex_supervisor.runtime_preflight",
            "codex_supervisor.story_loop_status",
            "codex_supervisor.task_current",
            "codex_supervisor.task_next_afk",
            "codex_supervisor.task_claim",
            "codex_supervisor.story_loop_run_once",
            "codex_supervisor.story_loop_start",
            "codex_supervisor.story_loop_poll",
        ),
        story_loop_status_checked=True,
        task_next_afk_requested=True,
    )

    assert report.ok is False
    assert report.ledger.evidence_mode == "missing"
    assert {issue.code for issue in report.issues} == {"degraded_evidence_blocked"}


def test_runtime_preflight_cli_returns_json_and_nonzero_on_blocker(tmp_path, capsys) -> None:
    initialize_planning_database(tmp_path / "plans" / "planning.sqlite3")

    assert (
        main(
            [
                "runtime-preflight",
                "--repo-root",
                str(tmp_path),
                "--path",
                str(tmp_path / "plans" / "planning.sqlite3"),
                "--full-afk",
                "--plugin-invocation",
                "--supervisor-backend",
                "skill_only",
                "--no-cli-available",
                "--worker-execution",
                "current_thread",
                "--database-mode",
                "memory_mongodb",
                "--task-next-afk-requested",
                "--json",
            ]
        )
        == 1
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["ledger"]["worker_execution"] == "current_thread"
    assert {issue["code"] for issue in payload["issues"]} >= {
        "supervisor_backend_unavailable",
        "current_thread_fallback_blocked",
        "memory_database_fallback_forbidden",
    }
