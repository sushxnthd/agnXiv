from pathlib import Path

from agnxiv.benchmark import load_jsonl_cases, run_recorded_benchmark


def test_core_benchmark_has_zero_false_passes() -> None:
    path = Path(__file__).parents[1] / "benchmarks" / "core.jsonl"
    report = run_recorded_benchmark(load_jsonl_cases(path))

    assert report.total >= 5
    assert report.false_passes == 0
    assert report.false_pass_rate == 0.0
    assert report.matched == report.total
