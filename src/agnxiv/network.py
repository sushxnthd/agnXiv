from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, Field

from .models import Verdict


class EvidenceGrade(StrEnum):
    STRONG = "STRONG"
    CONDITIONAL = "CONDITIONAL"
    INCONCLUSIVE = "INCONCLUSIVE"


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
    dependency_precision: str | None = None
    observation_method: str | None = None
    evidence_grade: EvidenceGrade = EvidenceGrade.INCONCLUSIVE
    independence_key: str | None = None
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


class ClaimEvidenceSummary(BaseModel):
    claim_key: str
    attempts: int
    independent_clusters: int
    strong_reproduced_clusters: int
    strong_divergent_clusters: int
    conditional_reproduced_clusters: int
    conditional_divergent_clusters: int
    conflicting_clusters: int
    current_state: str


class RecordSummary(BaseModel):
    paper_id: str
    attempts: int
    reproduced: int
    divergences: int
    partial: int
    unresolved: int
    open_challenges: int
    current_state: str
    claim_states: list[ClaimEvidenceSummary] = Field(default_factory=list)


def _claim_key(attempt: EvidenceAttempt) -> str:
    return attempt.claim_id or attempt.claim_text or "__paper_level__"


def _cluster_key(attempt: EvidenceAttempt) -> str:
    return (
        attempt.independence_key
        or f"{attempt.repository}@{attempt.pinned_commit or attempt.repository_ref}"
    )


def aggregate_claim_evidence(
    attempts: list[EvidenceAttempt],
) -> list[ClaimEvidenceSummary]:
    """Aggregate by independent evidence cluster instead of naive attempt votes."""
    grouped: dict[str, list[EvidenceAttempt]] = {}
    for attempt in attempts:
        grouped.setdefault(_claim_key(attempt), []).append(attempt)

    summaries: list[ClaimEvidenceSummary] = []
    for claim_key, claim_attempts in sorted(grouped.items()):
        clusters: dict[str, list[EvidenceAttempt]] = {}
        for attempt in claim_attempts:
            clusters.setdefault(_cluster_key(attempt), []).append(attempt)

        strong_reproduced = 0
        strong_divergent = 0
        conditional_reproduced = 0
        conditional_divergent = 0
        conflicts = 0

        for cluster_attempts in clusters.values():
            decided = {
                attempt.status
                for attempt in cluster_attempts
                if attempt.status
                in {AttemptStatus.REPRODUCED, AttemptStatus.RESULT_DIVERGENCE}
            }
            if len(decided) > 1:
                conflicts += 1
                continue

            status = next(iter(decided), None)
            if status is None:
                continue
            strongest = (
                EvidenceGrade.STRONG
                if any(a.evidence_grade == EvidenceGrade.STRONG for a in cluster_attempts)
                else EvidenceGrade.CONDITIONAL
            )
            if strongest == EvidenceGrade.STRONG:
                if status == AttemptStatus.REPRODUCED:
                    strong_reproduced += 1
                else:
                    strong_divergent += 1
            elif status == AttemptStatus.REPRODUCED:
                conditional_reproduced += 1
            else:
                conditional_divergent += 1

        if strong_reproduced and strong_divergent:
            state = "MIXED_EVIDENCE"
        elif strong_divergent:
            state = "RESULT_DIVERGENCE"
        elif strong_reproduced:
            state = "REPRODUCED"
        elif conditional_reproduced or conditional_divergent:
            state = "CONDITIONAL_EVIDENCE"
        elif conflicts:
            state = "CLUSTER_CONFLICT"
        else:
            state = "UNRESOLVED"

        summaries.append(
            ClaimEvidenceSummary(
                claim_key=claim_key,
                attempts=len(claim_attempts),
                independent_clusters=len(clusters),
                strong_reproduced_clusters=strong_reproduced,
                strong_divergent_clusters=strong_divergent,
                conditional_reproduced_clusters=conditional_reproduced,
                conditional_divergent_clusters=conditional_divergent,
                conflicting_clusters=conflicts,
                current_state=state,
            )
        )
    return summaries


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

        claim_states = aggregate_claim_evidence(self.attempts)
        strong_states = {item.current_state for item in claim_states}
        if "MIXED_EVIDENCE" in strong_states or (
            "REPRODUCED" in strong_states and "RESULT_DIVERGENCE" in strong_states
        ):
            state = "MIXED_EVIDENCE"
        elif "RESULT_DIVERGENCE" in strong_states:
            state = "RESULT_DIVERGENCE"
        elif "REPRODUCED" in strong_states:
            state = "REPRODUCED"
        elif "CONDITIONAL_EVIDENCE" in strong_states:
            state = "CONDITIONAL_EVIDENCE"

        return RecordSummary(
            paper_id=self.paper_id,
            attempts=len(self.attempts),
            reproduced=reproduced,
            divergences=divergences,
            partial=partial,
            unresolved=unresolved,
            open_challenges=open_challenges,
            current_state=state,
            claim_states=claim_states,
        )


