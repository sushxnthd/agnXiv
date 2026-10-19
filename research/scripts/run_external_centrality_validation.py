from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict, deque
from pathlib import Path

from agnxiv.auto import score_claim_centrality
from agnxiv.claims import extract_quantitative_claims
from agnxiv.models import Claim


def _paper_key(row: dict[str, str]) -> str:
    conference = (row.get("conference") or "unknown").strip()
    year = (row.get("year") or "unknown").strip()
    identity = (
        row.get("openreview_id")
        or row.get("paper_id")
        or row.get("PaperId")
        or row.get("title")
        or row.get("Paper")
        or ""
    ).strip()
    return f"{conference}:{year}:{identity}"


def _stratum(row: dict[str, str]) -> str:
    return (
        f"{(row.get('conference') or 'unknown').strip()}-"
        f"{(row.get('year') or 'unknown').strip()}"
    )


def _repository(row: dict[str, str]) -> str:
    return (
        row.get("github_repo")
        or row.get("GitHubRepo")
        or row.get("github_repos")
        or row.get("github_links_raw")
        or ""
    ).strip()


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-8, abs_tol=1e-10)


def _units_compatible(left: Claim, right: Claim) -> bool:
    if left.unit is None or right.unit is None:
        return True
    return left.unit == right.unit


def _metric_compatible(left: Claim, right: Claim) -> bool:
    if left.metric is None or right.metric is None:
        return True
    return left.metric == right.metric


def _gold_abstract_indices(
    tldr_claims: list[Claim],
    abstract_claims: list[Claim],
) -> set[int]:
    """Map author-TLDR quantitative claims to unique abstract claims.

    A TLDR claim contributes gold only when its reported numeric value maps to
    exactly one compatible abstract claim. Ambiguous matches are ignored rather
    than resolved with AgnXiv's ranking score.
    """
    gold: set[int] = set()

    for tldr_claim in tldr_claims:
        if tldr_claim.reported_value is None:
            continue
        matches = [
            index
            for index, abstract_claim in enumerate(abstract_claims)
            if (
                abstract_claim.reported_value is not None
                and _close(
                    float(tldr_claim.reported_value),
                    float(abstract_claim.reported_value),
                )
                and _units_compatible(tldr_claim, abstract_claim)
                and _metric_compatible(tldr_claim, abstract_claim)
            )
        ]
        if len(matches) == 1:
            gold.add(matches[0])

    return gold


def _load_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in paths:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                key = _paper_key(row)
                if not key or key in seen:
                    continue
                seen.add(key)
                rows.append(row)
    return rows


def _eligible_case(row: dict[str, str]) -> dict | None:
    abstract = (row.get("abstract") or "").strip()
    tldr = (row.get("tldr") or "").strip()
    if not abstract or not tldr or not _repository(row):
        return None

    abstract_claims = extract_quantitative_claims(abstract)
    tldr_claims = extract_quantitative_claims(tldr)
    if len(abstract_claims) < 2 or not tldr_claims:
        # A one-candidate abstract does not meaningfully test ranking.
        return None

    gold_indices = _gold_abstract_indices(tldr_claims, abstract_claims)
    if not gold_indices:
        return None

    scored = sorted(
        enumerate(abstract_claims),
        key=lambda item: (
            -score_claim_centrality(item[1]),
            item[0],
        ),
    )
    ranks = {
        abstract_index: rank
        for rank, (abstract_index, _) in enumerate(scored, start=1)
    }
    first_gold_rank = min(ranks[index] for index in gold_indices)

    return {
        "paper_cluster": _paper_key(row),
        "stratum": _stratum(row),
        "repository": _repository(row),
        "title": (row.get("title") or row.get("Paper") or "").strip(),
        "candidate_claims": len(abstract_claims),
        "gold_claims": len(gold_indices),
        "first_gold_rank": first_gold_rank,
        "recall_at_1": first_gold_rank <= 1,
        "recall_at_3": first_gold_rank <= 3,
        "recall_at_5": first_gold_rank <= 5,
        "gold": [
            {
                "abstract_index": index,
                "text": abstract_claims[index].text,
                "metric": abstract_claims[index].metric,
                "reported_value": abstract_claims[index].reported_value,
                "unit": abstract_claims[index].unit,
            }
            for index in sorted(gold_indices)
        ],
        "ranking": [
            {
                "rank": rank,
                "abstract_index": abstract_index,
                "score": score_claim_centrality(claim),
                "text": claim.text,
                "metric": claim.metric,
                "reported_value": claim.reported_value,
                "unit": claim.unit,
                "is_gold": abstract_index in gold_indices,
            }
            for rank, (abstract_index, claim) in enumerate(scored, start=1)
        ],
    }


