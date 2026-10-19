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


def test_ignores_hyphenated_model_identifiers_as_measurements() -> None:
    claims = extract_quantitative_claims(
        "LoRA performs well on GPT-2 and GPT-3 with no additional inference latency."
    )

    assert claims == []


def test_ignores_pdf_rendered_image_dimensions() -> None:
    claims = extract_quantitative_claims(
        "Our model establishes strong accuracy while synthesizing 512ˆ512 images."
    )

    assert claims == []


def test_ignores_multi_number_citation_lists() -> None:
    claims = extract_quantitative_claims(
        "The perceptual loss [26,54] improves image fidelity."
    )

    assert claims == []


def test_keeps_numeric_range_speedup_after_identifier_filter() -> None:
    claims = extract_quantitative_claims(
        "Our method significantly accelerates VQGAN by 30-64x."
    )

    assert any(
        claim.reported_value == 64 and claim.unit and claim.unit.lower() == "x"
        for claim in claims
    )


def test_ignores_single_digit_patch_dimensions() -> None:
    claims = extract_quantitative_claims(
        "We evaluate shuffled images using 1×1, 2×2, 4×4 and 8×8 patches."
    )

    assert claims == []


def test_ignores_section_list_and_symbolic_parameter_numbers() -> None:
    claims = extract_quantitative_claims(
        "Section 4 gives two examples: 1) robust accuracy and 2) clean accuracy. "
        "We set k = 2 and B = 1.2 for the analysis."
    )

    assert claims == []


def test_ignores_top_k_label_index_but_keeps_reported_accuracy() -> None:
    claims = extract_quantitative_claims(
        "Our method achieves top-1 accuracy of 46.6% on ImageNet."
    )

    assert not any(claim.reported_value == 1 for claim in claims)
    assert any(
        abs((claim.reported_value or 0) - 0.466) < 1e-9
        for claim in claims
    )


def test_ignores_pdf_section_heading_number_before_result_prose() -> None:
    claims = extract_quantitative_claims(
        "5 we report experimental results and discuss ablations."
    )

    assert claims == []
