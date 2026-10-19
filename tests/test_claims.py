from agnxiv.claims import extract_quantitative_claims


def test_extracts_percentage_claim() -> None:
    claims = extract_quantitative_claims(
        "Our proposed model achieves an accuracy of 91.4% on the held-out test set."
    )
    assert claims
    assert any(abs((claim.reported_value or 0) - 0.914) < 1e-9 for claim in claims)


def test_ignores_bare_year() -> None:
    claims = extract_quantitative_claims("The benchmark was introduced in 2024.")
    assert claims == []


def test_metric_is_bound_to_nearby_number_not_adjacent_claim() -> None:
    claims = extract_quantitative_claims(
        "F1 scores are up to 10% higher than competing methods. "
        "The model also uses 60% less training data."
    )

    ten = next(claim for claim in claims if abs((claim.reported_value or 0) - 0.10) < 1e-9)
    sixty = next(claim for claim in claims if abs((claim.reported_value or 0) - 0.60) < 1e-9)

    assert ten.metric == "f1"
    assert sixty.metric is None


def test_claim_text_is_sentence_bounded_not_neighboring_numeric_context() -> None:
    claims = extract_quantitative_claims(
        "The reference classifier has accuracy 76.6%. "
        "Our proposed method achieves accuracy 92.4% on the same test set."
    )

    reference = next(
        claim for claim in claims if abs((claim.reported_value or 0) - 0.766) < 1e-9
    )
    proposed = next(
        claim for claim in claims if abs((claim.reported_value or 0) - 0.924) < 1e-9
    )

    assert "proposed method" not in reference.text.lower()
    assert "proposed method" in proposed.text.lower()


def test_extracts_compact_multiplier_claim() -> None:
    claims = extract_quantitative_claims(
        "Our method accelerates autoregressive decoding by up to 64x."
    )

    assert any(
        claim.reported_value == 64 and claim.unit and claim.unit.lower() == "x"
        for claim in claims
    )


def test_sentence_context_does_not_split_second_decimal() -> None:
    claims = extract_quantitative_claims(
        "Our method saves 77.3% training time and 76.0% memory compared with baselines."
    )

    claim = next(
        item for item in claims if abs((item.reported_value or 0) - 0.773) < 1e-9
    )
    assert "76.0% memory" in claim.text


def test_image_dimensions_are_not_multiplier_claims() -> None:
    claims = extract_quantitative_claims(
        "Our model synthesizes 512×512 images. It accelerates decoding by 64×."
    )

    assert not any(
        claim.reported_value == 512 and claim.unit in {"×", "x"}
        for claim in claims
    )
    assert any(
        claim.reported_value == 64 and claim.unit in {"×", "x"}
        for claim in claims
    )


def test_model_version_suffixes_are_not_quantitative_claims() -> None:
    claims = extract_quantitative_claims(
        "LoRA performs on-par with fine-tuning on RoBERTa, DeBERTa, GPT-2, and GPT-3."
    )
    assert claims == []