def _balanced_sample(cases: list[dict], *, maximum: int) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        groups[str(case["stratum"])].append(case)

    queues: dict[str, deque[dict]] = {}
    for stratum, group in groups.items():
        queues[stratum] = deque(
            sorted(
                group,
                key=lambda case: hashlib.sha256(
                    (
                        str(case["paper_cluster"])
                        + "|agnxiv-centrality-heldout-v1"
                    ).encode("utf-8")
                ).hexdigest(),
            )
        )

    selected: list[dict] = []
    strata = sorted(queues)
    while len(selected) < maximum:
        progressed = False
        for stratum in strata:
            if not queues[stratum]:
                continue
            selected.append(queues[stratum].popleft())
            progressed = True
            if len(selected) >= maximum:
                break
        if not progressed:
            break
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--max-cases", type=int, default=120)
    parser.add_argument("--minimum-cases", type=int, default=75)
    parser.add_argument("--min-recall-at-1", type=float, default=0.60)
    parser.add_argument("--min-recall-at-3", type=float, default=0.90)
    parser.add_argument("--min-recall-at-5", type=float, default=0.95)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    rows = _load_rows([Path(value) for value in args.input])
    eligible = [
        case
        for row in rows
        if (case := _eligible_case(row)) is not None
    ]
    cases = _balanced_sample(eligible, maximum=args.max_cases)

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
    strata = Counter(str(case["stratum"]) for case in cases)

    passed = (
        total >= args.minimum_cases
        and len(strata) >= 3
        and recall_at_1 >= args.min_recall_at_1
        and recall_at_3 >= args.min_recall_at_3
        and recall_at_5 >= args.min_recall_at_5
    )

    report = {
        "schema_version": "agnxiv.external-centrality/1",
        "evaluation_role": "heldout_external_author_tldr",
        "source": {
            "dataset": "ReproRepo paper metadata",
            "repository": "LithiumDA/ReproRepo",
            "commit": "470a4c69d9f11df15526464e0a5bb66d95a12f55",
            "gold_signal": "author/OpenReview TLDR quantitative claims",
            "sampling_seed": "agnxiv-centrality-heldout-v1",
        },
        "eligibility": (
            "Papers require a repository, an abstract with at least two "
            "quantitative candidates, and at least one author-TLDR quantitative "
            "claim that uniquely maps to a compatible abstract claim."
        ),
        "cases": total,
        "eligible_before_sampling": len(eligible),
        "strata": dict(sorted(strata.items())),
        "recall_at_1": recall_at_1,
        "recall_at_3": recall_at_3,
        "recall_at_5": recall_at_5,
        "mean_reciprocal_rank": mrr,
        "mean_ndcg_at_5": ndcg_at_5,
        "thresholds": {
            "minimum_cases": args.minimum_cases,
            "minimum_strata": 3,
            "min_recall_at_1": args.min_recall_at_1,
            "min_recall_at_3": args.min_recall_at_3,
            "min_recall_at_5": args.min_recall_at_5,
        },
        "passed": passed,
        "cases_detail": cases,
        "interpretation": (
            "This evaluates quantitative central-claim ranking within abstracts "
            "against an external author-supplied TLDR signal. It does not claim "
            "full-document semantic centrality accuracy."
        ),
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))

    if total < args.minimum_cases:
        raise SystemExit(
            f"centrality validation has only {total} eligible held-out papers; "
            f"requires {args.minimum_cases}"
        )
    if len(strata) < 3:
        raise SystemExit("centrality validation requires at least three strata")
    if not passed:
        raise SystemExit(
            "centrality release gate failed: "
            f"R@1={recall_at_1:.4f}, "
            f"R@3={recall_at_3:.4f}, "
            f"R@5={recall_at_5:.4f}"
        )


if __name__ == "__main__":
    main()
