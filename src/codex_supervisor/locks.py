"""Source-of-truth document lock helpers."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

PROTECTED_FILES = (
    ".gitignore",
    ".gitattributes",
    "README.md",
    "AGENTS.md",
    "PLANS.md",
    "ARCHITECTURE.md",
    "CONTRACTS.md",
    "ROADMAP.md",
    "SOP.md",
    "TESTING.md",
    "DECISIONS.md",
    "LICENSE",
)


@dataclass(frozen=True)
class LockFailure:
    """A single protected-file lock failure."""

    relative_path: str
    expected_hash: str
    actual_hash: str | None
    reason: str


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest for a file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_protected_files(
    repo_root: Path,
    expected_hashes: dict[str, str],
) -> tuple[LockFailure, ...]:
    """Compare protected files with expected SHA-256 hashes."""

    failures: list[LockFailure] = []
    for relative_path, expected_hash in expected_hashes.items():
        path = repo_root / relative_path
        if not path.exists():
            failures.append(
                LockFailure(
                    relative_path=relative_path,
                    expected_hash=expected_hash,
                    actual_hash=None,
                    reason="missing",
                )
            )
            continue

        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            failures.append(
                LockFailure(
                    relative_path=relative_path,
                    expected_hash=expected_hash,
                    actual_hash=actual_hash,
                    reason="changed",
                )
            )
    return tuple(failures)


def untracked_protected_files(
    repo_root: Path,
    protected_files: tuple[str, ...] = PROTECTED_FILES,
) -> tuple[str, ...]:
    """Return protected files that are present locally but absent from the git index."""

    completed = subprocess.run(
        ("git", "ls-files", "-z", "--", *protected_files),
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=False,
    )
    tracked = {
        item.decode("utf-8").replace("\\", "/") for item in completed.stdout.split(b"\0") if item
    }
    return tuple(relative_path for relative_path in protected_files if relative_path not in tracked)
