from agnxiv.models import Claim
from agnxiv.outputs import extract_observation_candidates, select_unambiguous_observation


def test_parser_does_not_choose_number_because_it_matches_reported_value() -> None:
    claim = Claim(
        id="C1",
        text="Accuracy is 91.4%.",
        metric="accuracy",
        reported_value=0.914,
        unit="fraction",
    )
    output = "debug reference: 91.4%\naccuracy: 82.4%\n"
    candidates = extract_observation_candidates(output, claim)
    selected = select_unambiguous_observation(candidates)

    assert selected is not None
    assert abs(selected.value - 0.824) < 1e-9


def test_ambiguous_unlabelled_values_are_not_selected() -> None:
    claim = Claim(id="C1", text="Result", reported_value=1.0)
    candidates = extract_observation_candidates("0.9\n1.0\n", claim)
    assert select_unambiguous_observation(candidates) is None


def test_metric_name_digits_are_not_numeric_observations() -> None:
    claim = Claim(id="C1", text="F1 is 0.88.", metric="f1", reported_value=0.88)
    candidates = extract_observation_candidates("f1: 0.71\n", claim)
    selected = select_unambiguous_observation(candidates)

    assert selected is not None
    assert abs(selected.value - 0.71) < 1e-9
