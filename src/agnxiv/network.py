from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .models import Verdict


class AttemptStatus(StrEnum):
    READY_TO_VERIFY = "READY_TO_VERIFY"
    REPRODUCED = "REPRODUCED"
    PARTIALLY_REPRODUCED = "PARTIALLY_REPRODUCED"
    RESULT_DIVERGENCE = "RESULT_DIVERGENCE"
    EVIDENCE_INCOMPLETE = "EVIDENCE_INCOMPLETE"
    EXECUTION_BLOCKED = "EXECUTION_BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"


class ChallengeStatus(StrEnum):
    OPEN = "OPEN"
    AUTHOR_RESPONDED = "AUTHOR_RESPONDED"
    RESOLVED = "RESOLVED"
    DIVERGENCE_CONFIRMED = "DIVERGENCE_CONFIRMED"
    CLOSED_INCONCLUSIVE = "CLOSED_INCONCLUSIVE"


class EvidenceAttempt(BaseModel):
    """One durable attempt to test or prepare a scientific claim."""

    schema_version: str = "agnxiv.attempt/1"
    attempt_id: str
    paper_id: str | None = None
    claim_id: str | None = None
    claim_text: str | None = None
    repository: str
    repository_ref: str
    pinned_commit: str | None = None
    expected: float | None = None
    observed: float | None = None
    verdict: Verdict | None = None
    status: AttemptStatus
    automation_score: float | None = Field(default=None, ge=0.0, le=1.0)
    blockers: list[str] = Field(default_factory=list)
    execution_record_url: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuthorResponse(BaseModel):
    text: str
    evidence_url: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ScientificChallenge(BaseModel):
    """Evidence-specific challenge to one claim or reproduction attempt."""

    schema_version: str = "agnxiv.challenge/1"
    challenge_id: str
    paper_id: str | None = None
    claim_id: str | None = None
    claim_text: str | None = None
    attempt_id: str
    target_reported_result: str | None = None
    challenger_repository: str
    challenger_ref: str
    challenger_observed_result: str
    status: ChallengeStatus = ChallengeStatus.OPEN
    rationale: str
    challenger_evidence_url: str | None = None
    author_responses: list[AuthorResponse] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RecordSummary(BaseModel):
    paper_id: str
    attempts: int
    reproduced: int
    divergences: int
    partial: int
    unresolved: int
    open_challenges: int
    current_state: str


class ScientificRecord(BaseModel):
    """Living evidence state for one paper/preprint."""

    schema_version: str = "agnxiv.record/1"
    paper_id: str
    title: str | None = None
    attempts: list[EvidenceAttempt] = Field(default_factory=list)
    challenges: list[ScientificChallenge] = Field(default_factory=list)

    def summary(self) -> RecordSummary:
        reproduced = sum(a.status == AttemptStatus.REPRODUCED for a in self.attempts)
        divergences = sum(a.status == AttemptStatus.RESULT_DIVERGENCE for a in self.attempts)
        partial = sum(
            a.status == AttemptStatus.PARTIALLY_REPRODUCED for a in self.attempts
        )
        unresolved = len(self.attempts) - reproduced - divergences - partial
        open_challenges = sum(
            c.status in {ChallengeStatus.OPEN, ChallengeStatus.AUTHOR_RESPONDED}
            for c in self.challenges
        )

        if divergences and reproduced:
            state = "MIXED_EVIDENCE"
        elif divergences:
            state = "RESULT_DIVERGENCE"
        elif reproduced:
            state = "REPRODUCED"
        elif self.attempts:
            state = "UNRESOLVED"
        else:
            state = "UNTESTED"

        return RecordSummary(
            paper_id=self.paper_id,
            attempts=len(self.attempts),
            reproduced=reproduced,
            divergences=divergences,
            partial=partial,
            unresolved=unresolved,
            open_challenges=open_challenges,
            current_state=state,
        )


def attempt_from_github_payload(
    payload: dict[str, Any],
    *,
    attempt_id: str,
    execution_record_url: str | None = None,
) -> EvidenceAttempt:
    """Normalize an existing GitHub verification payload into a durable Attempt."""

    request = payload.get("request") or {}
    result = payload.get("result") or {}
    status = payload.get("status")
    error = payload.get("error")

    paper_id = request.get("arxiv_id")
    repository = str(request.get("repository") or "unknown")
    repository_ref = str(request.get("repository_ref") or "unknown")

    if error or status == "failed":
        return EvidenceAttempt(
            attempt_id=attempt_id,
            paper_id=paper_id,
            repository=repository,
            repository_ref=repository_ref,
            status=AttemptStatus.EXECUTION_BLOCKED,
            blockers=[str(error or "verification job failed")],
            execution_record_url=execution_record_url,
        )

    kind = result.get("kind")
    if kind == "auto_plan":
        plan = result.get("plan") or {}
        blockers = [str(item) for item in (plan.get("blockers") or [])]
        safe = bool(plan.get("safe_to_execute"))
        score = float(plan.get("automation_score") or 0.0)
        return EvidenceAttempt(
            attempt_id=attempt_id,
            paper_id=paper_id,
            repository=repository,
            repository_ref=repository_ref,
            pinned_commit=result.get("repository_commit"),
            status=(
                AttemptStatus.READY_TO_VERIFY
                if safe
                else AttemptStatus.EVIDENCE_INCOMPLETE
            ),
            automation_score=score,
            blockers=blockers,
            execution_record_url=execution_record_url,
        )

    if kind == "verification":
        bundle = result.get("bundle") or {}
        record = bundle.get("record") or {}
        claim = bundle.get("claim") or {}
        git = (bundle.get("provenance") or {}).get("git") or {}
        raw_verdict = record.get("verdict")
        verdict = Verdict(raw_verdict) if raw_verdict in set(Verdict) else None

        mapped = {
            Verdict.VERIFIED: AttemptStatus.REPRODUCED,
            Verdict.PARTIALLY_VERIFIED: AttemptStatus.PARTIALLY_REPRODUCED,
            Verdict.CONTRADICTED: AttemptStatus.RESULT_DIVERGENCE,
            Verdict.UNABLE_TO_VERIFY: AttemptStatus.INCONCLUSIVE,
        }.get(verdict, AttemptStatus.INCONCLUSIVE)

        return EvidenceAttempt(
            attempt_id=attempt_id,
            paper_id=paper_id,
            claim_id=claim.get("id"),
            claim_text=claim.get("text"),
            repository=repository,
            repository_ref=repository_ref,
            pinned_commit=git.get("commit"),
            expected=record.get("expected"),
            observed=record.get("observed_mean"),
            verdict=verdict,
            status=mapped,
            execution_record_url=execution_record_url,
        )

    return EvidenceAttempt(
        attempt_id=attempt_id,
        paper_id=paper_id,
        repository=repository,
        repository_ref=repository_ref,
        status=AttemptStatus.INCONCLUSIVE,
        blockers=["unknown worker result kind"],
        execution_record_url=execution_record_url,
    )
