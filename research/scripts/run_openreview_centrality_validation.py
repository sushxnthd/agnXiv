from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path

from agnxiv.auto import rank_claim_indices_with_statement_diversity, score_claim_centrality
from agnxiv.claims import extract_quantitative_claims
from agnxiv.models import Claim

SOURCE_COMMIT = "740c3112f479019d9902780fd627b0b7c19eac7c"

_STOPWORDS = {
    "about", "after", "also", "among", "and", "are", "been", "being", "but",
    "can", "for", "from", "has", "have", "into", "its", "more", "our", "than",
    "that", "the", "their", "this", "through", "using", "was", "were", "which",
    "while", "with", "without", "we", "show", "shows", "paper", "method", "model",
    "approach", "results", "result",
}


def _stem(token: str) -> str:
    for suffix in ("ization", "ations", "ation", "ments", "ment", "ingly", "ing", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) > len(suffix) + 3:
            return token[: -len(suffix)]
    return token


def _tokens(text: str) -> set[str]:
    return {
        _stem(token)
        for token in re.findall(r"[a-z][a-z0-9-]{2,}", text.lower())
        if token not in _STOPWORDS
    }


def _lexical_score(anchor: set[str], claim: set[str]) -> tuple[float, int]:
    overlap = len(anchor & claim)
    if not anchor or not claim or not overlap:
        return 0.0, overlap
    precision = overlap / len(claim)
    recall = overlap / len(anchor)
    return 2.0 * precision * recall / (precision + recall), overlap


def _close(left: float, right: float) -> bool:
    scale = max(1.0, abs(left), abs(right))
    return abs(left - right) <= max(1e-9, scale * 1e-6)


def _compatible(left: Claim, right: Claim) -> bool:
    if left.metric and right.metric and left.metric != right.metric:
        return False
    return not (left.unit and right.unit and left.unit != right.unit)


def _gold_indices(
    *,
    title: str,
    tldr: str,
    abstract_claims: list[Claim],
) -> tuple[set[int], str | None]:
    tldr_claims = extract_quantitative_claims(tldr)
    exact: set[int] = set()

    for tldr_claim in tldr_claims:
        if tldr_claim.reported_value is None:
            continue
        matches = [
            index
            for index, claim in enumerate(abstract_claims)
            if (
                claim.reported_value is not None
                and _close(
                    float(tldr_claim.reported_value),
                    float(claim.reported_value),
                )
                and _compatible(tldr_claim, claim)
            )
        ]
        if len(matches) == 1:
            exact.add(matches[0])

    if exact:
        return exact, "quantitative_tldr"

    anchor = _tokens(f"{title} {tldr}")
    scored: list[tuple[float, int, int]] = []
    for index, claim in enumerate(abstract_claims):
        score, overlap = _lexical_score(anchor, _tokens(claim.text))
        scored.append((score, overlap, index))
    scored.sort(reverse=True)

    if not scored:
        return set(), None

    best_score, best_overlap, best_index = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    if (
        best_overlap >= 2
        and best_score >= 0.08
        and best_score - second_score >= 0.015
    ):
        return {best_index}, "author_anchor_lexical"

    return set(), None