def _evidence_metadata(
    result: dict[str, Any],
    bundle: dict[str, Any],
    *,
    repository: str,
) -> tuple[str | None, str | None, EvidenceGrade, str]:
    runtime_build = bundle.get("runtime_build") or {}
    dependency_precision = runtime_build.get("dependency_precision")
    environment = bundle.get("environment") or {}
    historical_fidelity = environment.get("historical_fidelity")
    observation_method = bundle.get("observation_method")
    execution = bundle.get("execution") or {}
    record = bundle.get("record") or {}
    raw_verdict = record.get("verdict")

    decided = raw_verdict in {
        Verdict.VERIFIED.value,
        Verdict.CONTRADICTED.value,
        Verdict.PARTIALLY_VERIFIED.value,
    }
    execution_sound = (
        execution.get("returncode") == 0
        and execution.get("source_unchanged") is True
        and execution.get("artifacts_unchanged") is not False
    )
    locator_sound = observation_method in {
        "explicit_json_path",
        "explicit_regex",
    }
    strong_environment = (
        dependency_precision in {"hash-pinned", "locked"}
        and historical_fidelity == "constrained"
    )
    if decided and execution_sound and locator_sound and strong_environment:
        grade = EvidenceGrade.STRONG
    elif decided and execution_sound and locator_sound:
        grade = EvidenceGrade.CONDITIONAL
    else:
        grade = EvidenceGrade.INCONCLUSIVE

    git = (bundle.get("provenance") or {}).get("git") or {}
    artifact_hashes = sorted(
        str(item.get("sha256"))
        for item in (bundle.get("artifacts") or [])
        if item.get("sha256")
    )
    cluster_payload = json.dumps(
        {
            "repository": repository,
            "commit": git.get("commit"),
            "artifacts": artifact_hashes,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    independence_key = sha256(cluster_payload.encode("utf-8")).hexdigest()
    return dependency_precision, observation_method, grade, independence_key


def _attempt_from_verification(
    *,
    request: dict[str, Any],
    result: dict[str, Any],
    bundle: dict[str, Any],
    attempt_id: str,
    execution_record_url: str | None,
) -> EvidenceAttempt:
    paper_id = request.get("arxiv_id")
    repository = str(request.get("repository") or "unknown")
    repository_ref = str(request.get("repository_ref") or "unknown")
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
    dependency_precision, observation_method, grade, independence_key = (
        _evidence_metadata(result, bundle, repository=repository)
    )
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
        dependency_precision=dependency_precision,
        observation_method=observation_method,
        evidence_grade=grade,
        independence_key=independence_key,
    )


def attempts_from_github_payload(
    payload: dict[str, Any],
    *,
    attempt_id: str,
    execution_record_url: str | None = None,
) -> list[EvidenceAttempt]:
    """Normalize all claim-level verification bundles from one worker payload."""
    result = payload.get("result") or {}
    if result.get("kind") != "verification":
        return [
            attempt_from_github_payload(
                payload,
                attempt_id=attempt_id,
                execution_record_url=execution_record_url,
            )
        ]

    request = payload.get("request") or {}
    bundles: list[dict[str, Any]] = []
    primary = result.get("bundle")
    if isinstance(primary, dict):
        bundles.append(primary)
    for item in result.get("additional_verifications") or []:
        if isinstance(item, dict) and isinstance(item.get("bundle"), dict):
            bundles.append(item["bundle"])

    if not bundles:
        return [
            EvidenceAttempt(
                attempt_id=attempt_id,
                paper_id=request.get("arxiv_id"),
                repository=str(request.get("repository") or "unknown"),
                repository_ref=str(request.get("repository_ref") or "unknown"),
                status=AttemptStatus.INCONCLUSIVE,
                blockers=["verification result contained no claim bundles"],
            )
        ]

    return [
        _attempt_from_verification(
            request=request,
            result=result,
            bundle=bundle,
            attempt_id=attempt_id if index == 0 else f"{attempt_id}-C{index + 1}",
            execution_record_url=execution_record_url,
        )
        for index, bundle in enumerate(bundles)
    ]


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
        return _attempt_from_verification(
            request=request,
            result=result,
            bundle=bundle,
            attempt_id=attempt_id,
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
