"""Structured evidence envelope for compact attempt transitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from codex_supervisor.evidence_artifacts import primary_evidence_artifacts
from codex_supervisor.evidence_codec import (
    encode_acceptance_results,
    encode_gaps,
    encode_next_actions,
    encode_review_evidence,
    encode_risks,
)
from codex_supervisor.policy import EvidenceBundle


@dataclass(frozen=True)
class EvidenceEnvelope:
    """Structured evidence before it is encoded into the compact JSON fields."""

    checks: tuple[str, ...] = ()
    acceptance_results: Mapping[str, bool] | None = None
    risks: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()
    next_actions: tuple[str, ...] = ()
    review_evidence: tuple[str, ...] = ()

    def storage_checks(self) -> tuple[str, ...]:
        """Encode structured evidence into the existing checks JSON array."""

        evidence_checks = list(self.checks)
        evidence_checks.extend(encode_acceptance_results(self.acceptance_results))
        evidence_checks.extend(encode_risks(self.risks))
        evidence_checks.extend(encode_gaps(self.gaps))
        evidence_checks.extend(encode_next_actions(self.next_actions))
        evidence_checks.extend(encode_review_evidence(self.review_evidence))
        return tuple(evidence_checks)

    def policy_bundle(
        self,
        *,
        task_id: str,
        attempt_id: str,
        assurance: str,
        summary: str,
        artifacts: tuple[str, ...],
    ) -> EvidenceBundle:
        """Build the policy-facing EvidenceBundle without losing structure."""

        strict_checks = self.checks if assurance == "high" else ()
        focused_checks = self.checks if assurance != "high" else ()
        policy_artifacts = primary_evidence_artifacts(artifacts)
        return EvidenceBundle(
            task_id=task_id,
            attempt_id=attempt_id,
            summary=summary,
            checks=focused_checks,
            strict_checks=strict_checks,
            artifacts=policy_artifacts,
            acceptance_results=self.acceptance_results,
            risks=self.risks,
            gaps=self.gaps,
            next_actions=self.next_actions,
            review_evidence=self.review_evidence,
        )
