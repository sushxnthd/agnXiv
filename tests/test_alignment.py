from pathlib import Path

from agnxiv.alignment import detector_view, load_discrepancy_gold
from agnxiv.research import load_research_cases


def test_discrepancy_gold_is_separate_from_detector_view() -> None:
    cases = {
        case.case_id: case
        for case in load_research_cases(
            Path("research/benchmarks/scicoqa-pilot-v0.jsonl")
        )
    }
    gold = load_discrepancy_gold(
        Path("research/benchmarks/discrepancy-gold-v0.jsonl")
    )

    assert set(gold).issubset(cases)
    view = detector_view(cases["SCICOQA-63197a77"])
    payload = view.model_dump()

    assert "origin_url" not in payload
    assert "target_summary" not in payload
    assert "author_response_status" not in payload
    assert payload["commit"] == "a0d5efec36d74b5dce257492cc6943402573c4f3"


def test_discrepancy_gold_contains_distinct_failure_modes() -> None:
    gold = load_discrepancy_gold(
        Path("research/benchmarks/discrepancy-gold-v0.jsonl")
    )

    categories = {item.category for item in gold.values()}
    assert len(gold) == 4
    assert len(categories) == 4
    assert all(item.detector_visible is False for item in gold.values())
