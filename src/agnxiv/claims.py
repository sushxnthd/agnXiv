from __future__ import annotations

import re
from pathlib import Path

from .models import Claim, ClaimSource

_NUMBER = (
    r"(?<![A-Za-z0-9_.])[-+]?\d+(?:,\d{3})*(?:\.\d+)?"
    r"(?:[eE][-+]?\d+)?(?![A-WYZa-wyz0-9_]|\.\d)"
)
_UNIT = (
    r"%(?!\w)|percent\b|ms\b|s\b|seconds?\b|minutes?\b|hours?\b|"
    r"GB\b|MB\b|KB\b|x\b|×(?!\d)|times?\b|fold\b"
)
_QUANT_RE = re.compile(
    rf"(?P<prefix>.{{0,110}}?)"
    rf"(?P<value>{_NUMBER})"
    rf"(?:\s*(?:±|\+/-)\s*(?P<uncertainty>{_NUMBER}))?"
    rf"\s*(?P<unit>{_UNIT})?",
    flags=re.IGNORECASE,
)

_METRICS: dict[str, tuple[str, ...]] = {
    "accuracy": ("accuracy", "acc", "top-1", "top1"),
    "precision": ("precision",),
    "recall": ("recall",),
    "f1": ("f1", "f1-score", "f1 score", "micro-f1", "macro-f1"),
    "auroc": ("auroc", "roc-auc", "roc auc"),
    "auc": ("auc",),
    "bleu": ("bleu",),
    "mae": ("mae", "mean absolute error"),
    "mse": ("mse", "mean squared error"),
    "rmse": ("rmse", "root mean squared error"),
    "loss": ("loss",),
    "latency": ("latency",),
    "runtime": ("runtime", "run time", "execution time"),
    "throughput": ("throughput",),
    "speedup": ("speedup", "speed-up"),
    "split_half_r": ("split-half r", "split-half reliability", "split half r"),
    "spearman_brown": ("spearman-brown", "spearman brown"),
    "cohens_d": ("cohen's d", "cohens d", "cohen d"),
    "p_value": ("p-value", "p value"),
}

_CLAIM_SIGNALS = (
    "achiev",
    "outperform",
    "improv",
    "reduc",
    "increase",
    "decrease",
    "significant",
    "result",
    "obtain",
    "reach",
    "report",
    "yield",
    "mean",
    "median",
    "average",
    "error",
    "score",
    "loss",
)

_LABEL_RE = re.compile(
    r"(?:figure|fig|table|algorithm|alg|equation|eq|section|sec|lines?|appendix)"
    r"\s*$",
    flags=re.IGNORECASE,
)


def _clean_number(raw: str) -> float:
    return float(raw.replace(",", ""))


def _alias_positions(context: str, alias: str) -> list[int]:
    pattern = re.compile(
        rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])",
        flags=re.IGNORECASE,
    )
    return [match.start() for match in pattern.finditer(context)]


def _metric_from_context(context: str) -> str | None:
    best: tuple[int, str] | None = None

    for canonical, aliases in _METRICS.items():
        for alias in aliases:
            positions = _alias_positions(context, alias)
            if not positions:
                continue
            position = positions[-1]
            if best is None or position > best[0]:
                best = (position, canonical)

    return best[1] if best else None


def _is_sentence_boundary(text: str, position: int) -> bool:
    marker = text[position]
    if marker in "!?":
        return True
    if marker != ".":
        return False

    previous = text[position - 1] if position > 0 else ""
    following = text[position + 1] if position + 1 < len(text) else ""
    return not (previous.isdigit() and following.isdigit())


def _sentence_context(
    text: str,
    start: int,
    end: int,
    *,
    radius: int = 160,
) -> str:
    """Return local sentence context without splitting decimal numbers."""
    left_boundary = -1
    for position in range(start - 1, -1, -1):
        if text[position] in ".!?" and _is_sentence_boundary(text, position):
            left_boundary = position
            break
    left = left_boundary + 1 if left_boundary >= 0 else 0

    right = len(text)
    for position in range(end, len(text)):
        if text[position] in ".!?" and _is_sentence_boundary(text, position):
            right = position + 1
            break

    return text[max(left, start - radius) : min(right, end + radius)].strip()


def _looks_material(
    *,
    context: str,
    unit: str | None,
    uncertainty_raw: str | None,
    metric: str | None,
) -> bool:
    if unit or uncertainty_raw or metric:
        return True

    lower = context.lower()
    return any(
        re.search(rf"\b{re.escape(signal)}\w*", lower)
        for signal in _CLAIM_SIGNALS
    )


def _looks_like_label_or_citation(
    normalized: str,
    match: re.Match[str],
) -> bool:
    start = match.start("value")
    end = match.end("value")

    if (
        start > 0
        and end < len(normalized)
        and normalized[start - 1] == "["
        and normalized[end] == "]"
    ):
        return True

    prefix = normalized[max(0, start - 40) : start]
    return bool(_LABEL_RE.search(prefix))


def extract_quantitative_claims(
    text: str,
    *,
    manuscript: str | None = None,
    page: int | None = None,
) -> list[Claim]:
    """Extract candidate material quantitative claims conservatively."""
    claims: list[Claim] = []
    normalized = " ".join(text.split())

    for match in _QUANT_RE.finditer(normalized):
        if _looks_like_label_or_citation(normalized, match):
            continue

        value = _clean_number(match.group("value"))
        uncertainty_raw = match.group("uncertainty")
        unit = match.group("unit")

        start = max(0, match.start() - 100)
        end = min(len(normalized), match.end() + 100)
        quote = normalized[start:end].strip()

        local_context = _sentence_context(
            normalized,
            match.start("value"),
            match.end("value"),
        )
        # Resolve the metric nearest *before* this number, so a sentence
        # reporting multiple statistics cannot label them all by the last one.
        preceding = normalized[max(0, match.start("value") - 100) : match.start("value")]
        metric = _metric_from_context(preceding) or _metric_from_context(local_context)

        if not unit and not uncertainty_raw and value.is_integer() and 1900 <= value <= 2100:
            continue

        if not _looks_material(
            context=local_context,
            unit=unit,
            uncertainty_raw=uncertainty_raw,
            metric=metric,
        ):
            continue

        percent = bool(unit and unit.lower() in {"%", "percent"})
        claims.append(
            Claim(
                id="PENDING",
                text=local_context,
                metric=metric,
                reported_value=value / 100 if percent else value,
                reported_uncertainty=(
                    _clean_number(uncertainty_raw) / 100
                    if uncertainty_raw and percent
                    else _clean_number(uncertainty_raw)
                    if uncertainty_raw
                    else None
                ),
                unit="fraction" if percent else unit,
                source=ClaimSource(
                    manuscript=manuscript,
                    page=page,
                    quote=quote,
                ),
            )
        )

    for idx, claim in enumerate(claims, start=1):
        claim.id = f"C{idx:03d}"

    return claims


def extract_claims_from_pdf(path: str | Path) -> list[Claim]:
    """Extract candidate quantitative claims from a PDF."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "PDF support is optional. Install with: pip install -e '.[pdf]'"
        ) from exc

    pdf_path = Path(path)
    reader = PdfReader(str(pdf_path))
    claims: list[Claim] = []

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        claims.extend(
            extract_quantitative_claims(
                text,
                manuscript=pdf_path.name,
                page=page_number,
            )
        )

    for idx, claim in enumerate(claims, start=1):
        claim.id = f"C{idx:03d}"

    return claims
