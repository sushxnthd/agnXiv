from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Literal

from agnxiv.auto import score_claim_centrality
from agnxiv.claims import extract_quantitative_claims
from agnxiv.models import Claim


def _load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid SciTLDR JSON on line {line_number}: {exc}"
            ) from exc
        rows.append(row)
    return rows


def _paper_case(row: dict) -> dict | None:
    source = row.get("source")
    labels = row.get("source_labels")
    paper_id = str(row.get("paper_id") or "").strip()
    title = str(row.get("title") or "").strip()

    if (
        not paper_id
        or not isinstance(source, list)
        or not isinstance(labels, list)
        or len(source) != len(labels)
    ):
        return None

    candidates: list[tuple[int, int, Claim]] = []
    gold_candidate_ids: set[tuple[int, int]] = set()

    for sentence_index, (sentence, label) in enumerate(zip(source, labels)):
        if not isinstance(sentence, str):
            continue
        claims = extract_quantitative_claims(sentence)
        for local_index, claim in enumerate(claims):
            key = (sentence_index, local_index)
            candidates.append((sentence_index, local_index, claim))
            if int(label) == 1:
                gold_candidate_ids.add(key)

    if len(candidates) < 2 or not gold_candidate_ids:
        return None

    ranked = sorted(
        candidates,
        key=lambda item: (
            -score_claim_centrality(item[2]),
            item[0],
            item[1],
        ),
    )
    ranks = {
        (sentence_index, local_index): rank
        for rank, (sentence_index, local_index, _) in enumerate(
            ranked,
            start=1,
        )
    }
    gold_ranks = sorted(
        ranks[key]
        for key in gold_candidate_ids
        if key in ranks
    )
    if not gold_ranks:
        return None

    first_gold_rank = gold_ranks[0]
    return {
        "paper_id": paper_id,
        "title": title,
        "source_sentences": len(source),
        "candidate_claims": len(candidates),
        "gold_quantitative_claims": len(gold_ranks),
        "first_gold_rank": first_gold_rank,
        "recall_at_1": first_gold_rank <= 1,
        "recall_at_3": first_gold_rank <= 3,
        "recall_at_5": first_gold_rank <= 5,
        "gold_ranks": gold_ranks,
        "ranking": [
            {
                "rank": rank,
                "sentence_index": sentence_index,
                "local_claim_index": local_index,
                "score": score_claim_centrality(claim),
                "text": claim.text,
                "metric": claim.metric,
                "reported_value": claim.reported_value,
                "unit": claim.unit,
                "is_gold": (sentence_index, local_index) in gold_candidate_ids,
            }
            for rank, (sentence_index, local_index, claim) in enumerate(
                ranked,
                start=1,
            )
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument(
        "--role",
        choices=("development", "heldout"),
        required=True,
    )
    parser.add_argument("--minimum-cases", type=int, default=75)
    parser.add_argument("--min-recall-at-1", type=float, default=0.60)
    parser.add_argument("--min-recall-at-3", type=float, default=0.90)
    parser.add_argument("--min-recall-at-5", type=float, default=0.95)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    cases = [
        case
        for row in _load_rows(Path(args.input))
        if (case := _paper_case(row)) is not None
    ]
    total = len(cases)

    recall_at_1 = (
        sum(bool(case["recall_at_1"]) for case in cases) / total
        if total
        else 0.0
    )
    recall_at_3 = (
        sum(bool(case["recall_at_3"]) for case in cases) / total
        if total
        else 0.0
    )
    recall_at_5 = (
        sum(bool(case["recall_at_5"]) for case in cases) / total
        if total
        else 0.0
    )
    mrr = (
        sum(1.0 / int(case["first_gold_rank"]) for case in cases) / total
        if total
        else 0.0
    )
    ndcg_at_5 = (
        sum(
            (
                1.0 / math.log2(int(case["first_gold_rank"]) + 1)
                if int(case["first_gold_rank"]) <= 5
                else 0.0
            )
            for case in cases
        )
        / total
        if total
        else 0.0
    )

    passed = (
        total >= args.minimum_cases
        and recall_at_1 >= args.min_recall_at_1
        and recall_at_3 >= args.min_recall_at_3
        and recall_at_5 >= args.min_recall_at_5
    )

    report = {
        "schema_version": "agnxiv.scitldr-centrality/1",
        "evaluation_role": (
            "development_external_oracle"
            if args.role == "development"
            else "heldout_external_oracle"
        ),
        "source": {
            "dataset": "SciTLDR-A",
            "repository": "allenai/scitldr",
            "commit": "5ccad9c00a60ad75c9e04abf7f27d0f53f983b20",
            "input": str(args.input),
            "gold_signal": "SciTLDR source_labels oracle sentence labels",
        },
        "eligibility": (
            "A paper must contain at least two AgnXiv-extracted quantitative "
            "claims and at least one quantitative claim inside a SciTLDR "
            "oracle-labeled source sentence."
        ),
        "cases": total,
        "recall_at_1": recall_at_1,
        "recall_at_3": recall_at_3,
        "recall_at_5": recall_at_5,
        "mean_reciprocal_rank": mrr,
        "mean_ndcg_at_5": ndcg_at_5,
        "thresholds": {
            "minimum_cases": args.minimum_cases,
            "min_recall_at_1": args.min_recall_at_1,
            "min_recall_at_3": args.min_recall_at_3,
            "min_recall_at_5": args.min_recall_at_5,
        },
        "passed": passed,
        "cases_detail": cases,
        "interpretation": (
            "SciTLDR oracle labels provide an external sentence-level summary "
            "target. The benchmark measures whether AgnXiv ranks quantitative "
            "claims from those summary-relevant sentences near the top. It does "
            "not itself evaluate execution or numeric verification correctness."
        ),
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))

    if args.role == "heldout" and not passed:
        raise SystemExit(
            "SciTLDR held-out centrality gate failed: "
            f"n={total}, R@1={recall_at_1:.4f}, "
            f"R@3={recall_at_3:.4f}, R@5={recall_at_5:.4f}"
        )


if __name__ == "__main__":
    main()
