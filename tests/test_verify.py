from agnxiv.models import Claim, Observation, Verdict, VerificationPolicy
from agnxiv.verify import verify_numeric_claim


def test_relative_policy_verifies_close_result() -> None:
    record = verify_numeric_claim(
        Claim(id="C1", text="accuracy", reported_value=0.914),
        [Observation(value=0.9137)],
        VerificationPolicy(kind="relative", tolerance=0.01),
    )
    assert record.verdict == Verdict.VERIFIED
    assert record.relative_error is not None
    assert record.relative_error < 0.01


def test_relative_policy_contradicts_large_difference() -> None:
    record = verify_numeric_claim(
        Claim(id="C1", text="accuracy", reported_value=0.914),
        [Observation(value=0.824)],
        VerificationPolicy(kind="relative", tolerance=0.01),
    )
    assert record.verdict == Verdict.CONTRADICTED


def test_minimum_repetitions_abstains() -> None:
    record = verify_numeric_claim(
        Claim(id="C1", text="accuracy", reported_value=0.914),
        [Observation(value=0.914)],
        VerificationPolicy(kind="relative", tolerance=0.01, minimum_repetitions=3),
    )
    assert record.verdict == Verdict.UNABLE_TO_VERIFY


def test_at_least_policy_verifies_lower_bound() -> None:
    record = verify_numeric_claim(
        Claim(id="C1", text="Accuracy is at least 90%.", reported_value=0.90),
        [Observation(value=0.914)],
        VerificationPolicy(
            kind="absolute",
            operator="at_least",
            tolerance=0.0,
        ),
    )
    assert record.verdict == Verdict.VERIFIED


def test_at_most_policy_contradicts_exceeded_limit() -> None:
    record = verify_numeric_claim(
        Claim(id="C1", text="Latency is at most 100 ms.", reported_value=100.0),
        [Observation(value=108.0)],
        VerificationPolicy(
            kind="absolute",
            operator="at_most",
            tolerance=2.0,
        ),
    )
    assert record.verdict == Verdict.CONTRADICTED


def test_relative_threshold_allows_declared_slack() -> None:
    record = verify_numeric_claim(
        Claim(id="C1", text="Metric is at least 100.", reported_value=100.0),
        [Observation(value=99.5)],
        VerificationPolicy(
            kind="relative",
            operator="at_least",
            tolerance=0.01,
        ),
    )
    assert record.verdict == Verdict.VERIFIED


def test_absolute_tolerance_includes_decimal_boundary() -> None:
    record = verify_numeric_claim(
        Claim(id="C1", text="Gap is 26.6.", reported_value=26.6),
        [Observation(value=26.4)],
        VerificationPolicy(kind="absolute", tolerance=0.2),
    )
    assert record.verdict == Verdict.VERIFIED
