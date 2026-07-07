"""Structured evidence envelope for compact attempt transitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

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
        for criterion, passed in sorted((self.acceptance_results or {}).items()):
            evidence_checks.append(f"acceptance: {criterion} = {'pass' if passed else 'fail'}")
        evidence_checks.extend(f"risk: {risk}" for risk in self.risks)
        evidence_checks.extend(f"gap: {gap}" for gap in self.gaps)
        evidence_checks.extend(f"next-action: {action}" for action in self.next_actions)
        evidence_checks.extend(f"review: {review}" for review in self.review_evidence)
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
        return EvidenceBundle(
            task_id=task_id,
            attempt_id=attempt_id,
            summary=summary,
            checks=focused_checks,
            strict_checks=strict_checks,
            artifacts=artifacts,
            acceptance_results=self.acceptance_results,
            risks=self.risks,
            gaps=self.gaps,
            next_actions=self.next_actions,
            review_evidence=self.review_evidence,
        )
