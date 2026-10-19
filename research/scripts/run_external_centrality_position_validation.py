from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict, deque
from pathlib import Path

from agnxiv.auto import rank_claim_indices_with_statement_diversity, score_claim_centrality
from agnxiv.claims import extract_quantitative_claims


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


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _load_exclusions(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


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


def _eligible_case(row: dict[str, str], exclusions: set[str]) -> dict | None:
    paper_key = _paper_key(row)
    if paper_key in exclusions:
        return None

    abstract = (row.get("abstract") or "").strip()
    if not abstract or not _repository(row):
        return None

    claims = extract_quantitative_claims(abstract)
    if len(claims) < 2:
        return None

    # External author-emphasis proxy: the last quantitative sentence in the
    # abstract. Require that sentence to contain exactly one extracted claim
    # and occur in the latter half of the author-written abstract. This rule
    # is independent of AgnXiv's centrality score.
    last = claims[-1]
    same_sentence = [
        index
        for index, claim in enumerate(claims)
        if claim.text == last.text
    ]
    if len(same_sentence) != 1:
        return None

    normalized_abstract = _normalize(abstract)
    normalized_sentence = _normalize(last.text)
    sentence_start = normalized_abstract.rfind(normalized_sentence)
    if sentence_start < 0 or not normalized_abstract:
        return None
    relative_position = sentence_start / max(1, len(normalized_abstract))
    if relative_position < 0.50:
        return None

    gold_index = len(claims) - 1
    scores = [score_claim_centrality(claim) for claim in claims]
    order = rank_claim_indices_with_statement_diversity(claims, scores)
    scored = [(index, claims[index]) for index in order]
    ranks = {
        claim_index: rank
        for rank, (claim_index, _) in enumerate(scored, start=1)
    }
    gold_rank = ranks[gold_index]

    return {
        "paper_cluster": paper_key,
        "stratum": _stratum(row),
        "repository": _repository(row),
        "title": (row.get("title") or row.get("Paper") or "").strip(),
        "candidate_claims": len(claims),
        "gold_method": "late_unique_quantitative_sentence",
        "gold_relative_position": relative_position,
        "first_gold_rank": gold_rank,
        "recall_at_1": gold_rank <= 1,
        "recall_at_3": gold_rank <= 3,
        "recall_at_5": gold_rank <= 5,
        "gold": {
            "abstract_index": gold_index,
            "text": last.text,
            "metric": last.metric,
            "reported_value": last.reported_value,
            "unit": last.unit,
        },
        "ranking": [
            {
                "rank": rank,
                "abstract_index": claim_index,
                "score": score_claim_centrality(claim),
                "text": claim.text,
                "metric": claim.metric,
                "reported_value": claim.reported_value,
                "unit": claim.unit,
                "is_gold": claim_index == gold_index,
            }
            for rank, (claim_index, claim) in enumerate(scored, start=1)
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
                        + "|agnxiv-centrality-position-heldout-v1"
                    ).encode("utf-8")
                ).hexdigest(),
            )
        )

    selected: list[dict] = []
    strata = sorted(queues)
    while len(selected) < maximum:
        progressed = False
        for stratum in strata:
            queue = queues[stratum]
            if not queue:
                continue
            selected.append(queue.popleft())
            progressed = True
            if len(selected) >= maximum:
                break
        if not progressed:
            break
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--exclude", required=True)
    parser.add_argument("--max-cases", type=int, default=120)
    parser.add_argument("--minimum-cases", type=int, default=75)
    parser.add_argument("--min-recall-at-1", type=float, default=0.60)
    parser.add_argument("--min-recall-at-3", type=float, default=0.90)
    parser.add_argument("--min-recall-at-5", type=float, default=0.95)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    exclusions = _load_exclusions(Path(args.exclude))
    rows = _load_rows([Path(value) for value in args.input])
    eligible = [
        case
        for row in rows
        if (case := _eligible_case(row, exclusions)) is not None
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
        "schema_version": "agnxiv.external-centrality-position/1",
        "evaluation_role": "heldout_external_author_emphasis_proxy",
        "source": {
            "dataset": "ReproRepo paper metadata",
            "repository": "LithiumDA/ReproRepo",
            "commit": "470a4c69d9f11df15526464e0a5bb66d95a12f55",
            "sampling_seed": "agnxiv-centrality-position-heldout-v1",
            "development_exclusions": sorted(exclusions),
        },
        "gold_proxy": (
            "The unique quantitative claim in the last quantitative sentence of "
            "the author abstract, restricted to sentences starting in the latter "
            "half of the abstract."
        ),
        "cases": total,
        "eligible_before_sampling": len(eligible),
        "excluded_development_papers": len(exclusions),
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
            "This is a large disjoint author-emphasis proxy for abstract-level "
            "quantitative centrality. It complements, but does not replace, the "
            "smaller author-TLDR development/diagnostic set or human annotation."
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
            f"position centrality validation has only {total} eligible papers; "
            f"requires {args.minimum_cases}"
        )
    if len(strata) < 3:
        raise SystemExit("position centrality validation requires at least three strata")
    if not passed:
        raise SystemExit(
            "position centrality release gate failed: "
            f"R@1={recall_at_1:.4f}, "
            f"R@3={recall_at_3:.4f}, "
            f"R@5={recall_at_5:.4f}"
        )


if __name__ == "__main__":
    main()
