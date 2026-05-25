from __future__ import annotations

import json
from pathlib import Path

from codex_supervisor.cli import main
from codex_supervisor.planning import (
    PlanProgressRecord,
    PlanRecord,
    initialize_planning_database,
)
from codex_supervisor.release import build_release_readiness_report

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_release_readiness_report_surfaces_repo_evidence_and_external_os_gap(
    tmp_path: Path,
) -> None:
    report = build_release_readiness_report(
        REPO_ROOT,
        planning_db_path=tmp_path / "missing.sqlite3",
    )
    checks = {(check.section, check.name): check for check in report.checks}

    assert report.ready is False
    assert report.passing_checks >= 7
    assert report.gap_checks >= 1
    assert checks[("cli", "Package CLI entry point")].status == "pass"
    assert checks[("mcp", "MCP server and stdio tests")].status == "pass"
    assert checks[("plugin", "Codex Desktop plugin surface")].status == "pass"
    assert checks[("project_scaffold", "Spawned-project dry-run scaffold surface")].status == "pass"
    assert checks[("verification", "Publication-ready verification posture")].status == "pass"
    assert checks[("verification", "Integrity and hygiene gates")].status == "pass"
    external_os = checks[("os_validation", "External Windows install validation evidence")]
    assert external_os.status == "gap"
    assert "missing:" in external_os.evidence[0]
    assert "Windows install validation" in external_os.next_action


def test_release_readiness_uses_reviewed_windows_validation_evidence(tmp_path: Path) -> None:
    db_path = _validation_db(
        tmp_path,
        details={
            "platform": "windows",
            "status": "passed",
            "reviewed": True,
            "commands": [
                "uv run --no-sync python -B -m codex_supervisor.cli --help",
                "uv run --no-sync python -B scripts/verify.py --publication-ready",
            ],
            "environment": {"os": "Windows", "python": "3.14.5"},
        },
    )

    report = build_release_readiness_report(REPO_ROOT, planning_db_path=db_path)
    external_os = next(
        check
        for check in report.checks
        if (check.section, check.name)
        == ("os_validation", "External Windows install validation evidence")
    )

    assert external_os.status == "pass"
    assert external_os.next_action == ""
    assert any("release_validation_recorded" in item for item in external_os.evidence)
    assert any("command passed" in item for item in external_os.evidence)
    assert any("environment: os=Windows" in item for item in external_os.evidence)


def test_release_readiness_rejects_unreviewed_windows_validation_evidence(
    tmp_path: Path,
) -> None:
    db_path = _validation_db(
        tmp_path,
        details={
            "platform": "windows",
            "status": "passed",
            "reviewed": False,
            "commands": ["uv run --no-sync python -B -m codex_supervisor.cli --help"],
        },
    )

    report = build_release_readiness_report(REPO_ROOT, planning_db_path=db_path)
    external_os = next(
        check
        for check in report.checks
        if (check.section, check.name)
        == ("os_validation", "External Windows install validation evidence")
    )

    assert external_os.status == "gap"
    assert any("reviewed=true" in item for item in external_os.evidence)


def test_release_readiness_report_marks_missing_repo_surfaces_as_gaps(tmp_path: Path) -> None:
    report = build_release_readiness_report(tmp_path)
    checks = {(check.section, check.name): check for check in report.checks}
    mcp_check = next(check for check in report.checks if check.section == "mcp")

    assert report.ready is False
    assert report.passing_checks == 0
    assert report.gap_checks == len(report.checks)
    assert {check.status for check in report.checks} == {"gap"}
    assert "missing:" in mcp_check.evidence[0]
    assert checks[("cli", "Package CLI entry point")].evidence == (
        "missing: pyproject.toml declares the codex-supervisor console script",
        "missing: src/codex_supervisor/cli.py exists",
    )
    assert all(
        item.startswith("missing:")
        for item in checks[("documentation", "Install, run, plugin, and scaffold docs")].evidence
    )
    assert all(
        item.startswith("missing:")
        for item in checks[("os_validation", "Linux CI validation surface")].evidence
    )


def test_cli_release_readiness_emits_json(capsys) -> None:
    assert (
        main(
            [
                "release-readiness",
                "--repo-root",
                str(REPO_ROOT),
                "--planning-db",
                str(REPO_ROOT / "missing.sqlite3"),
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    checks = {(check["section"], check["name"]): check for check in payload["checks"]}

    assert payload["ready"] is False
    assert checks[("cli", "Package CLI entry point")]["status"] == "pass"
    assert (
        checks[("os_validation", "External Windows install validation evidence")]["status"] == "gap"
    )


def test_cli_release_readiness_emits_human_report(capsys) -> None:
    assert (
        main(
            [
                "release-readiness",
                "--repo-root",
                str(REPO_ROOT),
                "--planning-db",
                str(REPO_ROOT / "missing.sqlite3"),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out

    assert "release_ready: False" in output
    assert "os_validation" in output
    assert "External Windows install validation evidence" in output


def test_cli_release_readiness_accepts_planning_db(capsys, tmp_path: Path) -> None:
    db_path = _validation_db(
        tmp_path,
        details={
            "platform": "windows",
            "status": "passed",
            "reviewed": True,
            "commands": ["uv run --no-sync python -B scripts/verify.py --publication-ready"],
        },
    )

    assert (
        main(
            [
                "release-readiness",
                "--repo-root",
                str(REPO_ROOT),
                "--planning-db",
                str(db_path),
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    checks = {(check["section"], check["name"]): check for check in payload["checks"]}

    assert (
        checks[("os_validation", "External Windows install validation evidence")]["status"]
        == "pass"
    )


def _validation_db(tmp_path: Path, *, details: dict[str, object]) -> Path:
    db_path = tmp_path / "plans" / "planning.sqlite3"
    store = initialize_planning_database(db_path)
    store.upsert_plan(
        PlanRecord(
            plan_id="plan-release",
            slug="release",
            title="Release",
            goal="Validate release evidence.",
            status="active",
        )
    )
    store.add_plan_progress(
        PlanProgressRecord(
            progress_id="progress-windows-validation",
            plan_id="plan-release",
            event_type="release_validation_recorded",
            summary="Windows validation recorded.",
            details=json.dumps(details),
        )
    )
    return db_path
