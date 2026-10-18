from agnxiv.claims import extract_quantitative_claims
from agnxiv.models import Claim
from agnxiv.outputs import extract_regex_observation
from agnxiv.zero_manifest import discover_frozen_locator, discover_frozen_locators


def _claim(metric: str, value: float, *, number: int = 1) -> Claim:
    return Claim(
        id=f"C{number:03d}",
        text="Reported a scientific result.",
        metric=metric,
        reported_value=value,
    )


def test_freezes_unique_split_half_metric_without_matching_answer() -> None:
    claims = [
        _claim("split_half_r", 0.51),
        _claim("spearman_brown", 0.68, number=2),
    ]
    output = (
        "  expected split-half r = 0.51\n"
        "  split-half r = 0.47\n"
        "  Spearman-Brown = 0.68\n"
    )
    selected = discover_frozen_locator(output, claims)
    assert selected is not None
    assert selected.claim_id == "C001"
    assert selected.metric == "split_half_r"
    assert "0.47" not in selected.regex
    assert "0.51" not in selected.regex
    assert extract_regex_observation(output, selected.regex).value == 0.47


def test_rejects_duplicate_observed_metric() -> None:
    claims = [_claim("split_half_r", 0.51)]
    output = "split-half r = 0.51\nsplit-half r = 0.49\n"
    assert discover_frozen_locator(output, claims) is None


def test_rejects_multiple_distinct_paper_claims_same_metric() -> None:
    claims = [_claim("split_half_r", 0.51), _claim("split_half_r", 0.68, number=2)]
    assert discover_frozen_locator("split-half r = 0.51", claims) is None


def test_rejects_numeric_echo_without_measurement() -> None:
    claim = _claim("split_half_r", 0.51)
    assert discover_frozen_locator("reported split-half r = 0.51\n", [claim]) is None


def test_rejects_percent_output_without_paper_unit() -> None:
    claim = _claim("accuracy", 0.92)
    assert discover_frozen_locator("accuracy = 92%\n", [claim]) is None


def test_extracts_adjacent_reported_reliability_metrics() -> None:
    text = (
        "We obtained split-half r = 0.51, "
        "Spearman-Brown = 0.68, and Cohen's d = 4.57."
    )
    claims = extract_quantitative_claims(text)
    numeric_metrics = [(row.metric, row.reported_value) for row in claims]
    assert ("split_half_r", 0.51) in numeric_metrics
    assert ("spearman_brown", 0.68) in numeric_metrics
    assert ("cohens_d", 4.57) in numeric_metrics

def test_leading_dot_statistics_in_manuscript() -> None:
    text = (
        "Reliability was measured: split-half r=.51 and "
        "Spearman-Brown=.68 in our experiments."
    )
    claims = extract_quantitative_claims(text)
    assert ("split_half_r", 0.51) in [
        (row.metric, row.reported_value) for row in claims
    ]
    assert ("spearman_brown", 0.68) in [
        (row.metric, row.reported_value) for row in claims
    ]

def test_freezes_every_unique_metric_without_output_value_cherry_picking() -> None:
    claims = [_claim("split_half_r", 0.51), _claim("spearman_brown", 0.68, number=2)]
    output = "split-half r = 0.504\nSpearman-Brown = 0.676\n"
    found = discover_frozen_locators(output, claims)
    assert [row.metric for row in found] == ["split_half_r", "spearman_brown"]
    assert all("0.504" not in row.regex for row in found)
    assert all("0.676" not in row.regex for row in found)


def test_allows_repeated_mentions_of_same_statistic() -> None:
    claims = [_claim("split_half_r", 0.51), _claim("split_half_r", 0.51, number=2)]
    found = discover_frozen_locators("split-half r = 0.504", claims)
    assert len(found) == 1
    assert found[0].claim_id == "C001"


def test_pdf_dash_variant_reliability_metric() -> None:
    claims = extract_quantitative_claims(
        "The Spearman–Brown corrected reliability was 0.68."
    )
    assert any(
        claim.metric == "spearman_brown" and claim.reported_value == 0.68
        for claim in claims
    )
