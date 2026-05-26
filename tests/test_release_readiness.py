from __future__ import annotations

import json
import subprocess
from pathlib import Path

from codex_supervisor.cli import main
from codex_supervisor.planning import (
    CiRunEvidenceRecord,
    PlanArtifactLinkRecord,
    PlanProgressRecord,
    PlanRecord,
    initialize_planning_database,
)
from codex_supervisor.release import _resolve_target_commit, build_release_readiness_report

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET_COMMIT = "a" * 40
STALE_COMMIT = "b" * 40


def test_release_readiness_report_surfaces_repo_evidence_and_external_os_gap(
    tmp_path: Path,
) -> None:
    report = build_release_readiness_report(
        REPO_ROOT,
        planning_db_path=tmp_path / "missing.sqlite3",
        target_commit=TARGET_COMMIT,
    )
    checks = {(check.section, check.name): check for check in report.checks}

    assert report.ready is False
    assert report.target_commit == TARGET_COMMIT
    assert report.passing_checks >= 8
    assert report.gap_checks >= 1
    assert checks[("cli", "Package CLI entry point")].status == "pass"
    assert checks[("mcp", "MCP server and stdio tests")].status == "pass"
    assert checks[("plugin", "Codex Desktop plugin surface")].status == "pass"
    assert checks[("project_scaffold", "Spawned-project dry-run scaffold surface")].status == "pass"
    assert checks[("project_scaffold", "Spawned-project apply surface")].status == "pass"
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
            "head_sha": TARGET_COMMIT,
            "environment": {"os": "Windows", "python": "3.14.5"},
        },
    )

    report = build_release_readiness_report(
        REPO_ROOT,
        planning_db_path=db_path,
        target_commit=TARGET_COMMIT,
    )
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


def test_release_readiness_rejects_stale_windows_validation_evidence(
    tmp_path: Path,
) -> None:
    db_path = _validation_db(
        tmp_path,
        details={
            "platform": "windows",
            "status": "passed",
            "reviewed": True,
            "head_sha": STALE_COMMIT,
            "commands": ["uv run --no-sync python -B -m codex_supervisor.cli --help"],
        },
    )

    report = build_release_readiness_report(
        REPO_ROOT,
        planning_db_path=db_path,
        target_commit=TARGET_COMMIT,
    )
    external_os = next(
        check
        for check in report.checks
        if (check.section, check.name)
        == ("os_validation", "External Windows install validation evidence")
    )

    assert external_os.status == "gap"
    assert any("stale:" in item and STALE_COMMIT in item for item in external_os.evidence)
    assert any(TARGET_COMMIT in item for item in external_os.evidence)


def test_release_readiness_rejects_unreviewed_windows_validation_evidence(
    tmp_path: Path,
) -> None:
    db_path = _validation_db(
        tmp_path,
        details={
            "platform": "windows",
            "status": "passed",
            "reviewed": False,
            "head_sha": TARGET_COMMIT,
            "commands": ["uv run --no-sync python -B -m codex_supervisor.cli --help"],
        },
    )

    report = build_release_readiness_report(
        REPO_ROOT,
        planning_db_path=db_path,
        target_commit=TARGET_COMMIT,
    )
    external_os = next(
        check
        for check in report.checks
        if (check.section, check.name)
        == ("os_validation", "External Windows install validation evidence")
    )

    assert external_os.status == "gap"
    assert any("reviewed=true" in item for item in external_os.evidence)


def test_release_readiness_report_marks_missing_repo_surfaces_as_gaps(tmp_path: Path) -> None:
    report = build_release_readiness_report(tmp_path, target_commit=TARGET_COMMIT)
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
                "--commit",
                TARGET_COMMIT,
                "--json",
            ]
        )
        == 1
    )

    payload = json.loads(capsys.readouterr().out)
    checks = {(check["section"], check["name"]): check for check in payload["checks"]}

    assert payload["ready"] is False
    assert payload["target_commit"] == TARGET_COMMIT
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
                "--commit",
                TARGET_COMMIT,
            ]
        )
        == 1
    )

    output = capsys.readouterr().out

    assert f"target_commit: {TARGET_COMMIT}" in output
    assert "release_ready: False" in output
    assert "os_validation" in output
    assert "External Windows install validation evidence" in output


