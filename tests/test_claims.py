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
