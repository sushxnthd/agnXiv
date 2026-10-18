from agnxiv.challenge import assess_repeated_observations
from agnxiv.models import Claim, Observation, VerificationPolicy


def test_robustness_marks_fragile_repeated_result() -> None:
    claim = Claim(id="C1", text="Accuracy is 0.9", reported_value=0.9)
    observations = [
        Observation(value=0.90),
        Observation(value=0.90),
        Observation(value=0.89),
        Observation(value=0.70),
        Observation(value=0.65),
    ]
    summary = assess_repeated_observations(
        claim,
        observations,
        VerificationPolicy(kind="relative", tolerance=0.02),
        minimum_pass_fraction=0.8,
        minimum_repetitions=5,
    )

    assert summary.status == "FRAGILE_UNDER_DECLARED_TEST"
    assert summary.pass_fraction < 0.8
