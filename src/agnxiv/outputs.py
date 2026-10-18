from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from .models import Claim, Observation

_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_])[-+]?\d+(?:,\d{3})*(?:\.\d+)?"
    r"(?:[eE][-+]?\d+)?(?![A-Za-z0-9_])"
)

_METRIC_ALIASES: dict[str, set[str]] = {
    "accuracy": {"accuracy", "acc", "top1", "top-1"},
    "f1": {"f1", "f1_score", "f1-score"},
    "auroc": {"auroc", "roc_auc", "roc-auc"},
    "auc": {"auc"},
    "mae": {"mae", "mean_absolute_error"},
    "mse": {"mse", "mean_squared_error"},
    "rmse": {"rmse", "root_mean_squared_error"},
    "bleu": {"bleu"},
}


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

    raw_tokens = {
        part.lower()
        for part in re.findall(r"[A-Za-z][A-Za-z0-9_-]*", metric)
    }
    expanded = set(raw_tokens)
    for token in raw_tokens:
        expanded.update(_METRIC_ALIASES.get(token, set()))
    return expanded


def _parse_json_payload(output: str) -> Any | None:
    stripped = output.strip()
    if not stripped:
        return None

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return None

    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return None


def extract_json_observation(
    output: str,
    path: str,
    *,
    scale: float = 1.0,
) -> Observation | None:
    """Read a numeric observation from an explicit JSON path.

    The path uses dot-separated keys and integer list indices, such as
    metrics.accuracy or runs.0.f1. The locator is declared before comparison,
    so the paper's reported value cannot influence selection.
    """
    payload = _parse_json_payload(output)
    if payload is None:
        return None

    current: Any = payload
    normalized_path = path.removeprefix("$.").removeprefix("$")

    if not normalized_path:
        value = current
    else:
        for part in normalized_path.split("."):
            if isinstance(current, dict):
                if part not in current:
                    return None
                current = current[part]
            elif isinstance(current, list):
                try:
                    index = int(part)
                except ValueError:
                    return None
                if not 0 <= index < len(current):
                    return None
                current = current[index]
            else:
                return None
        value = current

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None

    return Observation(value=float(value) * scale)


def extract_regex_observation(
    output: str,
    pattern: str,
    *,
    scale: float = 1.0,
) -> Observation | None:
    """Read one numeric observation from one explicit regex match.

    The regex must either contain exactly one capture group or a named capture
    group called value. Multiple matches are rejected as ambiguous.
    """
    try:
        compiled = re.compile(pattern, flags=re.MULTILINE)
    except re.error:
        return None

    matches = list(compiled.finditer(output))
    if len(matches) != 1:
        return None

    match = matches[0]
    if "value" in compiled.groupindex:
        raw = match.group("value")
    elif compiled.groups == 1:
        raw = match.group(1)
    else:
        return None

    if raw is None:
        return None

    try:
        value = float(raw.replace(",", "").strip())
    except ValueError:
        return None

    return Observation(value=value * scale)


def extract_observation_candidates(
    output: str,
    claim: Claim,
    *,
    limit: int = 10,
) -> list[ObservationCandidate]:
    """Rank numeric outputs by structural/semantic evidence only.

    The paper's reported numeric value is deliberately not used to choose an
    observation. This prevents answer-guided selection.
    """
    metric_tokens = _metric_tokens(claim.metric)
    candidates: list[ObservationCandidate] = []

    for line_number, line in enumerate(output.splitlines(), start=1):
        line_lower = line.lower()
        matched_tokens = {token for token in metric_tokens if token in line_lower}
        metric_hits = len(matched_tokens)
        numbers = list(_NUMBER_RE.finditer(line))

        for index, match in enumerate(numbers):
            raw = float(match.group(0).replace(",", ""))
            normalized = raw
            percent_window = line[max(0, match.end() - 2) : match.end() + 2]
            percent_like = "%" in percent_window
            if claim.unit == "fraction" and percent_like:
                normalized = raw / 100.0

            score = 0.02
            rationale: list[str] = []

            if metric_hits:
                score += min(0.62, 0.24 * metric_hits)
                rationale.append(
                    "metric labels present: " + ", ".join(sorted(matched_tokens))
                )

            if len(numbers) == 1:
                score += 0.20
                rationale.append("only numeric value on metric line")
            elif index == 0 and metric_hits:
                score += 0.08
                rationale.append("first numeric value on labeled metric line")

            if re.search(r"[:=]\s*" + re.escape(match.group(0)), line):
                score += 0.18
                rationale.append("value follows explicit key/value separator")

            if percent_like and claim.unit == "fraction":
                score += 0.10
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
