from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Literal

from pydantic import BaseModel, Field


class ResearchCase(BaseModel):
    schema_version: Literal["agnxiv.research-case/1"] = "agnxiv.research-case/1"
    case_id: str
    source_suite: str
    source_task_id: str | None = None
    paper_url: str
    paper_url_versioned: str | None = None
    paper_alternate_urls: list[str] = Field(default_factory=list)
    repository: str | None = None
    commit: str | None = None
    origin_url: str | None = None
    known_public_ground_truth: bool = False
    evaluation_role: Literal[
        "diagnostic_nonblind", "development", "heldout_blind", "external"
    ] = "development"
    tracks: list[str] = Field(default_factory=list)
    status: Literal["queued", "running", "complete", "blocked"] = "queued"


class SelectiveOutcome(BaseModel):
    case_id: str
    gold_supports_claim: bool
    predicted: Literal["SUPPORTS", "DIVERGES", "ABSTAIN"]


class SelectiveMetrics(BaseModel):
    cases: int
    decided: int
    coverage: float
    support_predictions: int
    divergence_predictions: int
    false_pass_eligible: int
    false_divergence_eligible: int
    false_passes: int
    false_divergences: int
    false_pass_rate: float
    false_divergence_rate: float
    false_pass_upper_95: float
    false_divergence_upper_95: float
    selective_error_rate: float


def binomial_upper_bound_95(events: int, trials: int) -> float:
    """One-sided 95% upper bound for a Bernoulli error rate.

    The zero-event case uses the exact Clopper-Pearson bound. Non-zero cases
    use a one-sided Wilson score upper bound. With no trials, return 1.0:
    absence of decisions is not evidence of safety.
    """
    if trials < 0 or events < 0 or events > trials:
        raise ValueError("events/trials must satisfy 0 <= events <= trials")
    if trials == 0:
        return 1.0
    alpha = 0.05
    if events == 0:
        return 1.0 - alpha ** (1.0 / trials)

    p_hat = events / trials
    z = NormalDist().inv_cdf(1.0 - alpha)
    z2 = z * z
    denominator = 1.0 + z2 / trials
    center = (p_hat + z2 / (2.0 * trials)) / denominator
    spread = (
        z
        / denominator
        * math.sqrt(
            p_hat * (1.0 - p_hat) / trials
            + z2 / (4.0 * trials * trials)
        )
    )
    return min(1.0, center + spread)


def minimum_zero_event_sample_size(
    *,
    target_rate: float,
    confidence: float = 0.95,
) -> int:
    """Independent zero-error decisions needed to bound rate below target."""
    if not (0.0 < target_rate < 1.0):
        raise ValueError("target_rate must be between 0 and 1")
    if not (0.0 < confidence < 1.0):
        raise ValueError("confidence must be between 0 and 1")
    alpha = 1.0 - confidence
    return math.ceil(math.log(alpha) / math.log(1.0 - target_rate))


def score_selective_verification(outcomes: list[SelectiveOutcome]) -> SelectiveMetrics:
    cases = len(outcomes)
    decided_rows = [row for row in outcomes if row.predicted != "ABSTAIN"]
    decided = len(decided_rows)
    false_passes = sum(
        row.predicted == "SUPPORTS" and not row.gold_supports_claim
        for row in decided_rows
    )
    false_divergences = sum(
        row.predicted == "DIVERGES" and row.gold_supports_claim
        for row in decided_rows
    )
    errors = false_passes + false_divergences

    support_predictions = sum(row.predicted == "SUPPORTS" for row in decided_rows)
    divergence_predictions = sum(row.predicted == "DIVERGES" for row in decided_rows)

    # A false pass is a positive verifier decision on a case whose gold label
    # does not support the claim. The statistical denominator must therefore
    # be the number of gold-negative opportunities, not the number of positive
    # predictions. Otherwise a conservative verifier that correctly abstains
    # or diverges on every negative case would have zero statistical evidence.
    false_pass_eligible = sum(not row.gold_supports_claim for row in outcomes)
    false_divergence_eligible = sum(row.gold_supports_claim for row in outcomes)

    return SelectiveMetrics(
        cases=cases,
        decided=decided,
        coverage=(decided / cases) if cases else 0.0,
        support_predictions=support_predictions,
        divergence_predictions=divergence_predictions,
        false_pass_eligible=false_pass_eligible,
        false_divergence_eligible=false_divergence_eligible,
        false_passes=false_passes,
        false_divergences=false_divergences,
        false_pass_rate=(false_passes / false_pass_eligible)
        if false_pass_eligible
        else 0.0,
        false_divergence_rate=(false_divergences / false_divergence_eligible)
        if false_divergence_eligible
        else 0.0,
        false_pass_upper_95=binomial_upper_bound_95(
            false_passes,
            false_pass_eligible,
        ),
        false_divergence_upper_95=binomial_upper_bound_95(
            false_divergences,
            false_divergence_eligible,
        ),
        selective_error_rate=(errors / decided) if decided else 0.0,
    )


