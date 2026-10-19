from __future__ import annotations

import json
import math
from statistics import NormalDist
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class SafetyDecision(BaseModel):
    schema_version: Literal["agnxiv.safety-decision/1"] = "agnxiv.safety-decision/1"
    case_id: str = Field(min_length=1)
    independence_key: str = Field(min_length=1)
    ground_truth: Literal["supports", "not_supports"]
    decision: Literal["supports", "contradicts", "abstain"]
    source: str = Field(min_length=1)


class FalsePassConfidenceReport(BaseModel):
    schema_version: Literal["agnxiv.false-pass-confidence/1"] = (
        "agnxiv.false-pass-confidence/1"
    )
    cases: int
    supports_decisions: int
    correct_supports: int
    false_passes: int
    unique_support_independence_keys: int
    independent_supports: bool
    one_sided_confidence: float
    zero_false_pass_upper_bound: float | None
    one_sided_upper_bound: float | None
    target_upper_bound: float
    minimum_zero_error_supports: int
    production_pass: bool


def minimum_zero_error_sample(
    *,
    target_upper_bound: float = 0.01,
    alpha: float = 0.05,
) -> int:
    """Exact n needed so zero errors has one-sided upper bound <= target."""
    if not 0.0 < target_upper_bound < 1.0:
        raise ValueError("target_upper_bound must be between zero and one")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between zero and one")
    return math.ceil(math.log(alpha) / math.log(1.0 - target_upper_bound))


def load_safety_decisions(path: str | Path) -> list[SafetyDecision]:
    rows: list[SafetyDecision] = []
    seen_case_ids: set[str] = set()
    for number, raw in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw.strip():
            continue
        try:
            row = SafetyDecision.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"invalid safety decision on line {number}: {exc}") from exc
        if row.case_id in seen_case_ids:
            raise ValueError(f"duplicate safety case_id: {row.case_id}")
        seen_case_ids.add(row.case_id)
        rows.append(row)
    return rows


def false_pass_confidence(
    rows: list[SafetyDecision],
    *,
    target_upper_bound: float = 0.01,
    alpha: float = 0.05,
) -> FalsePassConfidenceReport:
    supports = [row for row in rows if row.decision == "supports"]
    false_passes = sum(row.ground_truth != "supports" for row in supports)
    correct = len(supports) - false_passes
    keys = {row.independence_key for row in supports}
    independent = len(keys) == len(supports)

    upper: float | None = None
    zero_error_upper: float | None = None
    if supports and false_passes == 0:
        # Exact Clopper-Pearson one-sided upper confidence limit when x=0:
        # P(X=0 | p)=(1-p)^n=alpha.
        zero_error_upper = 1.0 - alpha ** (1.0 / len(supports))
        upper = zero_error_upper
    elif supports:
        # One-sided Wilson score upper bound. This remains defined after a
        # false pass, so monitoring and release reports cannot drop uncertainty
        # exactly when the verifier becomes unsafe.
        n = len(supports)
        phat = false_passes / n
        z = NormalDist().inv_cdf(1.0 - alpha)
        z2 = z * z
        denominator = 1.0 + z2 / n
        centre = phat + z2 / (2.0 * n)
        radius = z * math.sqrt(
            phat * (1.0 - phat) / n + z2 / (4.0 * n * n)
        )
        upper = min(1.0, (centre + radius) / denominator)

    required = minimum_zero_error_sample(
        target_upper_bound=target_upper_bound,
        alpha=alpha,
    )
    production_pass = bool(
        independent
        and false_passes == 0
        and upper is not None
        and upper <= target_upper_bound
        and len(supports) >= required
    )
    return FalsePassConfidenceReport(
        cases=len(rows),
        supports_decisions=len(supports),
        correct_supports=correct,
        false_passes=false_passes,
        unique_support_independence_keys=len(keys),
        independent_supports=independent,
        one_sided_confidence=1.0 - alpha,
        zero_false_pass_upper_bound=zero_error_upper,
        one_sided_upper_bound=upper,
        target_upper_bound=target_upper_bound,
        minimum_zero_error_supports=required,
        production_pass=production_pass,
    )
