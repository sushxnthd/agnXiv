from __future__ import annotations

from statistics import fmean, pstdev

from pydantic import BaseModel, Field

from .models import Claim, Observation, Verdict, VerificationPolicy
from .verify import verify_numeric_claim


class RobustnessSummary(BaseModel):
    claim_id: str
    repetitions: int = Field(ge=0)
    pass_count: int = Field(ge=0)
    pass_fraction: float = Field(ge=0.0, le=1.0)
    mean: float | None
    standard_deviation: float | None
    minimum: float | None
    maximum: float | None
    status: str
    rationale: str


def assess_repeated_observations(
    claim: Claim,
    observations: list[Observation],
    policy: VerificationPolicy,
    *,
    minimum_pass_fraction: float = 0.8,
    minimum_repetitions: int = 5,
) -> RobustnessSummary:
    """Assess repeated-run stability separately from basic reproduction."""
    if not 0 <= minimum_pass_fraction <= 1:
        raise ValueError("minimum_pass_fraction must be between 0 and 1")

    if len(observations) < minimum_repetitions:
        return RobustnessSummary(
            claim_id=claim.id,
            repetitions=len(observations),
            pass_count=0,
            pass_fraction=0.0,
            mean=fmean(o.value for o in observations) if observations else None,
            standard_deviation=(
                pstdev(o.value for o in observations)
                if len(observations) > 1
                else None
            ),
            minimum=min((o.value for o in observations), default=None),
            maximum=max((o.value for o in observations), default=None),
            status="INCONCLUSIVE",
            rationale=(
                f"Robustness policy requires at least {minimum_repetitions} repetitions; "
                f"received {len(observations)}."
            ),
        )

    individual_records = [
        verify_numeric_claim(
            claim,
            [observation],
            VerificationPolicy(
                kind=policy.kind,
                tolerance=policy.tolerance,
                minimum_repetitions=1,
            ),
        )
        for observation in observations
    ]
    pass_count = sum(record.verdict == Verdict.VERIFIED for record in individual_records)
    pass_fraction = pass_count / len(observations)
    values = [o.value for o in observations]

    if pass_fraction >= minimum_pass_fraction:
        status = "ROBUST_UNDER_DECLARED_TEST"
        rationale = (
            f"{pass_count}/{len(observations)} repeated observations satisfy the "
            f"declared reproduction policy."
        )
    else:
        status = "FRAGILE_UNDER_DECLARED_TEST"
        rationale = (
            f"Only {pass_count}/{len(observations)} repeated observations satisfy "
            f"the declared reproduction policy."
        )

    return RobustnessSummary(
        claim_id=claim.id,
        repetitions=len(observations),
        pass_count=pass_count,
        pass_fraction=pass_fraction,
        mean=fmean(values),
        standard_deviation=pstdev(values) if len(values) > 1 else 0.0,
        minimum=min(values),
        maximum=max(values),
        status=status,
        rationale=rationale,
    )
