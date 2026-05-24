from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType


def test_source_inventory_detects_missing_documentation(tmp_path):
    module = _load_source_inventory_module()
    (tmp_path / "sources").mkdir()
    (tmp_path / "ATTRIBUTIONS.md").write_text(_attributions_pointer(), encoding="utf-8")
    (tmp_path / "sources" / "README.md").write_text("", encoding="utf-8")

    failures = module.check_source_inventory(tmp_path)

    assert any("source row missing" in failure.reason for failure in failures)


def test_source_inventory_detects_swapped_commit_in_documented_row(tmp_path):
    module = _load_source_inventory_module()
    (tmp_path / "sources").mkdir()
    table = _source_table(
        module,
        overrides={
            "openai-codex": {
                "commit": module.EXPECTED_SOURCES["openclaw-openclaw"]["commit"],
            },
        },
    )
    (tmp_path / "ATTRIBUTIONS.md").write_text(_attributions_pointer(), encoding="utf-8")
    (tmp_path / "sources" / "README.md").write_text(table, encoding="utf-8")

    failures = module.check_source_inventory(tmp_path)

    assert any(
        failure.source == "openai-codex" and "commit SHA mismatch" in failure.reason
        for failure in failures
    )


def test_source_inventory_rejects_extra_upstream_text(tmp_path):
    module = _load_source_inventory_module()
    (tmp_path / "sources").mkdir()
    table = _source_table(
        module,
        overrides={
            "openai-codex": {
                "url": (
                    module.EXPECTED_SOURCES["openai-codex"]["url"]
                    + " https://example.test/conflict"
                ),
            },
        },
    )
    (tmp_path / "ATTRIBUTIONS.md").write_text(_attributions_pointer(), encoding="utf-8")
    (tmp_path / "sources" / "README.md").write_text(table, encoding="utf-8")

    failures = module.check_source_inventory(tmp_path)

    assert any(
        failure.source == "openai-codex" and "upstream URL mismatch" in failure.reason
        for failure in failures
    )


def test_source_inventory_rejects_duplicate_table_in_attributions(tmp_path):
    module = _load_source_inventory_module()
    (tmp_path / "sources").mkdir()
    table = _source_table(module)
    (tmp_path / "ATTRIBUTIONS.md").write_text(
        f"{_attributions_pointer()}\n\n{table}",
        encoding="utf-8",
    )
    (tmp_path / "sources" / "README.md").write_text(table, encoding="utf-8")

    failures = module.check_source_inventory(tmp_path)

    assert any(
        failure.source == "ATTRIBUTIONS.md" and "duplicate source inventory table" in failure.reason
        for failure in failures
    )


def test_source_inventory_detects_unexpected_documented_row(tmp_path):
    module = _load_source_inventory_module()
    (tmp_path / "sources").mkdir()
    table = _source_table(module)
    extra = "| `extra-source` | `https://example.test/repo` | `abc123` | MIT | Extra. |"
    table = f"{table}\n{extra}"
    (tmp_path / "ATTRIBUTIONS.md").write_text(_attributions_pointer(), encoding="utf-8")
    (tmp_path / "sources" / "README.md").write_text(table, encoding="utf-8")

    failures = module.check_source_inventory(tmp_path)

    assert any(
        failure.source == "extra-source" and "unexpected source row" in failure.reason
        for failure in failures
    )


def test_source_inventory_does_not_skip_rows_containing_dashes(tmp_path):
    module = _load_source_inventory_module()
    (tmp_path / "sources").mkdir()
    table = _source_table(
        module,
        overrides={
            "openai-codex": {
                "use_posture": "Inspiration only --- not copied.",
            },
        },
    )
    (tmp_path / "ATTRIBUTIONS.md").write_text(_attributions_pointer(), encoding="utf-8")
    (tmp_path / "sources" / "README.md").write_text(table, encoding="utf-8")

    failures = module.check_source_inventory(tmp_path)

    assert any(
        failure.source == "openai-codex" and "use posture mismatch" in failure.reason
        for failure in failures
    )


def test_source_inventory_detects_license_and_use_posture_drift(tmp_path):
    module = _load_source_inventory_module()
    (tmp_path / "sources").mkdir()
    table = _source_table(
        module,
        overrides={
            "harnesslab-claw-code-agent": {
                "license_posture": "MIT",
                "license_evidence": "LICENSE sha256:bad",
                "use_posture": "Copy freely.",
            },
        },
    )
    (tmp_path / "ATTRIBUTIONS.md").write_text(_attributions_pointer(), encoding="utf-8")
    (tmp_path / "sources" / "README.md").write_text(table, encoding="utf-8")

    failures = module.check_source_inventory(tmp_path)

    assert any(
        failure.source == "harnesslab-claw-code-agent"
        and "license posture mismatch" in failure.reason
        for failure in failures
    )
    assert any(
        failure.source == "harnesslab-claw-code-agent"
        and "license evidence mismatch" in failure.reason
        for failure in failures
    )
    assert any(
        failure.source == "harnesslab-claw-code-agent" and "use posture mismatch" in failure.reason
        for failure in failures
    )


def test_source_inventory_detects_local_non_git_source_directory(tmp_path):
    module = _load_source_inventory_module()
    (tmp_path / "sources" / "openai-codex").mkdir(parents=True)
    table = _source_table(module)
    (tmp_path / "ATTRIBUTIONS.md").write_text(_attributions_pointer(), encoding="utf-8")
    (tmp_path / "sources" / "README.md").write_text(table, encoding="utf-8")

    failures = module.check_source_inventory(tmp_path)

    assert any(
        failure.source == "openai-codex" and "not a git clone" in failure.reason
        for failure in failures
    )


