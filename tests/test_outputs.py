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


def test_explicit_json_locator_selects_exact_field() -> None:
    from agnxiv.outputs import extract_json_observation

    output = '{"debug": 0.914, "metrics": {"accuracy": 0.824}}'
    observation = extract_json_observation(output, "metrics.accuracy")

    assert observation is not None
    assert abs(observation.value - 0.824) < 1e-9


def test_explicit_json_locator_supports_list_indices_and_scale() -> None:
    from agnxiv.outputs import extract_json_observation

    output = 'log line\n{"runs": [{"f1": 71.0}]}'
    observation = extract_json_observation(output, "runs.0.f1", scale=0.01)

    assert observation is not None
    assert abs(observation.value - 0.71) < 1e-9


def test_explicit_json_locator_rejects_boolean() -> None:
    from agnxiv.outputs import extract_json_observation

    assert extract_json_observation('{"passed": true}', "passed") is None


def test_explicit_regex_locator_extracts_one_declared_value() -> None:
    from agnxiv.outputs import extract_regex_observation

    output = "paper 26.6\nPool A gap G (15-85) got 26.4\n"
    observation = extract_regex_observation(
        output,
        r"Pool A gap G \(15-85\) got (?P<value>[-+]?\d+\.\d+)",
    )

    assert observation is not None
    assert abs(observation.value - 26.4) < 1e-9


def test_explicit_regex_locator_rejects_multiple_matches() -> None:
    from agnxiv.outputs import extract_regex_observation

    output = "accuracy: 0.8\naccuracy: 0.9\n"
    observation = extract_regex_observation(
        output,
        r"accuracy: (?P<value>\d+\.\d+)",
    )

    assert observation is None


def test_explicit_regex_locator_requires_one_capture() -> None:
    from agnxiv.outputs import extract_regex_observation

    assert extract_regex_observation("accuracy: 0.8", r"accuracy: \d+\.\d+") is None


def test_metric_alias_requires_token_boundary() -> None:
    claim = Claim(
        id="C1",
        text="Accuracy is 91.4%.",
        metric="accuracy",
        reported_value=0.914,
        unit="fraction",
    )
    candidates = extract_observation_candidates(
        "account: 91.4%\nobserved result: 82.4%\n",
        claim,
    )
    selected = select_unambiguous_observation(candidates)

    assert selected is not None
    assert abs(selected.value - 0.824) < 1e-9


def test_reference_metric_loses_to_observed_metric_without_answer_matching() -> None:
    claim = Claim(
        id="C1",
        text="Accuracy is 91.4%.",
        metric="accuracy",
        reported_value=0.914,
        unit="fraction",
    )
    candidates = extract_observation_candidates(
        "reference accuracy: 91.4%\nobserved accuracy: 82.4%\n",
        claim,
    )
    selected = select_unambiguous_observation(candidates)

    assert selected is not None
    assert abs(selected.value - 0.824) < 1e-9


def test_mixed_target_observed_same_line_remains_ambiguous() -> None:
    claim = Claim(
        id="C1",
        text="Accuracy is 91.4%.",
        metric="accuracy",
        reported_value=0.914,
        unit="fraction",
    )
    candidates = extract_observation_candidates(
        "target accuracy=91.4%; observed accuracy=82.4%\n",
        claim,
    )
    assert select_unambiguous_observation(candidates) is None


def test_claim_split_qualifier_selects_test_metric() -> None:
    claim = Claim(
        id="C1",
        text="Test accuracy on the held-out set.",
        metric="accuracy",
        unit="fraction",
    )
    candidates = extract_observation_candidates(
        "validation accuracy: 84.1%\ntest accuracy: 82.0%\n",
        claim,
    )
    selected = select_unambiguous_observation(candidates)

    assert selected is not None
    assert abs(selected.value - 0.82) < 1e-9


def test_claim_split_qualifier_selects_validation_metric() -> None:
    claim = Claim(
        id="C1",
        text="Validation MAE used for model selection.",
        metric="mae",
    )
    candidates = extract_observation_candidates(
        "val/mae: 3.9\ntest/mae: 4.2\n",
        claim,
    )
    selected = select_unambiguous_observation(candidates)

    assert selected is not None
    assert abs(selected.value - 3.9) < 1e-9


