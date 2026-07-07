"""Helpers for classifying durable evidence artifacts."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

RAW_LOG_RETENTION_BYTES = 1_048_576
KEY_EXCERPT_BYTES = 800
LARGE_LOG_WARNING_BYTES = 262_144


def raw_log_truncation_notice(*, stream_name: str) -> bytes:
    """Return the marker appended when retained raw stream output is capped."""

    return (
        "\n[codex-supervisor retained only the first "
        f"{RAW_LOG_RETENTION_BYTES} bytes of {stream_name}; "
        "read evidence digest key excerpts first and use this log only for "
        "short-term audit recovery.]\n"
    ).encode()


def primary_evidence_artifacts(artifacts: tuple[str, ...]) -> tuple[str, ...]:
    """Return artifacts that should satisfy assurance policy."""

    return tuple(artifact for artifact in artifacts if is_primary_evidence_artifact(artifact))


def is_primary_evidence_artifact(artifact: str) -> bool:
    """Return whether an artifact is primary evidence rather than audit metadata."""

    path = Path(artifact)
    if _is_supervisor_evidence_path(path):
        return False
    return not is_stream_log_artifact(path)


def is_stream_log_artifact(path: Path) -> bool:
    """Return whether a path looks like captured stdout/stderr/log output."""

    name = path.name.casefold()
    return (
        name.endswith("-stdout.txt")
        or name.endswith("-stderr.txt")
        or name.endswith("-verifier-stdout.txt")
        or name.endswith("-verifier-stderr.txt")
        or name.endswith(".log")
    )


def raw_log_artifact_entries(artifacts: tuple[str, ...]) -> list[dict[str, object]]:
    """Return compact raw log references for digest storage."""

    entries: list[dict[str, object]] = []
    for artifact in artifacts:
        path = Path(artifact)
        if not is_stream_log_artifact(path) or not path.is_file():
            continue
        entries.append(
            {
                "path": artifact,
                "bytes": path.stat().st_size,
                "retention": "short_term_audit_recovery",
                "primary_evidence": False,
            }
        )
    return entries


def log_summary_entries(artifacts: tuple[str, ...]) -> list[dict[str, object]]:
    """Return deterministic summaries for raw stream logs."""

    entries: list[dict[str, object]] = []
    for artifact in artifacts:
        path = Path(artifact)
        if not is_stream_log_artifact(path) or not path.is_file():
            continue
        entries.append(
            {
                "path": artifact,
                "stream": _stream_name(path),
                "bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
                "line_count": _line_count(path),
                "first_excerpt": head_text(path),
                "last_excerpt": tail_text(path),
                "primary_evidence": False,
            }
        )
    return entries


def key_excerpt_entries(artifacts: tuple[str, ...], *, limit: int = 4) -> list[dict[str, object]]:
    """Return small excerpts Goal Mode can read instead of raw logs."""

    excerpts: list[dict[str, object]] = []
    for artifact in artifacts:
        if len(excerpts) >= limit:
            break
        path = Path(artifact)
        if not is_stream_log_artifact(path) or not path.is_file():
            continue
        excerpts.append({"path": artifact, "excerpt": tail_text(path)})
    return excerpts


def log_warning_flags(artifacts: tuple[str, ...]) -> list[str]:
    """Return warning flags inferred from retained log artifacts."""

    warnings: list[str] = []
    for artifact in artifacts:
        path = Path(artifact)
        if not is_stream_log_artifact(path) or not path.is_file():
            continue
        size = path.stat().st_size
        lower_name = path.name.casefold()
        if size >= LARGE_LOG_WARNING_BYTES and "stderr" in lower_name:
            warnings.append(f"stderr_too_large: {artifact} ({size} bytes)")
        sample = _sample_text(path)
        if "retained only the first" in sample:
            warnings.append(f"raw_log_truncated: {artifact}")
        if (
            "in-process app-server event stream lagged" in sample
            or "dropping in-process app-server event" in sample
            or "consumer queue is full" in sample
        ):
            warnings.append(f"app_server_lag_detected: {artifact}")
        if "codex_core_plugins::manifest" in sample or "codex_core_skills::loader" in sample:
            warnings.append(f"ambient_plugin_warning_noise: {artifact}")
        if _looks_like_large_diff(sample):
            warnings.append(f"large_diff_output_detected: {artifact}")
    return warnings


def tail_text(path: Path) -> str:
    """Read a small tail excerpt from a text-ish artifact."""

    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - KEY_EXCERPT_BYTES))
        return handle.read().decode("utf-8", errors="replace")


def head_text(path: Path) -> str:
    """Read a small head excerpt from a text-ish artifact."""

    with path.open("rb") as handle:
        return handle.read(KEY_EXCERPT_BYTES).decode("utf-8", errors="replace")


def _sample_text(path: Path) -> str:
    with path.open("rb") as handle:
        return handle.read(RAW_LOG_RETENTION_BYTES + 4096).decode(
            "utf-8", errors="replace"
        )


def _looks_like_large_diff(sample: str) -> bool:
    plus = 0
    minus = 0
    for line in sample.splitlines():
        if line.startswith("+"):
            plus += 1
        elif line.startswith("-"):
            minus += 1
        if plus + minus >= 1_000:
            return True
    return False


def _is_supervisor_evidence_path(path: Path) -> bool:
    parts = {part.casefold() for part in path.parts}
    return ".codex-supervisor" in parts and "evidence" in parts


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _line_count(path: Path) -> int:
    count = 0
    saw_content = False
    last_byte = b""
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if chunk:
                saw_content = True
                last_byte = chunk[-1:]
                count += chunk.count(b"\n")
    if saw_content and last_byte != b"\n":
        count += 1
    return count


def _stream_name(path: Path) -> str:
    name = path.name.casefold()
    if "stderr" in name:
        return "stderr"
    if "stdout" in name:
        return "stdout"
    return "log"
