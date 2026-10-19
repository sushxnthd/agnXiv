from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from agnxiv.research import load_centrality_gold, score_centrality_ranking


def _find_plan(input_root: Path, case_id: str) -> Path:
    matches = [
        path
        for path in input_root.rglob("plan.json")
        if case_id in path.as_posix()
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one diagnostic plan for {case_id}, found {len(matches)}"
        )
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--gold", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_root = Path(args.input_root)
    gold_rows = load_centrality_gold(args.gold)
    results = []

    for case_id, gold in sorted(gold_rows.items()):
        plan_path = _find_plan(input_root, case_id)
        payload = json.loads(plan_path.read_text(encoding="utf-8"))
        ranked_claims = [
            row["claim"]["text"]
            for row in payload.get("claims", [])
            if isinstance(row, dict)
            and isinstance(row.get("claim"), dict)
            and isinstance(row["claim"].get("text"), str)
        ]
        scored = score_centrality_ranking(
            case_id,
            ranked_claims,
            gold,
        )
        rank = scored.first_gold_rank
        results.append(
            {
                **scored.model_dump(mode="json"),
                "reciprocal_rank": (1.0 / rank) if rank else 0.0,
                "ndcg_at_5": (
                    1.0 / math.log2(rank + 1)
                    if rank is not None and rank <= 5
                    else 0.0
                ),
            }
        )

    cases = len(results)
    report = {
        "schema_version": "agnxiv.centrality-diagnostic/1",
        "evaluation_role": "diagnostic_nonblind",
        "cases": cases,
        "recall_at_1": (
            sum(bool(row["recall_at_1"]) for row in results) / cases
            if cases
            else 0.0
        ),
        "recall_at_3": (
            sum(bool(row["recall_at_3"]) for row in results) / cases
            if cases
            else 0.0
        ),
        "recall_at_5": (
            sum(bool(row["recall_at_5"]) for row in results) / cases
            if cases
            else 0.0
        ),
        "mean_reciprocal_rank": (
            sum(float(row["reciprocal_rank"]) for row in results) / cases
            if cases
            else 0.0
        ),
        "mean_ndcg_at_5": (
            sum(float(row["ndcg_at_5"]) for row in results) / cases
            if cases
            else 0.0
        ),
        "results": results,
        "warning": (
            "This is a known non-blind regression set. It can detect regressions "
            "but cannot establish production central-claim accuracy."
        ),
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
