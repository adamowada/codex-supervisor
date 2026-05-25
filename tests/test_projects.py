import json
from pathlib import Path, PurePosixPath, PureWindowsPath

from codex_supervisor.cli import main
from codex_supervisor.projects import (
    discover_projects,
    stable_project_id_from_path,
)


def test_project_registry_discovers_generic_repo_with_stable_id(tmp_path: Path) -> None:
    repo = _write_generic_repo(tmp_path / "demo-supervised")

    first = discover_projects((repo,))
    second = discover_projects((repo,))

    assert len(first) == 1
    entry = first[0]
    assert entry == second[0]
    assert entry.project_id.startswith("demo-supervised-")
    assert entry.root_path == str(repo.resolve())
    assert entry.adapter_type == "generic_repo"
    assert entry.trust_policy == "local_trusted"
    assert entry.status == "ready"
    assert entry.facts is not None
    assert entry.facts.has_planning_database is True
    assert entry.facts.has_tasks_json is True
    assert entry.facts.source_documents == (
        "AGENTS.md",
        "PLANS.md",
        "TESTING.md",
        "README.md",
    )
    assert entry.facts.verification_commands == (
        "uv run python -B scripts/verify.py",
        "uv run python -B scripts/check_protected_files.py",
    )


def test_generic_repo_adapter_reports_bounded_facts_only(tmp_path: Path) -> None:
    repo = _write_generic_repo(tmp_path / "bounded")
    (repo / "deep").mkdir()
    (repo / "deep" / "private-notes.md").write_text("not an authority file", encoding="utf-8")
    (repo / "random.py").write_text("print('not a verification surface')\n", encoding="utf-8")

    entry = discover_projects((repo,))[0]

    assert entry.facts is not None
    facts = entry.facts
    assert "deep/private-notes.md" not in facts.source_documents
    assert "random.py" not in facts.verification_commands
    assert facts.authority_markers == (
        "AGENTS.md",
        "PLANS.md",
        "plans/planning.sqlite3",
        "TASKS.json",
    )


def test_project_list_cli_prints_json_for_current_repo(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    repo = _write_generic_repo(tmp_path / "current")
    monkeypatch.chdir(repo)

    assert main(["project-list", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["project_id"].startswith("current-")
    assert payload[0]["adapter_type"] == "generic_repo"
    assert payload[0]["status"] == "ready"
    assert payload[0]["facts"]["has_planning_database"] is True


def test_project_list_cli_prints_human_summary(tmp_path: Path, capsys) -> None:
    repo = _write_generic_repo(tmp_path / "human-summary")

    assert main(["project-list", "--root", str(repo)]) == 0

    output = capsys.readouterr().out
    assert "human-summary-" in output
    assert "generic_repo" in output
    assert "local_trusted" in output
    assert "source_documents: AGENTS.md, PLANS.md, TESTING.md, README.md" in output


def test_project_list_cli_reports_missing_roots_without_creating_files(
    tmp_path: Path,
    capsys,
) -> None:
    missing = tmp_path / "missing-project"

    assert main(["project-list", "--root", str(missing)]) == 1

    captured = capsys.readouterr()
    assert "Project root does not exist" in captured.err
    assert str(missing) in captured.err
    assert not missing.exists()


def test_stable_project_id_normalizes_windows_and_posix_paths() -> None:
    windows_a = PureWindowsPath(r"D:\Workspace\Example\Repo Name")
    windows_b = PureWindowsPath("D:/Workspace/Example/Repo Name")
    posix = PurePosixPath("/srv/example/Repo Name")

    assert stable_project_id_from_path(windows_a) == stable_project_id_from_path(windows_b)
    assert stable_project_id_from_path(windows_a).startswith("repo-name-")
    assert stable_project_id_from_path(posix).startswith("repo-name-")
    assert stable_project_id_from_path(posix) != stable_project_id_from_path(windows_a)


def _write_generic_repo(root: Path) -> Path:
    root.mkdir()
    (root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (root / "PLANS.md").write_text("# Plans\n", encoding="utf-8")
    (root / "TESTING.md").write_text("# Testing\n", encoding="utf-8")
    (root / "README.md").write_text("# Demo\n", encoding="utf-8")
    (root / "TASKS.json").write_text("[]\n", encoding="utf-8")
    (root / "plans").mkdir()
    (root / "plans" / "planning.sqlite3").write_bytes(b"not inspected by registry")
    (root / "scripts").mkdir()
    (root / "scripts" / "verify.py").write_text("print('verify')\n", encoding="utf-8")
    (root / "scripts" / "check_protected_files.py").write_text(
        "print('locks')\n",
        encoding="utf-8",
    )
    return root
