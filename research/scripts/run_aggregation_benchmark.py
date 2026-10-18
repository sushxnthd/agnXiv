from __future__ import annotations

import argparse
import json
from pathlib import Path

from agnxiv.network import EvidenceAttempt, aggregate_claim_evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--benchmark",
        default="research/benchmarks/aggregation-v1.jsonl",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    rows = []
    matched = 0
    for raw in Path(args.benchmark).read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        case = json.loads(raw)
        attempts = [EvidenceAttempt.model_validate(item) for item in case["attempts"]]
        summaries = aggregate_claim_evidence(attempts)
        actual_by_claim = {item.claim_key: item.current_state for item in summaries}

        if "expected_state" in case:
            actual = summaries[0].current_state if len(summaries) == 1 else None
            correct = (
                actual == case["expected_state"]
                and summaries[0].independent_clusters == case["expected_clusters"]
            )
        else:
            actual = actual_by_claim
            correct = (
                actual_by_claim == case["expected_state_by_claim"]
                and len(summaries) == case["expected_claims"]
            )
        matched += int(correct)
        rows.append(
            {
                "id": case["id"],
                "correct": correct,
                "actual": actual,
                "claim_states": [item.model_dump(mode="json") for item in summaries],
            }
        )

    report = {
        "cases": len(rows),
        "matched": matched,
        "accuracy": matched / len(rows) if rows else 0.0,
        "results": rows,
    }
    Path(args.output).write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if matched != len(rows):
        raise SystemExit("aggregation benchmark mismatch")


if __name__ == "__main__":
    main()
