"""Encoding helpers for compact evidence check strings."""

from __future__ import annotations

from collections.abc import Mapping

ACCEPTANCE_CHECK_PREFIX = "acceptance: "
RISK_CHECK_PREFIX = "risk: "
GAP_CHECK_PREFIX = "gap: "
NEXT_ACTION_CHECK_PREFIX = "next-action: "
REVIEW_CHECK_PREFIX = "review: "

PROCESS_EXIT_CHECK_PREFIX = "process exit code: "
VERIFIER_EXIT_CHECK_PREFIX = "verifier exit code: "
VERIFIER_SKIPPED_CHECK_PREFIX = "verifier skipped: "
GIT_CHANGED_PRODUCT_PATH_PREFIX = "git changed product path: "
MISSING_ARTIFACT_CHECK_PREFIX = "missing artifact: "
TELEMETRY_WARNING_CHECK_PREFIX = "telemetry warning: "
WARNING_CHECK_PREFIX = "warning: "
LAUNCH_PACKET_SHA256_CHECK_PREFIX = "launch packet sha256: "
VERIFIER_INTENT_SHA256_CHECK_PREFIX = "verifier intent sha256: "

PRODUCT_SHA_CHECK_PREFIX = "product artifact sha256: "
PRODUCT_DELETED_CHECK_PREFIX = "product artifact deleted: "


def encode_acceptance_results(results: Mapping[str, bool] | None) -> tuple[str, ...]:
    """Encode criterion acceptance results for compact checks storage."""

    if not results:
        return ()
    return tuple(
        f"{ACCEPTANCE_CHECK_PREFIX}{criterion} = {'pass' if passed else 'fail'}"
        for criterion, passed in sorted(results.items())
    )


def encode_risks(risks: tuple[str, ...]) -> tuple[str, ...]:
    """Encode risk notes for compact checks storage."""

    return _prefixed(RISK_CHECK_PREFIX, risks)


def encode_gaps(gaps: tuple[str, ...]) -> tuple[str, ...]:
    """Encode gap notes for compact checks storage."""

    return _prefixed(GAP_CHECK_PREFIX, gaps)


def encode_next_actions(next_actions: tuple[str, ...]) -> tuple[str, ...]:
    """Encode next-action notes for compact checks storage."""

    return _prefixed(NEXT_ACTION_CHECK_PREFIX, next_actions)


def encode_review_evidence(review_evidence: tuple[str, ...]) -> tuple[str, ...]:
    """Encode review evidence notes for compact checks storage."""

    return _prefixed(REVIEW_CHECK_PREFIX, review_evidence)


def check_suffix(checks: tuple[str, ...], prefix: str) -> str | None:
    """Return the first non-empty suffix for a compact evidence check prefix."""

    for check in checks:
        if not check.startswith(prefix):
            continue
        suffix = check.removeprefix(prefix).strip()
        return suffix or None
    return None


def check_suffixes(checks: tuple[str, ...], prefix: str) -> tuple[str, ...]:
    """Return all suffixes for a compact evidence check prefix."""

    return tuple(
        check.removeprefix(prefix).strip()
        for check in checks
        if check.startswith(prefix)
    )


def has_check_prefix(checks: tuple[str, ...], prefix: str) -> bool:
    """Return whether any compact evidence check has the given prefix."""

    return any(check.startswith(prefix) for check in checks)


def warning_checks(checks: tuple[str, ...]) -> tuple[str, ...]:
    """Return compact checks that should be treated as recovery warnings."""

    return tuple(
        check
        for check in checks
        if (
            check.startswith(TELEMETRY_WARNING_CHECK_PREFIX)
            or check.startswith(MISSING_ARTIFACT_CHECK_PREFIX)
            or check.startswith(VERIFIER_SKIPPED_CHECK_PREFIX)
            or check.startswith(WARNING_CHECK_PREFIX)
        )
    )


def _prefixed(prefix: str, values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(f"{prefix}{value}" for value in values)
