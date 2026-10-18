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
