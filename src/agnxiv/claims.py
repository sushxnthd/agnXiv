from __future__ import annotations

import re
from pathlib import Path

from .models import Claim, ClaimSource

_NUMBER = r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?"
_QUANT_RE = re.compile(
    rf"(?P<prefix>.{{0,110}}?)"
    rf"(?P<value>{_NUMBER})"
    rf"(?:\s*(?:±|\+/-)\s*(?P<uncertainty>{_NUMBER}))?"
    rf"\s*(?P<unit>%|percent|ms|s|seconds?|minutes?|hours?|GB|MB|KB)?",
    flags=re.IGNORECASE,
)

_METRICS: dict[str, tuple[str, ...]] = {
    "accuracy": ("accuracy", "acc", "top-1", "top1"),
    "precision": ("precision",),
    "recall": ("recall",),
    "f1": ("f1", "f1-score", "f1 score"),
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
    "p_value": ("p-value", "p value", "p="),
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
)


def _clean_number(raw: str) -> float:
    return float(raw.replace(",", ""))


def _metric_from_context(context: str) -> str | None:
    lower = context.lower()
    best: tuple[int, str] | None = None

    for canonical, aliases in _METRICS.items():
        for alias in aliases:
            position = lower.rfind(alias)
            if position >= 0 and (best is None or position > best[0]):
                best = (position, canonical)

    return best[1] if best else None


def _looks_material(
    *,
    context: str,
    unit: str | None,
    uncertainty_raw: str | None,
    metric: str | None,
) -> bool:
    lower = context.lower()
    if unit or uncertainty_raw or metric:
        return True
    return any(signal in lower for signal in _CLAIM_SIGNALS)


def extract_quantitative_claims(
    text: str,
    *,
    manuscript: str | None = None,
    page: int | None = None,
) -> list[Claim]:
    """Extract candidate material quantitative claims.

    This deterministic pass intentionally favors precision over recall. A later
    semantic compiler may propose additional claims, but it feeds the same Claim
    schema and cannot directly award a verification verdict.
    """
    claims: list[Claim] = []
    normalized = " ".join(text.split())

    for match in _QUANT_RE.finditer(normalized):
        value = _clean_number(match.group("value"))
        uncertainty_raw = match.group("uncertainty")
        unit = match.group("unit")

        start = max(0, match.start() - 100)
        end = min(len(normalized), match.end() + 100)
        quote = normalized[start:end].strip()
        prefix_context = normalized[start:match.start()]
        metric = _metric_from_context(prefix_context)

        if not unit and not uncertainty_raw and value.is_integer() and 1900 <= value <= 2100:
            continue

        if not _looks_material(
            context=quote,
            unit=unit,
            uncertainty_raw=uncertainty_raw,
            metric=metric,
        ):
            continue

        percent = bool(unit and unit.lower() in {"%", "percent"})
        claims.append(
            Claim(
                id="PENDING",
                text=quote,
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
