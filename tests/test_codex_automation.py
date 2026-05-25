from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_supervisor.cli import main
from codex_supervisor.codex_automation import (
    CodexAutomationBridgeSpec,
    build_codex_automation_bridge_dry_run,
    default_codex_automation_bridge_specs,
)

OBSERVED_AT = "2026-05-25T00:00:00Z"
PLAN_ID = "plan-stage10-codex-state-automation-bridge"
TASK_ID = "task-stage10e-codex-automation-bridge-dry-run"


def test_codex_automation_bridge_dry_run_builds_official_payloads(
    tmp_path: Path,
) -> None:
    report = build_codex_automation_bridge_dry_run(
        workspace_root=tmp_path,
        specs=default_codex_automation_bridge_specs(
            queue_reconciliation_rrule="FREQ=HOURLY;INTERVAL=6",
            health_check_rrule="FREQ=WEEKLY;BYDAY=MO;BYHOUR=9",
            model="gpt-5",
            reasoning_effort="medium",
        ),
        source_plan_id=PLAN_ID,
        source_task_id=TASK_ID,
        observed_at=OBSERVED_AT,
    )
    repeat = build_codex_automation_bridge_dry_run(
        workspace_root=tmp_path,
        specs=default_codex_automation_bridge_specs(
            queue_reconciliation_rrule="FREQ=HOURLY;INTERVAL=6",
            health_check_rrule="FREQ=WEEKLY;BYDAY=MO;BYHOUR=9",
            model="gpt-5",
            reasoning_effort="medium",
        ),
        source_plan_id=PLAN_ID,
        source_task_id=TASK_ID,
        observed_at=OBSERVED_AT,
    )

    assert report.findings == ()
    assert [proposal.purpose for proposal in report.proposals] == [
        "project_health_check",
        "queue_reconciliation",
    ]
    assert [proposal.proposal_id for proposal in report.proposals] == [
        proposal.proposal_id for proposal in repeat.proposals
    ]
    queue_proposal = next(
        proposal for proposal in report.proposals if proposal.purpose == "queue_reconciliation"
    )
    assert queue_proposal.proposal_id.startswith("codex-automation-")
    assert queue_proposal.action_type == "official-automation-suggested-create"
    assert queue_proposal.action_status == "proposed"
    assert queue_proposal.kind == "cron"
    assert queue_proposal.destination == ""
    assert queue_proposal.rrule == "FREQ=HOURLY;INTERVAL=6"
    assert queue_proposal.cwds == (tmp_path.resolve().as_posix(),)
    assert queue_proposal.source_kind == "planning_task"
    assert queue_proposal.source_plan_id == PLAN_ID
    assert queue_proposal.source_task_id == TASK_ID
    assert queue_proposal.confidence == "inferred"
    assert queue_proposal.official_payload["kind"] == "cron"
    assert queue_proposal.official_payload["name"] == "Codex Supervisor Queue Reconciliation"
    assert queue_proposal.official_payload["rrule"] == "FREQ=HOURLY;INTERVAL=6"
    assert queue_proposal.official_payload["executionEnvironment"] == "local"
    assert queue_proposal.official_payload["cwds"] == [tmp_path.resolve().as_posix()]
    assert queue_proposal.official_payload["model"] == "gpt-5"
    assert queue_proposal.official_payload["reasoningEffort"] == "medium"
    assert "Do not write Codex internal SQLite databases." in queue_proposal.prompt


def test_codex_automation_bridge_dry_run_surfaces_validation_findings(
    tmp_path: Path,
) -> None:
    report = build_codex_automation_bridge_dry_run(
        workspace_root=tmp_path,
        specs=(
            CodexAutomationBridgeSpec(
                name="duplicate",
                purpose="valid",
                rrule="FREQ=HOURLY;INTERVAL=4",
                prompt="Run a safe check.",
            ),
            CodexAutomationBridgeSpec(
                name="duplicate",
                purpose="duplicate",
                rrule="FREQ=HOURLY;INTERVAL=4",
                prompt="Run a duplicate check.",
            ),
            CodexAutomationBridgeSpec(
                name="bad schedule",
                purpose="bad_schedule",
                rrule="FREQ=DAILY",
                prompt="Run a bad schedule check.",
            ),
            CodexAutomationBridgeSpec(
                name="bad kind",
                purpose="bad_kind",
                rrule="FREQ=HOURLY",
                prompt="Run a bad kind check.",
                kind="calendar",
            ),
            CodexAutomationBridgeSpec(
                name="bad destination",
                purpose="bad_destination",
                rrule="FREQ=WEEKLY",
                prompt="Run a bad destination check.",
                kind="heartbeat",
                destination="workspace",
            ),
        ),
        observed_at=OBSERVED_AT,
    )
    missing_workspace_report = build_codex_automation_bridge_dry_run(
        workspace_root=tmp_path / "missing",
        specs=(
            CodexAutomationBridgeSpec(
                name="valid",
                purpose="valid",
                rrule="FREQ=HOURLY",
                prompt="Run a safe check.",
            ),
        ),
        observed_at=OBSERVED_AT,
    )

    assert [proposal.name for proposal in report.proposals] == ["duplicate"]
    assert {finding.finding_type for finding in report.findings} == {
        "duplicate_proposal_name",
        "invalid_rrule",
        "unsupported_automation_kind",
        "unsupported_destination",
    }
    assert missing_workspace_report.proposals == ()
    assert {finding.finding_type for finding in missing_workspace_report.findings} == {
        "missing_workspace_root"
    }


def test_codex_automation_dry_run_cli_prints_json_without_state_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sentinel = workspace / "private.txt"
    sentinel.write_text("do-not-print-this-secret", encoding="utf-8")
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "state_5.sqlite").write_bytes(b"not touched")
    before_workspace = _file_snapshot(workspace)
    before_codex_home = _file_snapshot(codex_home)

    exit_code = main(
        [
            "codex-automation-dry-run",
            "--workspace-root",
            str(workspace),
            "--queue-reconciliation-rrule",
            "FREQ=HOURLY;INTERVAL=6",
            "--health-check-rrule",
            "FREQ=WEEKLY;BYDAY=MO;BYHOUR=9",
            "--source-plan-id",
            PLAN_ID,
            "--source-task-id",
            TASK_ID,
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    serialized = json.dumps(payload, sort_keys=True)

    assert exit_code == 0
    assert captured.err == ""
    assert _file_snapshot(workspace) == before_workspace
    assert _file_snapshot(codex_home) == before_codex_home
    assert len(payload["proposals"]) == 2
    assert payload["proposals"][0]["official_payload"]["kind"] == "cron"
    assert payload["proposals"][0]["source_plan_id"] == PLAN_ID
    assert payload["proposals"][0]["source_task_id"] == TASK_ID
    assert payload["findings"] == []
    assert "do-not-print-this-secret" not in serialized
    assert "not touched" not in serialized


def test_codex_automation_dry_run_cli_prints_human_findings(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        [
            "codex-automation-dry-run",
            "--workspace-root",
            str(tmp_path / "missing"),
            "--queue-reconciliation-rrule",
            "FREQ=DAILY",
            "--health-check-rrule",
            "FREQ=WEEKLY",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "proposals:\n- none" in captured.out
    assert "missing_workspace_root" in captured.out
    assert "invalid_rrule" in captured.out


def _file_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
