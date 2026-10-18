from pathlib import Path

from agnxiv.benchmark import load_jsonl_cases, run_recorded_benchmark


def test_core_benchmark_has_zero_false_passes() -> None:
    path = Path(__file__).parents[1] / "benchmarks" / "core.jsonl"
    report = run_recorded_benchmark(load_jsonl_cases(path))

    assert report.total >= 5
    assert report.false_passes == 0
    assert report.false_pass_rate == 0.0
    assert report.matched == report.total


def test_benchmark_reports_decision_coverage() -> None:
    path = Path(__file__).parents[1] / "research" / "benchmarks" / "redbench-v0.jsonl"
    cases = load_jsonl_cases(path)
    report = run_recorded_benchmark(cases)

    assert report.total == len(cases)
    assert report.total >= 12
    assert all("\\n" not in case.output for case in cases)
    assert 0.0 <= report.coverage <= 1.0
    assert report.false_passes == 0
