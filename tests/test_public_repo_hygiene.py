from __future__ import annotations

import importlib.util
import sqlite3
import subprocess
from pathlib import Path
from types import ModuleType


def test_publication_ready_detects_untracked_and_unstaged_files(tmp_path):
    module = _load_hygiene_module()
    _git(tmp_path, "init")

    tracked_file = tmp_path / "tracked.txt"
    tracked_file.write_text("ok", encoding="utf-8")

    untracked_failures = module._check_no_untracked_or_unstaged_files(tmp_path)
    assert any("untracked public candidate" in failure for failure in untracked_failures)

    _git(tmp_path, "add", "tracked.txt")

    assert module._check_no_untracked_or_unstaged_files(tmp_path) == ()

    tracked_file.write_text("changed", encoding="utf-8")

    unstaged_failures = module._check_no_untracked_or_unstaged_files(tmp_path)
    assert any("unstaged change" in failure for failure in unstaged_failures)


def test_publication_ready_scans_indexed_blob_contents(tmp_path):
    module = _load_hygiene_module()
    _git(tmp_path, "init")
    key_name = "OPENAI" + "_API" + "_KEY"
    (tmp_path / "tracked.txt").write_text(f"{key_name}='value'\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")

    failures = module._check_indexed_text_files(tmp_path)

    assert any("staged blob matched" in failure and key_name in failure for failure in failures)


def test_public_hygiene_detects_secrets_and_unexpected_databases(tmp_path):
    module = _load_hygiene_module()
    _git(tmp_path, "init")
    key_name = "OPENAI" + "_API" + "_KEY"
    password_name = "pass" + "word"
    secret_name = "sec" + "ret"
    (tmp_path / "notes.txt").write_text(f'{key_name} = "value"', encoding="utf-8")
    (tmp_path / "settings.txt").write_text(
        f"{password_name} = hunter2\n{secret_name}: abc123\n",
        encoding="utf-8",
    )
    (tmp_path / "local.db").write_bytes(b"not sqlite")

    text_failures = module._check_candidate_text_files(tmp_path)
    database_failures = module._check_candidate_database_files(tmp_path)

    assert any(key_name in failure for failure in text_failures)
    assert any("settings.txt" in failure for failure in text_failures)
    assert database_failures == ("unexpected public database file: local.db",)


def test_public_hygiene_detects_cross_platform_home_paths(tmp_path):
    module = _load_hygiene_module()
    _git(tmp_path, "init")
    linux_home = "/" + "home" + "/example/private-project"
    mac_home = "/" + "Users" + "/example/private-project"
    unc_home = "\\\\" + "Users" + "\\\\example\\\\private-project"
    (tmp_path / "linux.txt").write_text(linux_home, encoding="utf-8")
    (tmp_path / "mac.txt").write_text(mac_home, encoding="utf-8")
    (tmp_path / "unc.txt").write_text(unc_home, encoding="utf-8")

    failures = module._check_candidate_text_files(tmp_path)

    assert len(failures) == 3


def test_public_hygiene_rejects_invalid_utf8_text_candidates(tmp_path):
    module = _load_hygiene_module()
    _git(tmp_path, "init")
    (tmp_path / "README.md").write_bytes(b"\xff\xfe")

    failures = module._check_candidate_text_files(tmp_path)

    assert any("not valid UTF-8" in failure for failure in failures)


def test_public_hygiene_ignores_deleted_tracked_files_until_publication_ready(tmp_path):
    module = _load_hygiene_module()
    _git(tmp_path, "init")
    path = tmp_path / "docs" / "README.md"
    path.parent.mkdir(parents=True)
    path.write_text("temporary\n", encoding="utf-8")
    _git(tmp_path, "add", "docs/README.md")
    path.unlink()

    assert module._check_candidate_text_files(tmp_path) == ()

    failures = module._check_no_untracked_or_unstaged_files(tmp_path)

    assert any("unstaged change" in failure and "docs/README.md" in failure for failure in failures)


def test_publication_ready_rejects_invalid_utf8_indexed_text_blobs(tmp_path):
    module = _load_hygiene_module()
    _git(tmp_path, "init")
    (tmp_path / "README.md").write_bytes(b"\xff\xfe")
    _git(tmp_path, "add", "README.md")

    failures = module._check_indexed_text_files(tmp_path)

    assert any("not valid UTF-8" in failure for failure in failures)


def test_public_hygiene_scans_allowed_planning_database_dump(tmp_path):
    module = _load_hygiene_module()
    (tmp_path / "plans").mkdir()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    key_name = "OPENAI" + "_API" + "_KEY"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE notes(value TEXT)")
        connection.execute("INSERT INTO notes VALUES (?)", (f"{key_name}='value'",))

    failures = module._check_database_dumps(tmp_path)

    assert any(key_name in failure for failure in failures)


def test_publication_ready_rejects_ignored_source_artifacts(tmp_path):
    module = _load_hygiene_module()
    (tmp_path / "plans").mkdir()
    (tmp_path / "sources" / "snarktank-ralph").mkdir(parents=True)
    db_path = tmp_path / "plans" / "planning.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE plan_artifact_links (plan_id TEXT, artifact_id TEXT, relationship TEXT)"
        )
        connection.execute("CREATE TABLE plan_progress_events (linked_artifact_id TEXT)")
        connection.execute(
            "INSERT INTO plan_artifact_links VALUES ('plan', 'sources/snarktank-ralph', 'known')"
        )
        connection.execute(
            "INSERT INTO plan_artifact_links VALUES ('plan', 'sources/not-documented', 'unknown')"
        )
        connection.execute(
            """
            INSERT INTO plan_artifact_links
            VALUES ('plan', 'sources/snarktank-ralph/../../plans/planning.sqlite3', 'escape')
            """
        )

    failures = module._check_planning_artifacts_indexed(tmp_path, set())

    assert any(
        failure == "planning artifact is not tracked for publication: sources/snarktank-ralph"
        for failure in failures
    )
    assert any("sources/not-documented" in failure for failure in failures)
    assert any("not repo-local" in failure for failure in failures)


def test_publication_ready_rejects_drive_relative_artifact_paths(tmp_path):
    module = _load_hygiene_module()
    (tmp_path / "plans").mkdir()
    db_path = tmp_path / "plans" / "planning.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE plan_artifact_links (plan_id TEXT, artifact_id TEXT, relationship TEXT)"
        )
        connection.execute("CREATE TABLE plan_progress_events (linked_artifact_id TEXT)")
        connection.execute(
            "INSERT INTO plan_artifact_links VALUES ('plan', 'C:relative/path.md', 'evidence')"
        )

    failures = module._check_planning_artifacts_indexed(tmp_path, set())

    assert any(
        "C:relative/path.md" in failure and "not repo-local" in failure for failure in failures
    )


def _load_hygiene_module() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "check_public_repo_hygiene.py"
    spec = importlib.util.spec_from_file_location("check_public_repo_hygiene", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> None:
    subprocess.run(("git", *args), cwd=repo, check=True, capture_output=True)
