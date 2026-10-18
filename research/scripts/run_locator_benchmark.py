from __future__ import annotations

import argparse
import json
from pathlib import Path

from agnxiv.locator_bench import load_locator_cases, run_locator_benchmark


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", default="research/benchmarks/locator-v0.jsonl")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = run_locator_benchmark(load_locator_cases(args.benchmark))
    payload = result.model_dump(mode="json")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
