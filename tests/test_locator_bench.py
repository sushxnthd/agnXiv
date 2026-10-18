from pathlib import Path

from agnxiv.locator_bench import load_locator_cases, run_locator_benchmark


def test_locator_benchmark_masks_reported_answers() -> None:
    cases = load_locator_cases(Path("research/benchmarks/locator-v0.jsonl"))
    assert len(cases) == 12
    result = run_locator_benchmark(cases)
    assert result.cases == 12
    assert result.abstain_cases >= 3
    assert result.selection_cases >= 6
    assert all("observed_value" in row for row in result.per_case)
