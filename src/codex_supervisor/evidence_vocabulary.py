"""Shared planning evidence labels for progress, artifact, and commit links."""

from __future__ import annotations

CI_RUN_RECORDED_EVENT = "ci_run_recorded"
PULL_REQUEST_RECORDED_EVENT = "pull_request_recorded"
ISSUE_COMMENT_RECORDED_EVENT = "issue_comment_recorded"
PUBLICATION_READY_VERIFICATION_RECORDED_EVENT = "publication_ready_verification_recorded"

REVIEW_ENFORCEMENT_ENABLED_EVENT = "review_enforcement_enabled"
REVIEW_RESULT_RECORDED_EVENT = "review_result_recorded"
PROMOTION_COMPLETED_EVENT = "promotion_completed"
WORKER_RESULT_REVIEW_PROMOTED_EVENT = "worker_result_review_promoted"

BROWSER_SMOKE_PASSED_EVENT = "browser_smoke_passed"
BROWSER_SMOKE_FAILED_EVENT = "browser_smoke_failed"

CODEX_STATE_RECONCILIATION_APPLIED_EVENT = "codex_state_reconciliation_applied"
CODEX_STATE_RECONCILIATION_FINDING_EVENT = "codex_state_reconciliation_finding"

FINAL_PROJECT_STATE_COMMIT_RELATIONSHIP = "final-project-state"
FINAL_STATE_COMMIT_RELATIONSHIP = "final-state"
COMPLETION_COMMIT_RELATIONSHIP = "completion"
FINAL_STATE_COMMIT_RELATIONSHIPS = (
    FINAL_PROJECT_STATE_COMMIT_RELATIONSHIP,
    FINAL_STATE_COMMIT_RELATIONSHIP,
    COMPLETION_COMMIT_RELATIONSHIP,
)

PR_HEAD_COMMIT_RELATIONSHIP = "pr-head"
ISSUE_COMMENT_COMMIT_RELATIONSHIP = "issue-comment-commit"

WORKER_RESULT_ARTIFACT_RELATIONSHIP = "worker-result"
WORKER_RESULT_NORMALIZED_ARTIFACT_RELATIONSHIP = "worker-result-normalized"
WORKER_EVIDENCE_MANIFEST_ARTIFACT_RELATIONSHIP = "worker-evidence-manifest"
WORKER_RESULT_JSON_SOURCE_KIND = "worker-result-json"
REVIEW_RESULT_ARTIFACT_RELATIONSHIP = "review-result"
REVIEW_ARTIFACT_RELATIONSHIP = "review-artifact"
CODEX_STATE_SNAPSHOT_ARTIFACT_RELATIONSHIP = "codex-state-snapshot"
ISSUE_COMMENT_ARTIFACT_RELATIONSHIP = "issue-comment"


def is_final_state_commit_relationship(value: str) -> bool:
    """Return whether a commit-link relationship denotes final project state."""

    return value in FINAL_STATE_COMMIT_RELATIONSHIPS
