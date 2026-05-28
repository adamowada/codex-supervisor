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
        assert (
            connection.execute("select count(*) from plans where status = 'active'").fetchone()[0]
            == 1
        )
        assert (
            connection.execute("select count(*) from tasks where status = 'ready'").fetchone()[0]
            >= 1
        )
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
