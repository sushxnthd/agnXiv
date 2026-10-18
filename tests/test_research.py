from pathlib import Path

from agnxiv.research import SelectiveOutcome, load_research_cases, score_selective_verification


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
