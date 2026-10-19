from __future__ import annotations

import json
import math
import re
from typing import Any

from pydantic import BaseModel, Field

from .models import Claim, Observation

_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_])[-+]?\d+(?:,\d{3})*(?:\.\d+)?"
    r"(?:[eE][-+]?\d+)?(?![A-Za-z0-9_])"
)

_MAX_REGEX_PATTERN_CHARS = 1024
_REPEAT_OPS = {
    re._constants.MAX_REPEAT,
    re._constants.MIN_REPEAT,
    re._constants.POSSESSIVE_REPEAT,
}
_UNSAFE_REGEX_OPS = {
    re._constants.ASSERT,
    re._constants.ASSERT_NOT,
    re._constants.GROUPREF,
}


def _regex_tree_contains(subpattern: Any, targets: set[Any]) -> bool:
    for op, arg in subpattern:
        if op in targets:
            return True
        if op is re._constants.SUBPATTERN:
            if _regex_tree_contains(arg[-1], targets):
                return True
        elif op is re._constants.BRANCH:
            if any(_regex_tree_contains(branch, targets) for branch in arg[1]):
                return True
        elif op in _REPEAT_OPS:
            if _regex_tree_contains(arg[2], targets):
                return True
    return False


def safe_regex_pattern(pattern: str) -> bool:
    """Accept a conservative regex subset suitable for trusted output parsing."""
    if not pattern or len(pattern) > _MAX_REGEX_PATTERN_CHARS or "\x00" in pattern:
        return False
    try:
        parsed = re._parser.parse(pattern, re.MULTILINE)
        compiled = re.compile(pattern, flags=re.MULTILINE)
    except (re.error, OverflowError):
        return False

    if compiled.groups != 1:
        return False
    if compiled.groupindex and set(compiled.groupindex) != {"value"}:
        return False

    def validate(subpattern: Any) -> bool:
        for op, arg in subpattern:
            if op in _UNSAFE_REGEX_OPS:
                return False
            if op is re._constants.GROUPREF_EXISTS:
                return False
            if op is re._constants.SUBPATTERN:
                if not validate(arg[-1]):
                    return False
            elif op is re._constants.BRANCH:
                if not all(validate(branch) for branch in arg[1]):
                    return False
            elif op in _REPEAT_OPS:
                minimum, maximum, child = arg
                if maximum != re._constants.MAXREPEAT and maximum > 10_000:
                    return False
                if maximum == re._constants.MAXREPEAT and (
                    _regex_tree_contains(child, _REPEAT_OPS)
                    or _regex_tree_contains(child, {re._constants.BRANCH})
                ):
                    return False
                if not validate(child):
                    return False
        return True

    return validate(parsed)


_METRIC_ALIASES: dict[str, set[str]] = {
    "accuracy": {
        "accuracy",
        "acc",
        "top1",
        "top-1",
        "cas",
        "classification accuracy score",
    },
    "f1": {"f1", "f1_score", "f1-score", "f1 score"},
    "auroc": {"auroc", "roc_auc", "roc-auc", "roc auc"},
    "auc": {"auc"},
    "mae": {"mae", "mean_absolute_error", "mean absolute error"},
    "mse": {"mse", "mean_squared_error", "mean squared error"},
    "rmse": {"rmse", "root_mean_squared_error", "root mean squared error"},
    "bleu": {"bleu", "bleu-4", "bleu4"},
    "latency": {"latency", "inference latency"},
    "runtime": {"runtime", "run time", "execution time"},
    "throughput": {"throughput", "samples/s", "samples per second"},
    "p_value": {"p_value", "p-value", "p value"},
}

_SPLIT_QUALIFIERS = {"test", "validation", "train"}
_SUMMARY_QUALIFIERS = {"mean", "median", "p90", "p95", "p99", "best"}


class ObservationCandidate(BaseModel):
    observation: Observation
    raw_value: float
    normalized_value: float
    line: str
    line_number: int = Field(ge=1)
    score: float = Field(ge=0.0, le=1.0)
    rationale: list[str] = Field(default_factory=list)


