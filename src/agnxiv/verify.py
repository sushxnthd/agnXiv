from __future__ import annotations

from statistics import fmean

from .models import Claim, Observation, Verdict, VerificationPolicy, VerificationRecord


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

    if expected == 0:
        relative_error = 0.0 if absolute_error == 0 else None
    else:
        relative_error = absolute_error / abs(expected)

    if policy.kind == "absolute":
        passed = absolute_error <= policy.tolerance
        comparison = f"absolute error {absolute_error:.6g} <= {policy.tolerance:.6g}"
    elif expected == 0:
        passed = absolute_error <= policy.tolerance
        comparison = (
            "reported value is zero; relative error is undefined, so the "
            f"tolerance is applied as an absolute bound: {absolute_error:.6g} "
            f"<= {policy.tolerance:.6g}"
        )
    else:
        assert relative_error is not None
        passed = relative_error <= policy.tolerance
        comparison = f"relative error {relative_error:.4%} <= {policy.tolerance:.4%}"

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
