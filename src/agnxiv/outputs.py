from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .models import Claim, Observation

_NUMBER_RE = re.compile(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?:[eE][-+]?\d+)?")


class ObservationCandidate(BaseModel):
    observation: Observation
    raw_value: float
    normalized_value: float
    line: str
    line_number: int = Field(ge=1)
    score: float = Field(ge=0.0, le=1.0)
    rationale: list[str] = Field(default_factory=list)


def _metric_tokens(metric: str | None) -> set[str]:
    if not metric:
        return set()
    return {part.lower() for part in re.findall(r"[A-Za-z][A-Za-z0-9_-]*", metric)}


def extract_observation_candidates(
    output: str,
    claim: Claim,
    *,
    limit: int = 10,
) -> list[ObservationCandidate]:
    """Rank numeric outputs that could instantiate a claim."""
    metric_tokens = _metric_tokens(claim.metric)
    candidates: list[ObservationCandidate] = []

    for line_number, line in enumerate(output.splitlines(), start=1):
        line_lower = line.lower()
        metric_hits = sum(token in line_lower for token in metric_tokens)

        for match in _NUMBER_RE.finditer(line):
            raw = float(match.group(0).replace(",", ""))
            normalized = raw
            percent_window = line[max(0, match.end() - 2) : match.end() + 2]
            percent_like = "%" in percent_window
            if claim.unit == "fraction" and percent_like:
                normalized = raw / 100.0

            score = 0.05
            rationale: list[str] = []

            if metric_hits:
                score += min(0.55, 0.18 * metric_hits)
                rationale.append(f"{metric_hits} metric-token matches")

            if claim.reported_value is not None:
                scale = max(abs(claim.reported_value), 1e-12)
                relative_distance = abs(normalized - claim.reported_value) / scale
                if relative_distance <= 0.001:
                    score += 0.38
                    rationale.append("extremely close to reported value")
                elif relative_distance <= 0.01:
                    score += 0.28
                    rationale.append("close to reported value")
                elif relative_distance <= 0.05:
                    score += 0.16
                    rationale.append("plausibly close to reported value")

            if percent_like and claim.unit == "fraction":
                score += 0.08
                rationale.append("percent output matches fractional claim unit")

            candidates.append(
                ObservationCandidate(
                    observation=Observation(value=normalized),
                    raw_value=raw,
                    normalized_value=normalized,
                    line=line.strip(),
                    line_number=line_number,
                    score=min(score, 1.0),
                    rationale=rationale,
                )
            )

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:limit]


def select_unambiguous_observation(
    candidates: list[ObservationCandidate],
    *,
    minimum_score: float = 0.45,
    minimum_margin: float = 0.12,
) -> Observation | None:
    """Select only when the best output is strong and clearly better than alternatives."""
    if not candidates:
        return None
    best = candidates[0]
    if best.score < minimum_score:
        return None
    if len(candidates) > 1 and best.score - candidates[1].score < minimum_margin:
        return None
    return best.observation
