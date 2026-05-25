#!/usr/bin/env python3
"""Fail on public-repo hygiene leaks in candidate public files."""

from __future__ import annotations

import argparse
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from codex_supervisor.locks import PROTECTED_FILES  # noqa: E402

TEXT_SECRET_PATTERNS = (
    re.compile(r"C:[/\\]Users[/\\][^/\\\s]+", re.IGNORECASE),
    re.compile(r"/(?:home|Users)/[^/\s]+"),
    re.compile(r"\\\\Users\\\\[^\\\s]+", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"OPENAI_API_KEY\s*=", re.IGNORECASE),
    re.compile(
        r"(api[_-]?key|password|secret)\s*[:=]\s*"
        r"(?!['\"]?(?:example|placeholder|redacted|none|null|xxx|<))"
        r"['\"]?[^'\"\s#]+",
        re.IGNORECASE,
    ),
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{30,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{30,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
)

ALLOWED_SOURCE_FILES = {"sources/README.md"}
ALLOWED_DATABASE_FILES = {"plans/planning.sqlite3"}
TEXT_SKIP_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".png", ".jpg", ".jpeg"}
PLACEHOLDER_MARKER_PATTERN = re.compile(
    r"\b(?:fake|dummy|demo)\b|Fake|Dummy|Demo",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--publication-ready",
        action="store_true",
        help="Also require clean/staged public state suitable for ACP/publication.",
    )
    args = parser.parse_args(argv)

    failures = list(_check_candidate_source_files(REPO_ROOT))
    failures.extend(_check_candidate_worker_result_files(REPO_ROOT))
    failures.extend(_check_candidate_database_files(REPO_ROOT))
    failures.extend(_check_candidate_text_files(REPO_ROOT))
    failures.extend(_check_production_placeholder_markers(REPO_ROOT))
    failures.extend(_check_database_dumps(REPO_ROOT))
    if args.publication_ready:
        failures.extend(_check_publication_ready(REPO_ROOT))
    if not failures:
        print("Public repo hygiene checks passed.")
        return 0
    print("Public repo hygiene checks failed.", file=sys.stderr)
    for failure in failures:
        print(f"- {failure}", file=sys.stderr)
    return 1


def _git_output(repo_root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ("git", *args),
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=False,
    )
    return completed.stdout


def _candidate_public_files(repo_root: Path) -> tuple[str, ...]:
    output = _git_output(repo_root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    paths: list[str] = []
    for item in output.split(b"\0"):
        if not item:
            continue
        relative_path = item.decode("utf-8")
        if (repo_root / relative_path).is_file():
            paths.append(relative_path)
    return tuple(paths)


def _indexed_files(repo_root: Path) -> set[str]:
    output = _git_output(repo_root, "ls-files", "-z", "--cached")
    return {item.decode("utf-8").replace("\\", "/") for item in output.split(b"\0") if item}


def _check_candidate_source_files(repo_root: Path) -> tuple[str, ...]:
    failures: list[str] = []
    for relative_path in _candidate_public_files(repo_root):
        normalized = relative_path.replace("\\", "/")
        if normalized.startswith("sources/") and normalized not in ALLOWED_SOURCE_FILES:
            failures.append(f"unexpected public source clone file: {relative_path}")
    return tuple(failures)


def _check_candidate_worker_result_files(repo_root: Path) -> tuple[str, ...]:
    failures: list[str] = []
    for relative_path in _candidate_public_files(repo_root):
        normalized = relative_path.replace("\\", "/")
        if normalized == "worker-results" or normalized.startswith("worker-results/"):
            failures.append(
                f"worker result artifact must live only in planning SQLite: {relative_path}"
            )
    return tuple(failures)


def _check_candidate_database_files(repo_root: Path) -> tuple[str, ...]:
    failures: list[str] = []
    for relative_path in _candidate_public_files(repo_root):
        normalized = relative_path.replace("\\", "/")
        if (repo_root / relative_path).suffix.lower() in {
            ".sqlite",
            ".sqlite3",
            ".db",
        } and normalized not in ALLOWED_DATABASE_FILES:
            failures.append(f"unexpected public database file: {relative_path}")
    return tuple(failures)


def _check_candidate_text_files(repo_root: Path) -> tuple[str, ...]:
    failures: list[str] = []
    for relative_path in _candidate_public_files(repo_root):
        path = repo_root / relative_path
        if path.suffix.lower() in TEXT_SKIP_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            failures.append(f"{relative_path}: could not read public candidate: {exc}")
            continue
        except UnicodeDecodeError as exc:
            failures.append(f"{relative_path}: public text candidate is not valid UTF-8: {exc}")
            continue
        for pattern in TEXT_SECRET_PATTERNS:
            if pattern.search(text):
                failures.append(
                    f"{relative_path}: matched public hygiene pattern {pattern.pattern}"
                )
    return tuple(failures)


def _check_production_placeholder_markers(repo_root: Path) -> tuple[str, ...]:
    package_root = repo_root / "src" / "codex_supervisor"
    if not package_root.exists():
        return ()
    failures: list[str] = []
    for path in sorted(package_root.glob("*.py")):
        relative_path = path.relative_to(repo_root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            failures.append(f"{relative_path}: could not inspect production package: {exc}")
            continue
        except UnicodeDecodeError as exc:
            failures.append(f"{relative_path}: production package is not valid UTF-8: {exc}")
            continue
        if PLACEHOLDER_MARKER_PATTERN.search(text):
            failures.append(
                f"{relative_path}: production package contains release-blocking placeholder marker"
            )
    return tuple(failures)


def _check_database_dumps(repo_root: Path) -> tuple[str, ...]:
    failures: list[str] = []
    for relative_path in ALLOWED_DATABASE_FILES:
        db_path = repo_root / relative_path
        if not db_path.exists():
            continue
        db_uri = f"file:{quote(db_path.resolve().as_posix(), safe='/:')}?mode=ro"
        try:
            with sqlite3.connect(db_uri, uri=True) as connection:
                text = "\n".join(sql for sql in connection.iterdump())
        except sqlite3.Error as exc:
            failures.append(f"{relative_path}: could not inspect database dump: {exc}")
            continue
        for pattern in TEXT_SECRET_PATTERNS:
            if pattern.search(text):
                failures.append(
                    f"{relative_path}: matched public hygiene pattern {pattern.pattern}"
                )
    return tuple(failures)


def _check_publication_ready(repo_root: Path) -> tuple[str, ...]:
    failures: list[str] = []
    failures.extend(_check_no_untracked_or_unstaged_files(repo_root))
    failures.extend(_check_indexed_text_files(repo_root))
    indexed = _indexed_files(repo_root)
    failures.extend(_check_protected_files_indexed(indexed))
    failures.extend(_check_planning_artifacts_indexed(repo_root, indexed))
    return tuple(failures)


def _check_no_untracked_or_unstaged_files(repo_root: Path) -> tuple[str, ...]:
    output = _git_output(repo_root, "status", "--porcelain=v1", "--untracked-files=normal")
    failures: list[str] = []
    for raw_line in output.decode("utf-8").splitlines():
        if not raw_line:
            continue
        status = raw_line[:2]
        path = raw_line[3:]
        if status == "??":
            failures.append(f"untracked public candidate must be staged or ignored: {path}")
        elif len(status) == 2 and status[1] != " ":
            failures.append(f"unstaged change must be staged or reverted before ACP: {path}")
    return tuple(failures)


def _check_indexed_text_files(repo_root: Path) -> tuple[str, ...]:
    failures: list[str] = []
    for relative_path in sorted(_indexed_files(repo_root)):
        path = Path(relative_path)
        if path.suffix.lower() in TEXT_SKIP_SUFFIXES:
            continue
        try:
            blob = _git_output(repo_root, "show", f":{relative_path}")
        except subprocess.CalledProcessError as exc:
            failures.append(f"{relative_path}: could not read staged blob: {exc}")
            continue
        try:
            text = blob.decode("utf-8")
        except UnicodeDecodeError as exc:
            failures.append(f"{relative_path}: staged text blob is not valid UTF-8: {exc}")
            continue
        for pattern in TEXT_SECRET_PATTERNS:
            if pattern.search(text):
                failures.append(
                    f"{relative_path}: staged blob matched public hygiene pattern {pattern.pattern}"
                )
    return tuple(failures)


def _check_protected_files_indexed(indexed: set[str]) -> tuple[str, ...]:
    failures: list[str] = []
    for relative_path in PROTECTED_FILES:
        if relative_path not in indexed:
            failures.append(f"protected source-of-truth file is not tracked: {relative_path}")
    return tuple(failures)


def _check_planning_artifacts_indexed(repo_root: Path, indexed: set[str]) -> tuple[str, ...]:
    db_path = repo_root / "plans" / "planning.sqlite3"
    if not db_path.exists():
        return ()
    db_uri = f"file:{quote(db_path.resolve().as_posix(), safe='/:')}?mode=ro"
    try:
        connection = sqlite3.connect(db_uri, uri=True)
    except sqlite3.Error as exc:
        return (f"planning database could not be opened for artifact checks: {exc}",)
    try:
        try:
            artifact_ids = {
                str(row[0])
                for row in connection.execute("SELECT artifact_id FROM plan_artifact_links")
            }
            artifact_ids.update(
                str(row[0])
                for row in connection.execute(
                    """
                    SELECT linked_artifact_id
                    FROM plan_progress_events
                    WHERE linked_artifact_id IS NOT NULL
                    """
                )
            )
        except sqlite3.Error as exc:
            return (f"planning database schema could not be inspected for artifacts: {exc}",)
    finally:
        connection.close()

    failures: list[str] = []
    for artifact_id in sorted(artifact_ids):
        normalized = _normalize_artifact_path(artifact_id)
        if normalized is None:
            continue
        if _is_unsafe_repo_relative_path(normalized):
            failures.append(f"planning artifact path is not repo-local: {artifact_id}")
            continue
        path = repo_root / normalized
        if not path.exists():
            failures.append(f"planning artifact does not exist on disk: {artifact_id}")
        elif normalized not in indexed:
            failures.append(f"planning artifact is not tracked for publication: {artifact_id}")
    return tuple(failures)


def _normalize_artifact_path(artifact_id: str) -> str | None:
    value = artifact_id.split("#", 1)[0].replace("\\", "/").strip()
    if not value:
        return None
    if re.match(r"^[a-z][a-z0-9+.-]*://", value, flags=re.IGNORECASE):
        return None
    return value


def _is_unsafe_repo_relative_path(normalized_path: str) -> bool:
    path = Path(normalized_path)
    return (
        path.is_absolute() or bool(re.match(r"^[A-Za-z]:", normalized_path)) or ".." in path.parts
    )


if __name__ == "__main__":
    raise SystemExit(main())
