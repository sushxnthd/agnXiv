from pathlib import Path

from agnxiv.research import (
    CentralityGold,
    SelectiveOutcome,
    binomial_upper_bound_95,
    load_research_cases,
    minimum_zero_event_sample_size,
    score_centrality_ranking,
    score_selective_verification,
)


def test_selective_metrics_separate_false_passes_from_abstention() -> None:
    metrics = score_selective_verification(
        [
            SelectiveOutcome(case_id="a", gold_supports_claim=True, predicted="SUPPORTS"),
            SelectiveOutcome(case_id="b", gold_supports_claim=False, predicted="SUPPORTS"),
            SelectiveOutcome(case_id="c", gold_supports_claim=False, predicted="DIVERGES"),
            SelectiveOutcome(case_id="d", gold_supports_claim=True, predicted="ABSTAIN"),
        ]
    )

    assert metrics.coverage == 0.75
    assert metrics.false_passes == 1
    assert metrics.false_pass_rate == 0.5
    assert metrics.selective_error_rate == 1 / 3


def test_scicoqa_pilot_manifest_is_valid() -> None:
    path = Path("research/benchmarks/scicoqa-pilot-v0.jsonl")
    cases = load_research_cases(path)

    assert len(cases) == 8
    assert all(case.evaluation_role == "diagnostic_nonblind" for case in cases)
    assert all(case.commit for case in cases)
    assert len({case.case_id for case in cases}) == len(cases)


def test_evidence_independence_collapses_correlated_attempts() -> None:
    from agnxiv.research import EvidenceDependency, summarize_evidence_independence

    summary = summarize_evidence_independence(
        ["A", "B", "C"],
        [
            EvidenceDependency(
                left_attempt="A",
                right_attempt="B",
                shared_factors=["author_code", "checkpoint"],
            )
        ],
    )

    assert summary.independent_components == 2
    assert ["A", "B"] in summary.components
    assert ["C"] in summary.components


def test_research_case_supports_alternate_manuscript_sources() -> None:
    cases = load_research_cases(Path("research/benchmarks/scicoqa-pilot-v0.jsonl"))
    bp_case = next(case for case in cases if case.case_id == "SCICOQA-183bd763")

    assert bp_case.paper_alternate_urls
    assert "fullTextXML" in bp_case.paper_alternate_urls[0]


def test_centrality_ranking_reports_first_gold_rank() -> None:
    gold = CentralityGold(
        case_id="paper-a",
        required_substrings=["10000 times", "3 times"],
        rationale="abstract contribution",
    )
    result = score_centrality_ranking(
        "paper-a",
        [
            "A reference result reports 30% latency.",
            "LoRA reduces trainable parameters by 10,000 times and GPU memory by 3 times.",
        ],
        gold,
    )

    assert result.first_gold_rank == 2
    assert result.recall_at_1 is False
    assert result.recall_at_3 is True



def test_zero_false_passes_report_uncertainty_not_zero_risk() -> None:
    upper = binomial_upper_bound_95(0, 12)
    assert 0.22 < upper < 0.23


def test_gold_negative_abstentions_still_count_as_false_pass_opportunities() -> None:
    metrics = score_selective_verification(
        [
            SelectiveOutcome(
                case_id=f"n-{index}",
                gold_supports_claim=False,
                predicted="ABSTAIN",
            )
            for index in range(299)
        ]
    )
    assert metrics.support_predictions == 0
    assert metrics.false_pass_eligible == 299
    assert metrics.false_pass_rate == 0.0
    assert metrics.false_pass_upper_95 <= 0.01


def test_sample_size_for_one_percent_zero_false_pass_claim() -> None:
    assert minimum_zero_event_sample_size(
        target_rate=0.01,
        confidence=0.95,
    ) == 299
