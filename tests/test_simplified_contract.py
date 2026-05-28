from __future__ import annotations

import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "plans" / "planning.sqlite3"


def test_fresh_planning_database_contract() -> None:
    connection = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
            )
        }
        assert tables == {
            "attempts",
            "decisions",
            "evidence_bundles",
            "meta",
            "plans",
            "tasks",
        }
        assert (
            connection.execute(
                "select value from meta where key = 'schema_name'"
            ).fetchone()[0]
            == "fresh_simplified_planning"
        )
        active_plans = connection.execute(
            "select count(*) from plans where status = 'active'"
        ).fetchone()[0]
        done_plans = connection.execute(
            "select count(*) from plans where status = 'done'"
        ).fetchone()[0]
        open_tasks = connection.execute(
            "select count(*) from tasks where status in ('ready', 'running')"
        ).fetchone()[0]
        assert active_plans <= 1
        assert active_plans + done_plans >= 1
        if active_plans:
            assert open_tasks >= 1
        else:
            assert open_tasks == 0
    finally:
        connection.close()


def test_single_repo_local_skill() -> None:
    skill_files = sorted((REPO_ROOT / ".agents" / "skills").glob("*/SKILL.md"))
    assert [path.parent.name for path in skill_files] == ["codex-supervisor"]


def test_simplification_insight_exists() -> None:
    insight = REPO_ROOT / "insights" / "simplification-lessons-2026-05-28.md"
    text = insight.read_text(encoding="utf-8")
    assert "TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision" in text
    assert "Assurance" in text
