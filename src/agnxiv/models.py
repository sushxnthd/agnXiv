from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Verdict(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    CONTRADICTED = "CONTRADICTED"
    UNABLE_TO_VERIFY = "UNABLE_TO_VERIFY"


class ClaimSource(BaseModel):
    manuscript: str | None = None
    page: int | None = Field(default=None, ge=1)
    section: str | None = None
    table: str | None = None
    figure: str | None = None
    quote: str | None = None


class EvidenceRef(BaseModel):
    repository: str | None = None
    commit: str | None = None
    path: str | None = None
    command: str | None = None
    dataset: str | None = None
    environment_digest: str | None = None


class Claim(BaseModel):
    id: str
    text: str
    claim_type: str = "quantitative"
    metric: str | None = None
    reported_value: float | None = None
    reported_uncertainty: float | None = Field(default=None, ge=0)
    unit: str | None = None
    source: ClaimSource = Field(default_factory=ClaimSource)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class VerificationPolicy(BaseModel):
    kind: Literal["absolute", "relative"] = "relative"
    tolerance: float = Field(gt=0)
    minimum_repetitions: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_relative_tolerance(self) -> VerificationPolicy:
        if self.kind == "relative" and self.tolerance > 1:
            raise ValueError("relative tolerance must be expressed as a fraction, e.g. 0.01")
        return self


class Observation(BaseModel):
    value: float
    run_id: str | None = None
    seed: int | None = None
    output_digest: str | None = None


class VerificationRecord(BaseModel):
    schema_version: str = "agnxiv.verify/0.1"
    claim: Claim
    policy: VerificationPolicy
    observations: list[Observation]
    verdict: Verdict
    expected: float | None
    observed_mean: float | None
    absolute_error: float | None
    relative_error: float | None
    rationale: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
