from __future__ import annotations

import json
from pathlib import Path

from codex_supervisor.cli import main
from codex_supervisor.release import build_release_readiness_report

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_release_readiness_report_surfaces_repo_evidence_and_external_os_gap() -> None:
    report = build_release_readiness_report(REPO_ROOT)
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
    assert "Windows install validation" in external_os.next_action


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
    assert main(["release-readiness", "--repo-root", str(REPO_ROOT), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    checks = {(check["section"], check["name"]): check for check in payload["checks"]}

    assert payload["ready"] is False
    assert checks[("cli", "Package CLI entry point")]["status"] == "pass"
    assert (
        checks[("os_validation", "External Windows install validation evidence")]["status"] == "gap"
    )


def test_cli_release_readiness_emits_human_report(capsys) -> None:
    assert main(["release-readiness", "--repo-root", str(REPO_ROOT)]) == 0

    output = capsys.readouterr().out

    assert "release_ready: False" in output
    assert "os_validation" in output
    assert "External Windows install validation evidence" in output
