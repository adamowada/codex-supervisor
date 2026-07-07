"""Compact evidence digests for Goal Mode recovery."""

from __future__ import annotations

import json
from pathlib import Path

DIGEST_CHECK_PREFIX = "evidence digest: "
_TAIL_BYTES = 800
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
        "warnings": _warnings(checks),
        "artifact_count": len(artifacts),
        "artifacts": list(artifacts),
        "log_sizes": _log_sizes(artifacts),
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


def _log_sizes(artifacts: tuple[str, ...]) -> list[dict[str, object]]:
    sizes: list[dict[str, object]] = []
    for artifact in artifacts:
        path = Path(artifact)
        if not _is_log_artifact(path) or not path.is_file():
            continue
        sizes.append({"path": artifact, "bytes": path.stat().st_size})
    return sizes


def _important_tails(artifacts: tuple[str, ...]) -> list[dict[str, object]]:
    tails: list[dict[str, object]] = []
    for artifact in artifacts:
        if len(tails) >= _MAX_LOG_TAILS:
            break
        path = Path(artifact)
        if not _is_log_artifact(path) or not path.is_file():
            continue
        tails.append({"path": artifact, "tail": _tail_text(path)})
    return tails


def _tail_text(path: Path) -> str:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - _TAIL_BYTES))
        return handle.read().decode("utf-8", errors="replace")


def _is_log_artifact(path: Path) -> bool:
    name = path.name.casefold()
    return (
        "stdout" in name
        or "stderr" in name
        or "log" in name
        or path.suffix.casefold() == ".log"
    )


def _string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))