def test_release_readiness_requires_current_live_and_ci_evidence(tmp_path: Path) -> None:
    db_path = _release_db(tmp_path, target_commit=TARGET_COMMIT)

    report = build_release_readiness_report(
        REPO_ROOT,
        planning_db_path=db_path,
        target_commit=TARGET_COMMIT,
    )
    checks = {(check.section, check.name): check for check in report.checks}

    assert report.ready is True
    assert checks[("ci", "Current successful CI for target commit")].status == "pass"
    assert checks[("verification", "Current publication-ready verification evidence")].status == (
        "pass"
    )
    assert checks[("live_evidence", "Live worker smoke evidence")].status == "pass"
    assert checks[("live_evidence", "Live review smoke evidence")].status == "pass"
    assert checks[("live_evidence", "Mutating MCP smoke evidence")].status == "pass"
    assert checks[("live_evidence", "Real project bootstrap smoke evidence")].status == "pass"


def test_release_readiness_requires_bootstrap_apply_artifact_link(tmp_path: Path) -> None:
    db_path = _release_db(
        tmp_path,
        target_commit=TARGET_COMMIT,
        include_bootstrap_artifact=False,
    )

    report = build_release_readiness_report(
        REPO_ROOT,
        planning_db_path=db_path,
        target_commit=TARGET_COMMIT,
    )
    check = next(
        check
        for check in report.checks
        if (check.section, check.name) == ("live_evidence", "Real project bootstrap smoke evidence")
    )

    assert report.ready is False
    assert check.status == "gap"
    assert any("spawned-project-apply JSON artifact" in item for item in check.evidence)


def test_release_readiness_rejects_stale_ci_and_live_evidence(tmp_path: Path) -> None:
    db_path = _release_db(tmp_path, target_commit=STALE_COMMIT)

    report = build_release_readiness_report(
        REPO_ROOT,
        planning_db_path=db_path,
        target_commit=TARGET_COMMIT,
    )
    checks = {(check.section, check.name): check for check in report.checks}

    assert report.ready is False
    assert checks[("ci", "Current successful CI for target commit")].status == "gap"
    assert any(
        "stale:" in item and STALE_COMMIT in item
        for item in checks[("ci", "Current successful CI for target commit")].evidence
    )
    assert checks[("live_evidence", "Live worker smoke evidence")].status == "gap"
    assert any(
        "stale:" in item and STALE_COMMIT in item
        for item in checks[("live_evidence", "Live worker smoke evidence")].evidence
    )


def test_cli_release_readiness_accepts_planning_db(capsys, tmp_path: Path) -> None:
    db_path = _release_db(tmp_path, target_commit=TARGET_COMMIT)

    assert (
        main(
            [
                "release-readiness",
                "--repo-root",
                str(REPO_ROOT),
                "--planning-db",
                str(db_path),
                "--commit",
                TARGET_COMMIT,
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    checks = {(check["section"], check["name"]): check for check in payload["checks"]}

    assert payload["ready"] is True
    assert checks[("os_validation", "External Windows install validation evidence")]["status"] == (
        "pass"
    )
    assert checks[("live_evidence", "Live worker smoke evidence")]["status"] == "pass"


def test_release_readiness_defaults_to_subject_commit_after_evidence_commit(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "codex@example.test")
    _git(tmp_path, "config", "user.name", "Codex Test")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "code.py").write_text("print('v1')\n", encoding="utf-8")
    _git(tmp_path, "add", "src/code.py")
    _git(tmp_path, "commit", "-m", "code")
    code_commit = _git(tmp_path, "rev-parse", "HEAD").stdout.strip()

    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "planning.sqlite3").write_text("evidence\n", encoding="utf-8")
    (tmp_path / "HANDOFF.md").write_text("handoff\n", encoding="utf-8")
    (tmp_path / "insights").mkdir()
    (tmp_path / "insights" / "release.md").write_text("insight\n", encoding="utf-8")
    _git(tmp_path, "add", "plans/planning.sqlite3", "HANDOFF.md", "insights/release.md")
    _git(tmp_path, "commit", "-m", "release evidence")

    assert _resolve_target_commit(tmp_path, None) == code_commit


def test_release_readiness_keeps_head_when_latest_commit_changes_code(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "codex@example.test")
    _git(tmp_path, "config", "user.name", "Codex Test")
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "planning.sqlite3").write_text("evidence\n", encoding="utf-8")
    _git(tmp_path, "add", "plans/planning.sqlite3")
    _git(tmp_path, "commit", "-m", "evidence")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "code.py").write_text("print('v2')\n", encoding="utf-8")
    _git(tmp_path, "add", "src/code.py")
    _git(tmp_path, "commit", "-m", "code")
    head_commit = _git(tmp_path, "rev-parse", "HEAD").stdout.strip()

    assert _resolve_target_commit(tmp_path, None) == head_commit


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


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ("git", *args),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result