def _selected(paper_id: str, *, seed: str, modulus: int, bucket: int) -> bool:
    digest = hashlib.sha256(f"{seed}|{paper_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % modulus == bucket


def _row_value(row: dict[str, str], *names: str) -> str:
    lowered = {key.lower(): value for key, value in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value:
            return value.strip()
    return ""


def _case(row: dict[str, str]) -> dict | None:
    paper_id = _row_value(row, "id", "paper_id")
    title = _row_value(row, "title")
    abstract = _row_value(row, "abstract")
    tldr = _row_value(row, "tldr")
    area = _row_value(row, "primary_area", "primary area")
    if not paper_id or not title or not abstract or not tldr:
        return None

    claims = extract_quantitative_claims(abstract)
    if len(claims) < 2:
        return None

    gold, method = _gold_indices(
        title=title,
        tldr=tldr,
        abstract_claims=claims,
    )
    if not gold or method is None:
        return None

    scores = [score_claim_centrality(claim) for claim in claims]
    order = rank_claim_indices_with_statement_diversity(claims, scores)
    ranks = {claim_index: rank for rank, claim_index in enumerate(order, start=1)}
    first = min(ranks[index] for index in gold)

    return {
        "paper_id": paper_id,
        "title": title,
        "primary_area": area or "unspecified",
        "candidate_claims": len(claims),
        "gold_method": method,
        "gold_claims": len(gold),
        "first_gold_rank": first,
        "recall_at_1": first <= 1,
        "recall_at_3": first <= 3,
        "recall_at_5": first <= 5,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--hash-seed", required=True)
    parser.add_argument("--hash-modulus", type=int, required=True)
    parser.add_argument("--hash-bucket", type=int, required=True)
    parser.add_argument("--minimum-cases", type=int, default=75)
    parser.add_argument("--minimum-areas", type=int, default=4)
    parser.add_argument("--min-recall-at-3", type=float, default=0.90)
    parser.add_argument("--min-recall-at-5", type=float, default=0.95)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.hash_modulus < 1:
        raise ValueError("hash-modulus must be >= 1")
    if not 0 <= args.hash_bucket < args.hash_modulus:
        raise ValueError("hash-bucket must be in [0, hash-modulus)")

    rows: list[dict[str, str]] = []
    with Path(args.input).open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            paper_id = _row_value(row, "id", "paper_id")
            if paper_id and _selected(
                paper_id,
                seed=args.hash_seed,
                modulus=args.hash_modulus,
                bucket=args.hash_bucket,
            ):
                rows.append(row)

    cases = [case for row in rows if (case := _case(row)) is not None]
    total = len(cases)
    r1 = sum(bool(case["recall_at_1"]) for case in cases) / total if total else 0.0
    r3 = sum(bool(case["recall_at_3"]) for case in cases) / total if total else 0.0
    r5 = sum(bool(case["recall_at_5"]) for case in cases) / total if total else 0.0
    mrr = (
        sum(1.0 / int(case["first_gold_rank"]) for case in cases) / total
        if total
        else 0.0
    )
    ndcg5 = (
        sum(
            1.0 / math.log2(int(case["first_gold_rank"]) + 1)
            if int(case["first_gold_rank"]) <= 5
            else 0.0
            for case in cases
        )
        / total
        if total
        else 0.0
    )

    methods: dict[str, int] = {}
    areas: dict[str, int] = {}
    for case in cases:
        method = str(case["gold_method"])
        area = str(case["primary_area"])
        methods[method] = methods.get(method, 0) + 1
        areas[area] = areas.get(area, 0) + 1

    passed = (
        total >= args.minimum_cases
        and len(areas) >= args.minimum_areas
        and r3 >= args.min_recall_at_3
        and r5 >= args.min_recall_at_5
    )

    report = {
        "schema_version": "agnxiv.openreview-centrality/1",
        "evaluation_role": "heldout_external_author_metadata",
        "source": {
            "dataset": "ICLR 2024 OpenReview submission metadata",
            "repository": "astenuz/iclr2024-openreview",
            "commit": SOURCE_COMMIT,
            "input": str(args.input),
            "gold_signal": "author title + author TLDR",
            "hash_seed": args.hash_seed,
            "hash_modulus": args.hash_modulus,
            "hash_bucket": args.hash_bucket,
        },
        "eligibility": (
            "Non-empty author TLDR and at least two quantitative abstract claims. "
            "Gold prefers unique quantitative TLDR-to-abstract matches; lexical "
            "fallback uses title+TLDR with >=2 shared content tokens, F1 >=0.08, "
            "and margin >=0.015. Centrality scores are never consulted for gold."
        ),
        "source_rows_after_partition": len(rows),
        "cases": total,
        "primary_areas": dict(sorted(areas.items())),
        "gold_methods": dict(sorted(methods.items())),
        "recall_at_1": r1,
        "recall_at_3": r3,
        "recall_at_5": r5,
        "mean_reciprocal_rank": mrr,
        "mean_ndcg_at_5": ndcg5,
        "thresholds": {
            "minimum_cases": args.minimum_cases,
            "minimum_areas": args.minimum_areas,
            "min_recall_at_3": args.min_recall_at_3,
            "min_recall_at_5": args.min_recall_at_5,
        },
        "passed": passed,
        "cases_detail": cases,
        "interpretation": (
            "This evaluates abstract-level quantitative claim routing against "
            "external author metadata. Recall@1 is diagnostic; the production "
            "gate requires the author-salient claim inside the verification slate."
        ),
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))

    if not passed:
        raise SystemExit(
            "ICLR OpenReview centrality gate failed: "
            f"n={total}, areas={len(areas)}, R@1={r1:.4f}, "
            f"R@3={r3:.4f}, R@5={r5:.4f}"
        )


if __name__ == "__main__":
    main()
