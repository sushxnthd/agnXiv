from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

from agnxiv.auto import rank_claim_indices_with_statement_diversity, score_claim_centrality
from agnxiv.claims import extract_quantitative_claims
from agnxiv.models import Claim

SCITLDR_COMMIT = "5ccad9c00a60ad75c9e04abf7f27d0f53f983b20"

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


def _content_tokens(text: str) -> set[str]:
    return {
        _stem(token)
        for token in re.findall(r"[a-z][a-z0-9-]{2,}", text.lower())
        if token not in _STOPWORDS
    }


def _lexical_score(anchor: set[str], claim: set[str]) -> tuple[float, int]:
    overlap = len(anchor & claim)
    if not anchor or not claim or overlap == 0:
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


def _load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid SciTLDR JSON on line {line_number}: {exc}") from exc
    return rows


def _partitioned(row: dict, *, seed: str, modulus: int, bucket: int) -> bool:
    paper_id = str(row.get("paper_id") or "").strip()
    if not paper_id:
        return False
    digest = hashlib.sha256(f"{seed}|{paper_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % modulus == bucket


def _gold_indices(
    *,
    title: str,
    author_tldr: str,
    candidates: list[tuple[int, int, Claim]],
) -> tuple[set[tuple[int, int]], str | None]:
    target_claims = extract_quantitative_claims(author_tldr)
    exact: set[tuple[int, int]] = set()

    for target_claim in target_claims:
        if target_claim.reported_value is None:
            continue
        matches = [
            (sentence_index, local_index)
            for sentence_index, local_index, claim in candidates
            if (
                claim.reported_value is not None
                and _close(
                    float(target_claim.reported_value),
                    float(claim.reported_value),
                )
                and _compatible(target_claim, claim)
            )
        ]
        if len(matches) == 1:
            exact.add(matches[0])

    if exact:
        return exact, "author_tldr_quantitative"

    anchor = _content_tokens(f"{title} {author_tldr}")
    scored: list[tuple[float, int, tuple[int, int]]] = []
    for sentence_index, local_index, claim in candidates:
        score, overlap = _lexical_score(anchor, _content_tokens(claim.text))
        scored.append((score, overlap, (sentence_index, local_index)))
    scored.sort(reverse=True)

    if not scored:
        return set(), None

    best_score, best_overlap, best_key = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0

    if (
        best_overlap >= 2
        and best_score >= 0.08
        and best_score - second_score >= 0.015
    ):
        return {best_key}, "author_tldr_lexical"

    return set(), None


def _case(row: dict) -> dict | None:
    paper_id = str(row.get("paper_id") or "").strip()
    title = str(row.get("title") or "").strip()
    source = row.get("source")
    targets = row.get("target")

    if (
        not paper_id
        or not title
        or not isinstance(source, list)
        or not isinstance(targets, list)
        or not targets
        or not isinstance(targets[0], str)
        or not targets[0].strip()
    ):
        return None

    author_tldr = targets[0].strip()
    candidates: list[tuple[int, int, Claim]] = []
    for sentence_index, sentence in enumerate(source):
        if not isinstance(sentence, str):
            continue
        for local_index, claim in enumerate(extract_quantitative_claims(sentence)):
            candidates.append((sentence_index, local_index, claim))

    if len(candidates) < 2:
        return None

    gold, method = _gold_indices(
        title=title,
        author_tldr=author_tldr,
        candidates=candidates,
    )
    if not gold or method is None:
        return None

    denominator = max(1, len(source) - 1)
    scores = [
        score_claim_centrality(
            claim,
            document_position=sentence_index / denominator,
        )
        for sentence_index, _, claim in candidates
    ]
    order = rank_claim_indices_with_statement_diversity(
        [claim for _, _, claim in candidates],
        scores,
    )
    ranked = [candidates[index] for index in order]
    ranks = {
        (sentence_index, local_index): rank
        for rank, (sentence_index, local_index, _) in enumerate(ranked, start=1)
    }
    gold_ranks = sorted(ranks[key] for key in gold if key in ranks)
    if not gold_ranks:
        return None

    first = gold_ranks[0]
    return {
        "paper_id": paper_id,
        "title": title,
        "author_tldr": author_tldr,
        "candidate_claims": len(candidates),
        "gold_method": method,
        "gold_claims": len(gold_ranks),
        "gold_ranks": gold_ranks,
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
    parser.add_argument("--min-recall-at-3", type=float, default=0.90)
    parser.add_argument("--min-recall-at-5", type=float, default=0.95)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.hash_modulus < 1:
        raise ValueError("hash-modulus must be >= 1")
    if not 0 <= args.hash_bucket < args.hash_modulus:
        raise ValueError("hash-bucket must be in [0, hash-modulus)")

    rows = [
        row
        for row in _load_rows(Path(args.input))
        if _partitioned(
            row,
            seed=args.hash_seed,
            modulus=args.hash_modulus,
            bucket=args.hash_bucket,
        )
    ]
    cases = [case for row in rows if (case := _case(row)) is not None]
    total = len(cases)

    recall_at_1 = sum(bool(case["recall_at_1"]) for case in cases) / total if total else 0.0
    recall_at_3 = sum(bool(case["recall_at_3"]) for case in cases) / total if total else 0.0
    recall_at_5 = sum(bool(case["recall_at_5"]) for case in cases) / total if total else 0.0
    mrr = (
        sum(1.0 / int(case["first_gold_rank"]) for case in cases) / total
        if total
        else 0.0
    )
    ndcg_at_5 = (
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
    for case in cases:
        key = str(case["gold_method"])
        methods[key] = methods.get(key, 0) + 1

    passed = (
        total >= args.minimum_cases
        and recall_at_3 >= args.min_recall_at_3
        and recall_at_5 >= args.min_recall_at_5
    )

    report = {
        "schema_version": "agnxiv.scitldr-author-centrality/1",
        "evaluation_role": "heldout_external_author_tldr",
        "source": {
            "dataset": "SciTLDR-AIC",
            "repository": "allenai/scitldr",
            "commit": SCITLDR_COMMIT,
            "input": str(args.input),
            "gold_signal": "target[0] author TLDR",
            "hash_seed": args.hash_seed,
            "hash_modulus": args.hash_modulus,
            "hash_bucket": args.hash_bucket,
        },
        "eligibility": (
            "At least two quantitative source claims plus one uniquely mapped "
            "author-TLDR gold claim. Gold mapping prefers unique quantitative "
            "value matches; lexical fallback requires >=2 shared content tokens, "
            "F1 >=0.08, and margin >=0.015. Centrality scores are never consulted "
            "while constructing gold."
        ),
        "source_rows_after_partition": len(rows),
        "cases": total,
        "gold_methods": dict(sorted(methods.items())),
        "recall_at_1": recall_at_1,
        "recall_at_3": recall_at_3,
        "recall_at_5": recall_at_5,
        "mean_reciprocal_rank": mrr,
        "mean_ndcg_at_5": ndcg_at_5,
        "thresholds": {
            "minimum_cases": args.minimum_cases,
            "min_recall_at_3": args.min_recall_at_3,
            "min_recall_at_5": args.min_recall_at_5,
        },
        "passed": passed,
        "cases_detail": cases,
        "interpretation": (
            "This measures whether AgnXiv routes author-salient quantitative "
            "claims into its multi-claim verification slate. Recall@1 is "
            "diagnostic; production release is gated on Recall@3 and Recall@5."
        ),
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))

    if not passed:
        raise SystemExit(
            "SciTLDR author-TLDR centrality gate failed: "
            f"n={total}, R@1={recall_at_1:.4f}, "
            f"R@3={recall_at_3:.4f}, R@5={recall_at_5:.4f}"
        )


if __name__ == "__main__":
    main()