def _release_db(
    tmp_path: Path,
    *,
    target_commit: str,
    include_bootstrap_artifact: bool = True,
) -> Path:
    db_path = _validation_db(
        tmp_path,
        details={
            "platform": "windows",
            "status": "passed",
            "reviewed": True,
            "head_sha": target_commit,
            "commands": [
                "uv run --no-sync python -B -m codex_supervisor.cli --help",
                "uv run --no-sync python -B scripts/verify.py --publication-ready",
            ],
            "environment": {"os": "Windows", "python": "3.14.5"},
        },
    )
    store = initialize_planning_database(db_path)
    store.record_ci_run_evidence(
        CiRunEvidenceRecord(
            progress_id="progress-ci-current",
            plan_id="plan-release",
            provider="github-actions",
            run_id="12345",
            run_url="https://github.com/owner/repo/actions/runs/12345",
            head_sha=target_commit,
            status="completed",
            conclusion="success",
            workflow="Verify",
        )
    )
    bootstrap_artifact_id = "tests/fixtures/spawned-project-apply.json"
    for event_type, details in (
        (
            "publication_ready_verification_recorded",
            {
                "status": "passed",
                "head_sha": target_commit,
                "commands": ["uv run --no-sync python -B scripts/verify.py --publication-ready"],
            },
        ),
        (
            "live_worker_smoke_recorded",
            {
                "status": "passed",
                "head_sha": target_commit,
                "live": True,
                "commands": [
                    "uv run --no-sync python -B -m codex_supervisor.cli story-loop-run-once"
                ],
            },
        ),
        (
            "live_review_smoke_recorded",
            {
                "status": "passed",
                "head_sha": target_commit,
                "live": True,
                "commands": ["uv run --no-sync python -B -m codex_supervisor.cli review-run-live"],
            },
        ),
        (
            "mutating_mcp_smoke_recorded",
            {
                "status": "passed",
                "head_sha": target_commit,
                "mutating": True,
                "commands": ["codex-supervisor MCP task_upsert smoke"],
            },
        ),
        (
            "real_project_bootstrap_smoke_recorded",
            {
                "status": "passed",
                "head_sha": target_commit,
                "writes_files": True,
                "commands": [
                    "uv run --no-sync python -B -m codex_supervisor.cli spawned-project-apply"
                ],
            },
        ),
    ):
        progress = PlanProgressRecord(
            progress_id=f"progress-{event_type}",
            plan_id="plan-release",
            event_type=event_type,
            summary=f"Recorded {event_type}.",
            details=json.dumps(details),
            linked_artifact_id=(
                bootstrap_artifact_id
                if event_type == "real_project_bootstrap_smoke_recorded"
                and include_bootstrap_artifact
                else None
            ),
        )
        if event_type == "real_project_bootstrap_smoke_recorded" and include_bootstrap_artifact:
            store.add_plan_progress_with_artifact_links(
                progress,
                (
                    PlanArtifactLinkRecord(
                        plan_id="plan-release",
                        artifact_id=bootstrap_artifact_id,
                        relationship="real-project-bootstrap-smoke",
                    ),
                ),
            )
        else:
            store.add_plan_progress(progress)
    return db_path
