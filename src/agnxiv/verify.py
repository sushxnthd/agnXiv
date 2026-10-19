from __future__ import annotations

import math
from statistics import fmean

from .models import Claim, Observation, Verdict, VerificationPolicy, VerificationRecord

_FLOAT_REL_TOL = 1e-12
_FLOAT_ABS_TOL = 1e-12


def _allowed_slack(expected: float, policy: VerificationPolicy) -> float:
    if policy.kind == "absolute":
        return policy.tolerance
    if expected == 0:
        return policy.tolerance
    return abs(expected) * policy.tolerance


def _less_or_close(left: float, right: float) -> bool:
    return left <= right or math.isclose(
        left,
        right,
        rel_tol=_FLOAT_REL_TOL,
        abs_tol=_FLOAT_ABS_TOL,
    )


def _greater_or_close(left: float, right: float) -> bool:
    return left >= right or math.isclose(
        left,
        right,
        rel_tol=_FLOAT_REL_TOL,
        abs_tol=_FLOAT_ABS_TOL,
    )


def verify_numeric_claim(
    claim: Claim,
    observations: list[Observation],
    policy: VerificationPolicy,
) -> VerificationRecord:
    """Verify a numeric claim using explicit, deterministic comparison rules."""

    if claim.reported_value is None:
        return VerificationRecord(
            claim=claim,
            policy=policy,
            observations=observations,
            verdict=Verdict.UNABLE_TO_VERIFY,
            expected=None,
            observed_mean=None,
            absolute_error=None,
            relative_error=None,
            rationale="Claim has no machine-readable reported numeric value.",
        )

    if (
        not math.isfinite(claim.reported_value)
        or not math.isfinite(policy.tolerance)
        or any(not math.isfinite(item.value) for item in observations)
    ):
        return VerificationRecord(
            claim=claim,
            policy=policy,
            observations=[],
            verdict=Verdict.UNABLE_TO_VERIFY,
            expected=None,
            observed_mean=None,
            absolute_error=None,
            relative_error=None,
            rationale="Non-finite numeric evidence is not eligible for verification.",
        )

    if len(observations) < policy.minimum_repetitions:
        return VerificationRecord(
            claim=claim,
            policy=policy,
            observations=observations,
            verdict=Verdict.UNABLE_TO_VERIFY,
            expected=claim.reported_value,
            observed_mean=fmean(o.value for o in observations) if observations else None,
            absolute_error=None,
            relative_error=None,
            rationale=(
                f"Policy requires {policy.minimum_repetitions} observations; "
                f"received {len(observations)}."
            ),
        )

    observed = fmean(o.value for o in observations)
    expected = claim.reported_value
    absolute_error = abs(observed - expected)
    relative_error = (
        0.0
        if expected == 0 and absolute_error == 0
        else None
        if expected == 0
        else absolute_error / abs(expected)
    )
    slack = _allowed_slack(expected, policy)

    if policy.operator == "approx":
        passed = _less_or_close(absolute_error, slack)
        comparison = (
            f"|observed - reported| = {absolute_error:.6g} "
            f"<= allowed slack {slack:.6g}"
        )
    elif policy.operator == "at_least":
        boundary = expected - slack
        passed = _greater_or_close(observed, boundary)
        comparison = f"observed {observed:.6g} >= lower bound {boundary:.6g}"
    else:
        boundary = expected + slack
        passed = _less_or_close(observed, boundary)
        comparison = f"observed {observed:.6g} <= upper bound {boundary:.6g}"

    verdict = Verdict.VERIFIED if passed else Verdict.CONTRADICTED

    return VerificationRecord(
        claim=claim,
        policy=policy,
        observations=observations,
        verdict=verdict,
        expected=expected,
        observed_mean=observed,
        absolute_error=absolute_error,
        relative_error=relative_error,
        rationale=comparison,
    )
