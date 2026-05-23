from __future__ import annotations

from codex_supervisor.locks import check_protected_files, sha256_file


def test_check_protected_files_reports_changed_file(tmp_path):
    protected = tmp_path / "README.md"
    protected.write_text("hello\n", encoding="utf-8")

    expected = sha256_file(protected)
    assert check_protected_files(tmp_path, {"README.md": expected}) == ()

    protected.write_text("changed\n", encoding="utf-8")
    failures = check_protected_files(tmp_path, {"README.md": expected})

    assert len(failures) == 1
    assert failures[0].relative_path == "README.md"
    assert failures[0].reason == "changed"


def test_check_protected_files_reports_missing_file(tmp_path):
    failures = check_protected_files(tmp_path, {"README.md": "abc"})

    assert len(failures) == 1
    assert failures[0].reason == "missing"
