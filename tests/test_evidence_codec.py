from __future__ import annotations

from codex_supervisor.evidence_codec import (
    GIT_CHANGED_PRODUCT_PATH_PREFIX,
    LAUNCH_PACKET_SHA256_CHECK_PREFIX,
    MISSING_ARTIFACT_CHECK_PREFIX,
    TELEMETRY_WARNING_CHECK_PREFIX,
    VERIFIER_SKIPPED_CHECK_PREFIX,
    check_suffix,
    check_suffixes,
    encode_acceptance_results,
    encode_gaps,
    encode_next_actions,
    encode_review_evidence,
    encode_risks,
    warning_checks,
)


def test_evidence_codec_encodes_structured_checks() -> None:
    assert encode_acceptance_results({"Criterion B": False, "Criterion A": True}) == (
        "acceptance: Criterion A = pass",
        "acceptance: Criterion B = fail",
    )
    assert encode_risks(("Risk noted",)) == ("risk: Risk noted",)
    assert encode_gaps(("Gap noted",)) == ("gap: Gap noted",)
    assert encode_next_actions(("Next action",)) == ("next-action: Next action",)
    assert encode_review_evidence(("Review note",)) == ("review: Review note",)


def test_evidence_codec_parses_check_suffixes_and_warnings() -> None:
    checks = (
        f"{LAUNCH_PACKET_SHA256_CHECK_PREFIX}abc123",
        f"{GIT_CHANGED_PRODUCT_PATH_PREFIX}README.md",
        f"{GIT_CHANGED_PRODUCT_PATH_PREFIX}src/app.py",
        f"{MISSING_ARTIFACT_CHECK_PREFIX}report.txt",
        f"{VERIFIER_SKIPPED_CHECK_PREFIX}worker exit code was 1",
        f"{TELEMETRY_WARNING_CHECK_PREFIX}could not write optional metadata",
    )

    assert check_suffix(checks, LAUNCH_PACKET_SHA256_CHECK_PREFIX) == "abc123"
    assert check_suffixes(checks, GIT_CHANGED_PRODUCT_PATH_PREFIX) == (
        "README.md",
        "src/app.py",
    )
    assert warning_checks(checks) == (
        "missing artifact: report.txt",
        "verifier skipped: worker exit code was 1",
        "telemetry warning: could not write optional metadata",
    )
