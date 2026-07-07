"""Compact evidence digests for Goal Mode recovery."""

from __future__ import annotations

import json
from pathlib import Path

from codex_supervisor.evidence_artifacts import (
    is_stream_log_artifact,
    key_excerpt_entries,
    log_summary_entries,
    log_warning_flags,
    primary_evidence_artifacts,
    raw_log_artifact_entries,
    tail_text,
)

DIGEST_CHECK_PREFIX = "evidence digest: "
_MAX_LOG_TAILS = 4


def build_evidence_digest(
    *,
    summary: str,
    checks: tuple[str, ...],
    artifacts: tuple[str, ...],
    risks: tuple[str, ...],
    gaps: tuple[str, ...],
    next_actions: tuple[str, ...],
    review_evidence: tuple[str, ...],
    acceptance_rationale: str,
    acceptance_evaluation: dict[str, object],
) -> dict[str, object]:
    """Build a compact digest without replacing raw artifact references."""

    return {
        "summary": summary,
        "process_exit_code": _first_check_suffix(checks, "process exit code: "),
        "verifier_exit_code": _first_check_suffix(checks, "verifier exit code: "),
        "changed_files": _check_suffixes(checks, "git changed product path: "),
        "product_state": _product_state(checks),
        "warnings": _unique_strings((*_warnings(checks), *log_warning_flags(artifacts))),
        "artifact_count": len(artifacts),
        "artifacts": list(artifacts),
        "primary_artifacts": list(primary_evidence_artifacts(artifacts)),
        "raw_log_artifacts": raw_log_artifact_entries(artifacts),
        "log_summaries": log_summary_entries(artifacts),
        "log_sizes": _log_sizes(artifacts),
        "key_excerpts": key_excerpt_entries(artifacts, limit=_MAX_LOG_TAILS),
        "important_tails": _important_tails(artifacts),
        "risks": list(risks),
        "gaps": list(gaps),
        "next_actions": list(next_actions),
        "review_evidence": list(review_evidence),
        "acceptance": {
            "accepted": bool(acceptance_evaluation.get("accepted")),
            "rationale": acceptance_rationale,
            "missing_requirements": list(
                _string_list(acceptance_evaluation.get("missing_requirements"))
            ),
            "failed_acceptance_criteria": list(
                _string_list(acceptance_evaluation.get("failed_acceptance_criteria"))
            ),
        },
        "raw_artifacts_preserved": True,
    }


def encode_evidence_digest(digest: dict[str, object]) -> str:
    """Encode a digest as one checks_json string."""

    return DIGEST_CHECK_PREFIX + json.dumps(digest, sort_keys=True, separators=(",", ":"))


def parse_evidence_digest(checks: tuple[str, ...]) -> dict[str, object] | None:
    """Read the latest digest from stored checks."""

    for check in reversed(checks):
        if not check.startswith(DIGEST_CHECK_PREFIX):
            continue
        try:
            decoded = json.loads(check.removeprefix(DIGEST_CHECK_PREFIX))
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, dict) else None
    return None


def _first_check_suffix(checks: tuple[str, ...], prefix: str) -> str | None:
    values = _check_suffixes(checks, prefix)
    return values[0] if values else None


def _check_suffixes(checks: tuple[str, ...], prefix: str) -> list[str]:
    return [check.removeprefix(prefix).strip() for check in checks if check.startswith(prefix)]


def _warnings(checks: tuple[str, ...]) -> list[str]:
    warnings: list[str] = []
    for check in checks:
        if (
            check.startswith("telemetry warning: ")
            or check.startswith("missing artifact: ")
            or check.startswith("verifier skipped: ")
            or check.startswith("warning: ")
        ):
            warnings.append(check)
    return warnings


def _product_state(checks: tuple[str, ...]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for check in checks:
        if check.startswith("product artifact sha256: "):
            payload = _json_object(check.removeprefix("product artifact sha256: "))
            path = payload.get("path")
            digest = payload.get("sha256")
            if isinstance(path, str) and isinstance(digest, str):
                entries.append({"path": path, "sha256": digest, "state": "present"})
        elif check.startswith("product artifact deleted: "):
            payload = _json_object(check.removeprefix("product artifact deleted: "))
            path = payload.get("path")
            if isinstance(path, str):
                entries.append({"path": path, "state": "deleted"})
    return entries


def _json_object(raw_json: str) -> dict[str, object]:
    try:
        value = json.loads(raw_json)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _log_sizes(artifacts: tuple[str, ...]) -> list[dict[str, object]]:
    sizes: list[dict[str, object]] = []
    for artifact in artifacts:
        path = Path(artifact)
        if not is_stream_log_artifact(path) or not path.is_file():
            continue
        sizes.append({"path": artifact, "bytes": path.stat().st_size})
    return sizes


def _important_tails(artifacts: tuple[str, ...]) -> list[dict[str, object]]:
    tails: list[dict[str, object]] = []
    for artifact in artifacts:
        if len(tails) >= _MAX_LOG_TAILS:
            break
        path = Path(artifact)
        if not is_stream_log_artifact(path) or not path.is_file():
            continue
        tails.append({"path": artifact, "tail": tail_text(path)})
    return tails


def _string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _unique_strings(items: tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique
