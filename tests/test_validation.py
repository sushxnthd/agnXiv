from agnxiv.validation import evaluate_false_pass_gate, zero_event_upper_bound


def test_zero_false_pass_bound_crosses_one_percent_at_299_trials() -> None:
    assert zero_event_upper_bound(298) > 0.01
    assert zero_event_upper_bound(299) <= 0.01


def test_false_pass_gate_requires_zero_failures_and_enough_independent_trials() -> None:
    passing = evaluate_false_pass_gate(
        independent_trials=320,
        false_passes=0,
    )
    assert passing.passed is True
    assert passing.zero_false_pass_upper_bound < 0.01

    too_small = evaluate_false_pass_gate(
        independent_trials=100,
        false_passes=0,
    )
    assert too_small.passed is False

    one_failure = evaluate_false_pass_gate(
        independent_trials=1000,
        false_passes=1,
    )
    assert one_failure.passed is False
    assert one_failure.zero_false_pass_upper_bound == 1.0