def load_research_cases(path: str | Path) -> list[ResearchCase]:
    rows: list[ResearchCase] = []
    for line_number, raw in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw.strip():
            continue
        try:
            rows.append(ResearchCase.model_validate(json.loads(raw)))
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(
                f"invalid research case on line {line_number}: {exc}"
            ) from exc
    return rows


class EvidenceDependency(BaseModel):
    left_attempt: str
    right_attempt: str
    shared_factors: list[
        Literal[
            "author_code",
            "derived_code",
            "checkpoint",
            "data_split",
            "preprocessing",
            "environment",
        ]
    ] = Field(min_length=1)


class IndependenceSummary(BaseModel):
    attempts: int
    dependency_edges: int
    independent_components: int
    components: list[list[str]]


def summarize_evidence_independence(
    attempt_ids: list[str],
    dependencies: list[EvidenceDependency],
) -> IndependenceSummary:
    parent = {attempt_id: attempt_id for attempt_id in attempt_ids}

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for dependency in dependencies:
        if dependency.left_attempt not in parent or dependency.right_attempt not in parent:
            raise ValueError("dependency references an unknown attempt")
        union(dependency.left_attempt, dependency.right_attempt)

    groups: dict[str, list[str]] = {}
    for attempt_id in attempt_ids:
        groups.setdefault(find(attempt_id), []).append(attempt_id)

    components = sorted(
        (sorted(group) for group in groups.values()),
        key=lambda group: group[0] if group else "",
    )
    return IndependenceSummary(
        attempts=len(attempt_ids),
        dependency_edges=len(dependencies),
        independent_components=len(components),
        components=components,
    )


class CentralityGold(BaseModel):
    case_id: str
    required_substrings: list[str] = Field(min_length=1)
    rationale: str


class CentralityResult(BaseModel):
    case_id: str
    first_gold_rank: int | None
    recall_at_1: bool
    recall_at_3: bool
    recall_at_5: bool


def _normalize_centrality_text(value: str) -> str:
    return " ".join(value.lower().replace(",", "").split())


def score_centrality_ranking(
    case_id: str,
    ranked_claim_texts: list[str],
    gold: CentralityGold,
) -> CentralityResult:
    if gold.case_id != case_id:
        raise ValueError("centrality gold case does not match evaluated case")

    required = [_normalize_centrality_text(item) for item in gold.required_substrings]
    first_rank: int | None = None
    for rank, text in enumerate(ranked_claim_texts, start=1):
        normalized = _normalize_centrality_text(text)
        if all(item in normalized for item in required):
            first_rank = rank
            break

    return CentralityResult(
        case_id=case_id,
        first_gold_rank=first_rank,
        recall_at_1=first_rank == 1,
        recall_at_3=first_rank is not None and first_rank <= 3,
        recall_at_5=first_rank is not None and first_rank <= 5,
    )


def load_centrality_gold(path: str | Path) -> dict[str, CentralityGold]:
    rows: dict[str, CentralityGold] = {}
    for line_number, raw in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw.strip():
            continue
        try:
            item = CentralityGold.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(
                f"invalid centrality gold row on line {line_number}: {exc}"
            ) from exc
        if item.case_id in rows:
            raise ValueError(f"duplicate centrality gold case: {item.case_id}")
        rows[item.case_id] = item
    return rows
