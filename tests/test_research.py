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