def _metric_aliases(metric: str | None) -> set[str]:
    if not metric:
        return set()

    canonical = metric.lower()
    aliases = {canonical}
    aliases.update(_METRIC_ALIASES.get(canonical, set()))
    return aliases


def _contains_alias(text: str, alias: str) -> bool:
    return bool(
        re.search(
            rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])",
            text,
            flags=re.IGNORECASE,
        )
    )


def _metric_matches(text: str, metric: str | None) -> set[str]:
    return {
        alias
        for alias in _metric_aliases(metric)
        if _contains_alias(text, alias)
    }


def _local_key_before_number(line: str, start: int) -> str | None:
    prefix = line[:start]
    match = re.search(
        r"([A-Za-z][A-Za-z0-9_/@-]*"
        r"(?:\s+[A-Za-z][A-Za-z0-9_/@-]*){0,4})\s*[:=]\s*$",
        prefix,
    )
    return match.group(1).strip() if match else None


def _looks_like_metric_label_number(line: str, match: re.Match[str]) -> bool:
    start = match.start()
    end = match.end()

    if start < 2 or line[start - 1] != "-" or not line[start - 2].isalnum():
        return False

    suffix = line[end:]
    return bool(
        re.match(
            r"(?:\s+[A-Za-z][A-Za-z0-9_-]*){0,3}\s*[:=]",
            suffix,
        )
    )


def _numeric_matches(line: str) -> list[re.Match[str]]:
    return [
        match
        for match in _NUMBER_RE.finditer(line)
        if not _looks_like_metric_label_number(line, match)
    ]


def _claim_qualifiers(claim: Claim) -> set[str]:
    lower = claim.text.lower()
    qualifiers: set[str] = set()

    if re.search(r"\btest\b|\bheld[- ]out\b", lower):
        qualifiers.add("test")
    if re.search(r"\bvalidation\b|\bval(?:idation)?\s+(?:set|split|fold|mae|loss)\b", lower):
        qualifiers.add("validation")
    if re.search(r"\btrain(?:ing)?\b", lower):
        qualifiers.add("train")

    if claim.metric not in {"mae", "mse", "rmse"} and re.search(r"\bmean\b", lower):
        qualifiers.add("mean")
    if re.search(r"\bmedian\b", lower):
        qualifiers.add("median")
    if re.search(r"\bp(?:90|95|99)\b", lower):
        qualifiers.update(re.findall(r"\bp(?:90|95|99)\b", lower))
    if re.search(r"\bbest\b", lower):
        qualifiers.add("best")

    return qualifiers


def _line_qualifiers(line: str) -> set[str]:
    lower = line.lower()
    qualifiers: set[str] = set()

    if re.search(r"\btest\b|(?:^|[/_])test(?:[/_:]|$)", lower):
        qualifiers.add("test")
    if re.search(r"\bvalidation\b|(?:^|[/_])val(?:[/_:]|$)", lower):
        qualifiers.add("validation")
    if re.search(r"\btrain(?:ing)?\b|(?:^|[/_])train(?:[/_:]|$)", lower):
        qualifiers.add("train")
    if re.search(r"\bmean\b", lower):
        qualifiers.add("mean")
    if re.search(r"\bmedian\b", lower):
        qualifiers.add("median")
    qualifiers.update(re.findall(r"\bp(?:90|95|99)\b", lower))
    if re.search(r"\bbest\b", lower):
        qualifiers.add("best")
    if re.search(r"\bseed\s*\d*\b", lower):
        qualifiers.add("seed")

    return qualifiers


