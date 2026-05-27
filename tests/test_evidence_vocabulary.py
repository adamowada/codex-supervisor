from codex_supervisor import codex_state_reconciliation, release, review_persistence
from codex_supervisor.evidence_vocabulary import (
    CI_RUN_RECORDED_EVENT,
    CODEX_STATE_RECONCILIATION_APPLIED_EVENT,
    CODEX_STATE_RECONCILIATION_FINDING_EVENT,
    CODEX_STATE_SNAPSHOT_ARTIFACT_RELATIONSHIP,
    FINAL_STATE_COMMIT_RELATIONSHIP,
    FINAL_STATE_COMMIT_RELATIONSHIPS,
    ISSUE_COMMENT_ARTIFACT_RELATIONSHIP,
    ISSUE_COMMENT_COMMIT_RELATIONSHIP,
    PR_HEAD_COMMIT_RELATIONSHIP,
    PUBLICATION_READY_VERIFICATION_RECORDED_EVENT,
    REVIEW_ARTIFACT_RELATIONSHIP,
    REVIEW_RESULT_ARTIFACT_RELATIONSHIP,
    REVIEW_RESULT_RECORDED_EVENT,
    WORKER_RESULT_ARTIFACT_RELATIONSHIP,
    WORKER_RESULT_JSON_SOURCE_KIND,
    is_final_state_commit_relationship,
)
from codex_supervisor.planning import IssueCommentEvidenceRecord, PullRequestEvidenceRecord


def test_final_state_commit_relationships_include_legacy_compatibility_labels() -> None:
    assert FINAL_STATE_COMMIT_RELATIONSHIP in FINAL_STATE_COMMIT_RELATIONSHIPS
    assert is_final_state_commit_relationship("final-project-state")
    assert is_final_state_commit_relationship("completion")
    assert not is_final_state_commit_relationship("final_app_commit")


def test_evidence_modules_reexport_shared_vocabulary() -> None:
    assert release.CI_RUN_EVENT_TYPE == CI_RUN_RECORDED_EVENT
    assert release.PUBLICATION_READY_EVENT_TYPE == PUBLICATION_READY_VERIFICATION_RECORDED_EVENT
    assert review_persistence.REVIEW_RESULT_RECORDED_EVENT == REVIEW_RESULT_RECORDED_EVENT
    assert (
        review_persistence.REVIEW_RESULT_ARTIFACT_RELATIONSHIP
        == REVIEW_RESULT_ARTIFACT_RELATIONSHIP
    )
    assert review_persistence.REVIEW_ARTIFACT_RELATIONSHIP == REVIEW_ARTIFACT_RELATIONSHIP
    assert (
        codex_state_reconciliation.CODEX_STATE_SNAPSHOT_RELATIONSHIP
        == CODEX_STATE_SNAPSHOT_ARTIFACT_RELATIONSHIP
    )
    assert codex_state_reconciliation.CODEX_STATE_APPLIED_EVENT == (
        CODEX_STATE_RECONCILIATION_APPLIED_EVENT
    )
    assert codex_state_reconciliation.CODEX_STATE_FINDING_EVENT == (
        CODEX_STATE_RECONCILIATION_FINDING_EVENT
    )


def test_planning_record_defaults_use_shared_relationship_vocabulary() -> None:
    assert (
        PullRequestEvidenceRecord(
            plan_id="plan",
            progress_id="progress",
            provider="github",
            repository="owner/repo",
            pr_number=1,
            pr_url="https://github.com/owner/repo/pull/1",
            state="open",
            head_sha="a" * 40,
        ).commit_relationship
        == PR_HEAD_COMMIT_RELATIONSHIP
    )
    issue_comment = IssueCommentEvidenceRecord(
        plan_id="plan",
        progress_id="progress",
        provider="github",
        repository="owner/repo",
        issue_number=1,
        comment_id="comment-1",
        comment_url="https://github.com/owner/repo/issues/1#issuecomment-1",
    )
    assert issue_comment.artifact_relationship == ISSUE_COMMENT_ARTIFACT_RELATIONSHIP
    assert issue_comment.commit_relationship == ISSUE_COMMENT_COMMIT_RELATIONSHIP


def test_worker_result_vocabulary_names_db_backed_result_artifacts() -> None:
    assert WORKER_RESULT_ARTIFACT_RELATIONSHIP == "worker-result"
    assert WORKER_RESULT_JSON_SOURCE_KIND == "worker-result-json"