def test_local_key_binds_metric_to_value_on_multi_metric_line() -> None:
    f1_claim = Claim(id="C1", text="F1 score.", metric="f1")
    accuracy_claim = Claim(id="C2", text="Accuracy.", metric="accuracy")

    f1 = select_unambiguous_observation(
        extract_observation_candidates("accuracy=0.82 f1=0.71\n", f1_claim)
    )
    accuracy = select_unambiguous_observation(
        extract_observation_candidates("accuracy=0.82 f1=0.71\n", accuracy_claim)
    )

    assert f1 is not None and abs(f1.value - 0.71) < 1e-9
    assert accuracy is not None and abs(accuracy.value - 0.82) < 1e-9


def test_metric_label_digit_is_not_observation() -> None:
    claim = Claim(id="C1", text="BLEU score.", metric="bleu")
    candidates = extract_observation_candidates("BLEU-4: 32.1\n", claim)
    selected = select_unambiguous_observation(candidates)

    assert selected is not None
    assert abs(selected.value - 32.1) < 1e-9
    assert all(candidate.raw_value != 4 for candidate in candidates)


def test_p_value_alias_is_recognized() -> None:
    claim = Claim(id="C1", text="Statistical p-value.", metric="p_value")
    selected = select_unambiguous_observation(
        extract_observation_candidates("p-value = 0.003\n", claim)
    )

    assert selected is not None
    assert abs(selected.value - 0.003) < 1e-12


def test_summary_qualifier_selects_median_over_p95() -> None:
    claim = Claim(
        id="C1",
        text="Median inference latency.",
        metric="latency",
        unit="ms",
    )
    selected = select_unambiguous_observation(
        extract_observation_candidates(
            "median latency: 42 ms\np95 latency: 60 ms\n",
            claim,
        )
    )

    assert selected is not None
    assert abs(selected.value - 42.0) < 1e-9


def test_target_and_observed_on_same_line_still_abstains_after_key_binding() -> None:
    claim = Claim(
        id="C1",
        text="Test accuracy.",
        metric="accuracy",
        unit="fraction",
    )
    candidates = extract_observation_candidates(
        "target accuracy=91.4%; observed accuracy=82.4%\n",
        claim,
    )

    assert select_unambiguous_observation(candidates) is None


def test_explicit_regex_locator_rejects_redos_shapes_and_extra_captures() -> None:
    from agnxiv.outputs import extract_regex_observation, safe_regex_pattern

    assert safe_regex_pattern(r"accuracy: (?P<value>\d+\.\d+)")
    for pattern in (
        r"(?P<value>(a+)+)$",
        r"(?P<value>(a|aa)+)$",
        r"(?=(?P<value>\d+))",
        r"(?P<value>\d+)\s+\1",
        r"(?P<value>\d+)(extra)",
    ):
        assert safe_regex_pattern(pattern) is False
        assert extract_regex_observation("a" * 10000, pattern) is None


def test_explicit_regex_locator_stops_after_second_match() -> None:
    from agnxiv.outputs import extract_regex_observation

    output = ("accuracy: 0.8\n" * 100_000)
    assert (
        extract_regex_observation(
            output,
            r"accuracy: (?P<value>\d+\.\d+)",
        )
        is None
    )


def test_explicit_json_locator_rejects_nan_and_infinity() -> None:
    from agnxiv.outputs import extract_json_observation

    assert extract_json_observation('{"x": NaN}', "x") is None
    assert extract_json_observation('{"x": Infinity}', "x") is None
    assert extract_json_observation('{"x": 1e308}', "x", scale=1e308) is None


def test_explicit_regex_locator_rejects_overflowed_numeric_value() -> None:
    from agnxiv.outputs import extract_regex_observation

    assert (
        extract_regex_observation(
            "metric=1e999",
            r"metric=(?P<value>\d+e\d+)",
        )
        is None
    )