def _qualifier_adjustment(
    claim_qualifiers: set[str],
    line_qualifiers: set[str],
) -> tuple[float, list[str]]:
    score = 0.0
    rationale: list[str] = []

    matches = claim_qualifiers & line_qualifiers
    if matches:
        score += 0.22 * len(matches)
        rationale.append("claim qualifier match: " + ", ".join(sorted(matches)))

    claim_splits = claim_qualifiers & _SPLIT_QUALIFIERS
    line_splits = line_qualifiers & _SPLIT_QUALIFIERS
    if claim_splits and line_splits and not (claim_splits & line_splits):
        score -= 0.24
        rationale.append("conflicting data split")

    claim_summaries = claim_qualifiers & _SUMMARY_QUALIFIERS
    line_summaries = line_qualifiers & _SUMMARY_QUALIFIERS
    if claim_summaries and line_summaries and not (claim_summaries & line_summaries):
        score -= 0.24
        rationale.append("conflicting summary statistic")

    if "mean" in claim_qualifiers and "seed" in line_qualifiers:
        score -= 0.12
        rationale.append("per-seed value for mean claim")

    return score, rationale


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
    normalized = float(value) * scale
    if not math.isfinite(normalized):
        return None

    return Observation(value=normalized)


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
    if not safe_regex_pattern(pattern):
        return None
    compiled = re.compile(pattern, flags=re.MULTILINE)

    iterator = compiled.finditer(output)
    match = next(iterator, None)
    if match is None or next(iterator, None) is not None:
        return None

    raw = (
        match.group("value")
        if "value" in compiled.groupindex
        else match.group(1)
    )

    if raw is None:
        return None

    try:
        value = float(raw.replace(",", "").strip())
    except ValueError:
        return None
    normalized = value * scale
    if not math.isfinite(normalized):
        return None

    return Observation(value=normalized)


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
    claim_qualifiers = _claim_qualifiers(claim)
    candidates: list[ObservationCandidate] = []

    for line_number, line in enumerate(output.splitlines(), start=1):
        line_lower = line.lower()
        line_metric_matches = _metric_matches(line, claim.metric)
        line_qualifiers = _line_qualifiers(line)
        numbers = _numeric_matches(line)

        for index, match in enumerate(numbers):
            raw = float(match.group(0).replace(",", ""))
            if not math.isfinite(raw):
                continue
            normalized = raw
            percent_window = line[max(0, match.end() - 2) : match.end() + 2]
            percent_like = "%" in percent_window
            if claim.unit == "fraction" and percent_like:
                normalized = raw / 100.0

            score = 0.02
            rationale: list[str] = []

            local_key = _local_key_before_number(line, match.start())
            local_matches = _metric_matches(local_key or "", claim.metric)

            if local_matches:
                score += min(0.62, 0.48 + 0.06 * (len(local_matches) - 1))
                rationale.append(
                    "metric bound to value key: " + ", ".join(sorted(local_matches))
                )
            elif line_metric_matches and local_key is None:
                score += min(0.46, 0.24 * len(line_metric_matches))
                rationale.append(
                    "metric labels present: " + ", ".join(sorted(line_metric_matches))
                )

            if len(numbers) == 1:
                score += 0.20
                rationale.append("only numeric value on metric line")
            elif index == 0 and local_matches:
                score += 0.04
                rationale.append("first value bound to requested metric key")

            if local_key is not None:
                score += 0.18
                rationale.append("value follows explicit key/value separator")

            if percent_like and claim.unit == "fraction":
                score += 0.10
                rationale.append("percent output matches fractional claim unit")

            qualifier_score, qualifier_reasons = _qualifier_adjustment(
                claim_qualifiers,
                line_qualifiers,
            )
            score += qualifier_score
            rationale.extend(qualifier_reasons)

            negative_cues = {
                cue
                for cue in (
                    "target",
                    "expected",
                    "claimed",
                    "reference",
                    "reported",
                    "paper value",
                )
                if cue in line_lower
            }
            if negative_cues:
                score -= 0.28
                rationale.append(
                    "non-observation cue present: " + ", ".join(sorted(negative_cues))
                )

            positive_cues = {
                cue
                for cue in ("observed", "measured", "result", "evaluation", "eval")
                if cue in line_lower
            }
            if positive_cues and not negative_cues:
                score += 0.16
                rationale.append(
                    "observation cue present: " + ", ".join(sorted(positive_cues))
                )

            candidates.append(
                ObservationCandidate(
                    observation=Observation(value=normalized),
                    raw_value=raw,
                    normalized_value=normalized,
                    line=line.strip(),
                    line_number=line_number,
                    score=min(max(score, 0.0), 1.0),
                    rationale=rationale,
                )
            )

    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
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
