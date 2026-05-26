"""Worktree and run-artifact path guards."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
DRIVE_PATH_PATTERN = re.compile(r"^[A-Za-z]:")
URI_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
IGNORED_RUNTIME_ROOTS = frozenset({"artifacts", "logs", "runs", "worktrees"})


class WorktreeArtifactError(ValueError):
    """Raised when a worktree or artifact path is unsafe."""


@dataclass(frozen=True)
class WorktreeRunLayout:
    """Deterministic repo-relative paths for one worker run."""

    task_id: str
    worker_run_id: str
    worktree_path: str
    run_directory: str
    artifact_directory: str
    prompt_path: str
    jsonl_path: str
    stdout_path: str
    stderr_path: str
    final_message_path: str
    diff_summary_path: str
    raw_result_path: str
    evidence_manifest_path: str

    def raw_evidence_paths(self) -> dict[str, str]:
        """Return raw local evidence paths for worker-run metadata."""

        return {
            "worktree": self.worktree_path,
            "run_directory": self.run_directory,
            "artifact_directory": self.artifact_directory,
            "prompt": self.prompt_path,
            "jsonl": self.jsonl_path,
            "stdout": self.stdout_path,
            "stderr": self.stderr_path,
            "final_message": self.final_message_path,
            "diff_summary": self.diff_summary_path,
            "raw_result": self.raw_result_path,
            "evidence_manifest": self.evidence_manifest_path,
        }


@dataclass(frozen=True)
class ChangedPathViolation:
    """One changed path that cannot be accepted for a task contract."""

    path: str
    reason: str


def build_worktree_run_layout(task_id: str, worker_run_id: str) -> WorktreeRunLayout:
    """Build deterministic ignored-run paths for one worker attempt."""

    safe_task_id = _safe_identifier(task_id, "task_id")
    safe_worker_run_id = _safe_identifier(worker_run_id, "worker_run_id")
    run_directory = f"runs/{safe_worker_run_id}"
    artifact_directory = f"artifacts/{safe_worker_run_id}"
    return WorktreeRunLayout(
        task_id=safe_task_id,
        worker_run_id=safe_worker_run_id,
        worktree_path=f"worktrees/{safe_worker_run_id}",
        run_directory=run_directory,
        artifact_directory=artifact_directory,
        prompt_path=f"{run_directory}/prompt.md",
        jsonl_path=f"{run_directory}/events.jsonl",
        stdout_path=f"{run_directory}/stdout.txt",
        stderr_path=f"{run_directory}/stderr.txt",
        final_message_path=f"{run_directory}/final-message.txt",
        diff_summary_path=f"{run_directory}/diff-summary.txt",
        raw_result_path=f"{artifact_directory}/worker-result.raw.json",
        evidence_manifest_path=f"{artifact_directory}/evidence-manifest.json",
    )


def validate_cleanup_target(workspace_root: Path, target_path: Path | str) -> Path:
    """Return a resolved cleanup target only when it stays inside the workspace root."""

    if str(workspace_root).strip() == "":
        msg = "workspace_root is required"
        raise WorktreeArtifactError(msg)
    root = workspace_root.resolve()
    if not root.exists() or not root.is_dir():
        msg = f"workspace_root does not exist or is not a directory: {workspace_root}"
        raise WorktreeArtifactError(msg)
    target_input = Path(target_path)
    candidate = target_input if target_input.is_absolute() else root / target_input
    target = candidate.resolve(strict=False)
    if target == root:
        msg = "cleanup target must not be the workspace root"
        raise WorktreeArtifactError(msg)
    try:
        target.relative_to(root)
    except ValueError as exc:
        msg = f"cleanup target is outside workspace root: {target_path}"
        raise WorktreeArtifactError(msg) from exc
    return target


def validate_changed_files(
    changed_files: tuple[str, ...],
    allowed_paths: tuple[str, ...],
) -> tuple[ChangedPathViolation, ...]:
    """Report unsafe or out-of-scope changed files without touching the filesystem."""

    allowed_patterns: list[str] = []
    violations: list[ChangedPathViolation] = []
    for allowed_path in allowed_paths:
        normalized_allowed, reason = _normalize_repo_relative_path(allowed_path)
        if reason is None:
            allowed_patterns.append(normalized_allowed)
        else:
            violations.append(ChangedPathViolation(allowed_path, f"unsafe_allowed_path:{reason}"))
    for changed_file in changed_files:
        normalized_changed, reason = _normalize_repo_relative_path(changed_file)
        if reason is not None:
            violations.append(ChangedPathViolation(changed_file, f"unsafe_changed_file:{reason}"))
            continue
        if not any(
            _matches_allowed_path(normalized_changed, allowed) for allowed in allowed_patterns
        ):
            violations.append(ChangedPathViolation(normalized_changed, "outside_allowed_paths"))
    return tuple(violations)


def is_ignored_runtime_path(path: str) -> bool:
    """Return whether a repo-relative path belongs to ignored runtime output."""

    normalized, reason = _normalize_repo_relative_path(path)
    if reason is not None:
        return False
    return normalized.split("/", 1)[0] in IGNORED_RUNTIME_ROOTS


def _safe_identifier(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        msg = f"{field_name} is required"
        raise WorktreeArtifactError(msg)
    if ".." in normalized or not IDENTIFIER_PATTERN.fullmatch(normalized):
        msg = f"{field_name} is not a safe path segment: {value}"
        raise WorktreeArtifactError(msg)
    return normalized


def _normalize_repo_relative_path(value: str) -> tuple[str, str | None]:
    normalized = value.strip().replace("\\", "/")
    if not normalized:
        return normalized, "empty"
    if URI_PATTERN.match(normalized):
        return normalized, "uri"
    if DRIVE_PATH_PATTERN.match(normalized):
        return normalized, "drive_path"
    if normalized.startswith("/"):
        return normalized, "absolute"
    if ":" in normalized:
        return normalized, "colon"
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return normalized, "non_normalized_or_parent"
    return normalized, None


def _matches_allowed_path(path: str, allowed: str) -> bool:
    if allowed.endswith("/**"):
        prefix = allowed[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return path == allowed or fnmatch.fnmatchcase(path, allowed)
