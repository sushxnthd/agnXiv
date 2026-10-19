from __future__ import annotations

from pydantic import BaseModel, Field


class FalsePassGateReport(BaseModel):
    """Statistical release gate for false-positive scientific verification."""

    confidence: float = Field(gt=0.0, lt=1.0)
    independent_trials: int = Field(ge=0)
    false_passes: int = Field(ge=0)
    zero_false_pass_upper_bound: float = Field(ge=0.0, le=1.0)
    minimum_independent_trials: int = Field(ge=1)
    maximum_upper_bound: float = Field(gt=0.0, lt=1.0)
    passed: bool


def zero_event_upper_bound(
    trials: int,
    *,
    confidence: float = 0.95,
) -> float:
    """Exact one-sided Clopper-Pearson upper bound after zero observed events.

    With zero false passes in n independent trials, the upper endpoint p solves
    (1 - p) ** n = 1 - confidence.
    """
    if trials < 1:
        raise ValueError("trials must be at least 1")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between 0 and 1")

    return 1.0 - (1.0 - confidence) ** (1.0 / trials)


def evaluate_false_pass_gate(
    *,
    independent_trials: int,
    false_passes: int,
    confidence: float = 0.95,
    minimum_independent_trials: int = 299,
    maximum_upper_bound: float = 0.01,
) -> FalsePassGateReport:
    """Evaluate the production false-pass release criterion.

    The confidence bound is meaningful only for the predeclared zero-event
    release condition. Any observed false pass closes the gate regardless of
    the nominal sample size.
    """
    if false_passes < 0:
        raise ValueError("false_passes cannot be negative")
    if false_passes > independent_trials:
        raise ValueError("false_passes cannot exceed independent_trials")
    if minimum_independent_trials < 1:
        raise ValueError("minimum_independent_trials must be at least 1")
    if not 0.0 < maximum_upper_bound < 1.0:
        raise ValueError("maximum_upper_bound must be between 0 and 1")

    upper = (
        zero_event_upper_bound(independent_trials, confidence=confidence)
        if independent_trials > 0 and false_passes == 0
        else 1.0
    )
    passed = (
        false_passes == 0
        and independent_trials >= minimum_independent_trials
        and upper <= maximum_upper_bound
    )
    return FalsePassGateReport(
        confidence=confidence,
        independent_trials=independent_trials,
        false_passes=false_passes,
        zero_false_pass_upper_bound=upper,
        minimum_independent_trials=minimum_independent_trials,
        maximum_upper_bound=maximum_upper_bound,
        passed=passed,
    )