def test_source_inventory_detects_dirty_local_clone(tmp_path):
    module = _load_source_inventory_module()
    source = "openai-codex"
    source_path = tmp_path / "sources" / source
    source_path.mkdir(parents=True)
    _git(source_path, "init")
    _git(source_path, "config", "user.email", "test@example.com")
    _git(source_path, "config", "user.name", "Test User")
    _git(source_path, "remote", "add", "origin", module.EXPECTED_SOURCES[source]["url"])
    (source_path / "README.md").write_text("clean\n", encoding="utf-8")
    _git(source_path, "add", "README.md")
    _git(source_path, "commit", "-m", "seed")
    module.EXPECTED_SOURCES[source]["commit"] = _git(source_path, "rev-parse", "HEAD")
    (source_path / "README.md").write_text("dirty\n", encoding="utf-8")
    table = _source_table(module)
    (tmp_path / "ATTRIBUTIONS.md").write_text(_attributions_pointer(), encoding="utf-8")
    (tmp_path / "sources" / "README.md").write_text(table, encoding="utf-8")

    failures = module.check_source_inventory(tmp_path)

    assert any(
        failure.source == source and "uncommitted changes" in failure.reason for failure in failures
    )


def test_source_inventory_detects_local_license_evidence_drift(tmp_path):
    module = _load_source_inventory_module()
    source = "openai-codex"
    source_path = tmp_path / "sources" / source
    source_path.mkdir(parents=True)
    _git(source_path, "init")
    _git(source_path, "config", "user.email", "test@example.com")
    _git(source_path, "config", "user.name", "Test User")
    _git(source_path, "remote", "add", "origin", module.EXPECTED_SOURCES[source]["url"])
    (source_path / "LICENSE").write_text("unexpected license text\n", encoding="utf-8")
    _git(source_path, "add", "LICENSE")
    _git(source_path, "commit", "-m", "seed")
    module.EXPECTED_SOURCES[source]["commit"] = _git(source_path, "rev-parse", "HEAD")
    table = _source_table(module)
    (tmp_path / "ATTRIBUTIONS.md").write_text(_attributions_pointer(), encoding="utf-8")
    (tmp_path / "sources" / "README.md").write_text(table, encoding="utf-8")

    failures = module.check_source_inventory(tmp_path)

    assert any(
        failure.source == source and "local license evidence" in failure.reason
        for failure in failures
    )


def test_source_inventory_reports_git_failures_without_traceback(tmp_path):
    module = _load_source_inventory_module()
    source = "openai-codex"
    source_path = tmp_path / "sources" / source
    source_path.mkdir(parents=True)
    _git(source_path, "init")
    _git(source_path, "config", "user.email", "test@example.com")
    _git(source_path, "config", "user.name", "Test User")
    (source_path / "README.md").write_text("clean\n", encoding="utf-8")
    _git(source_path, "add", "README.md")
    _git(source_path, "commit", "-m", "seed")
    module.EXPECTED_SOURCES[source]["commit"] = _git(source_path, "rev-parse", "HEAD")
    table = _source_table(module)
    (tmp_path / "ATTRIBUTIONS.md").write_text(_attributions_pointer(), encoding="utf-8")
    (tmp_path / "sources" / "README.md").write_text(table, encoding="utf-8")

    failures = module.check_source_inventory(tmp_path)

    assert any(
        failure.source == source and "git remote get-url origin failed" in failure.reason
        for failure in failures
    )


def test_source_inventory_accepts_ssh_github_remote_equivalent(tmp_path):
    module = _load_source_inventory_module()
    source = "openai-codex"
    source_path = tmp_path / "sources" / source
    source_path.mkdir(parents=True)
    _git(source_path, "init")
    _git(source_path, "config", "user.email", "test@example.com")
    _git(source_path, "config", "user.name", "Test User")
    _git(source_path, "remote", "add", "origin", "git@github.com:openai/codex.git")
    (source_path / "README.md").write_text("clean\n", encoding="utf-8")
    _git(source_path, "add", "README.md")
    _git(source_path, "commit", "-m", "seed")
    module.EXPECTED_SOURCES[source]["commit"] = _git(source_path, "rev-parse", "HEAD")
    module.EXPECTED_SOURCES[source]["license_evidence"] = "none found"
    table = _source_table(module)
    (tmp_path / "ATTRIBUTIONS.md").write_text(_attributions_pointer(), encoding="utf-8")
    (tmp_path / "sources" / "README.md").write_text(table, encoding="utf-8")

    failures = module.check_source_inventory(tmp_path)

    assert not any(
        failure.source == source and "remote URL" in failure.reason for failure in failures
    )


def _source_table(
    module: ModuleType,
    *,
    overrides: dict[str, dict[str, str]] | None = None,
) -> str:
    overrides = overrides or {}
    rows = []
    for source, expected in module.EXPECTED_SOURCES.items():
        row = dict(expected)
        row.update(overrides.get(source, {}))
        rows.append(
            f"| `{source}` | `{row['url']}` | `{row['commit']}` | "
            f"{row['license_posture']} | {row['license_evidence']} | {row['use_posture']} |"
        )
    return "\n".join(
        [
            "| Source | Upstream | Local commit | Observed license posture | "
            "License evidence | Use posture |",
            "| --- | --- | --- | --- | --- | --- |",
            *rows,
        ]
    )


def _attributions_pointer() -> str:
    return (
        "# Attributions\n\n"
        "Source clone metadata lives in `sources/README.md` and is validated by "
        "`scripts/check_source_inventory.py`.\n"
    )


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _load_source_inventory_module() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "check_source_inventory.py"
    spec = importlib.util.spec_from_file_location("check_source_inventory", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
