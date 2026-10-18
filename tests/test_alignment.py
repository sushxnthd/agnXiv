from pathlib import Path

from agnxiv.alignment import (
    AlignmentCandidate,
    LocalizationGold,
    detector_view,
    load_discrepancy_gold,
    score_localization,
)
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


def test_localization_accepts_multiple_implicated_files() -> None:
    gold = LocalizationGold(
        case_id="case",
        target_paths=["model.py", "layers.py"],
        detector_visible=False,
    )
    candidates = [
        AlignmentCandidate(
            path="unrelated.py",
            line_number=1,
            code_line="value = other(x)",
            paper_sentence="The method transforms the input.",
            shared_tokens=["input"],
            score=2.0,
        ),
        AlignmentCandidate(
            path="layers.py",
            line_number=8,
            code_line="edge_bias = encode(edge)",
            paper_sentence="Edge features are encoded as attention bias.",
            shared_tokens=["edge", "bias"],
            score=1.5,
        ),
    ]

    result = score_localization("case", candidates, gold)

    assert result.first_target_path_rank == 2
    assert result.recall_at_5 is True
    assert result.target_paths == ["model.py", "layers.py"]
