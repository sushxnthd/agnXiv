from __future__ import annotations

import re
from pathlib import Path

from .models import Claim, ClaimSource

_NUMBER = r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?"
_QUANT_RE = re.compile(
    rf"(?P<prefix>.{{0,90}}?)"
    rf"(?P<value>{_NUMBER})"
    rf"(?:\s*(?:±|\+/-)\s*(?P<uncertainty>{_NUMBER}))?"
    rf"\s*(?P<unit>%|percent|ms|s|seconds?|minutes?|hours?|GB|MB|KB|"
    rf"accuracy|F1|AUROC|AUC|BLEU|MAE|MSE|RMSE)?",
    flags=re.IGNORECASE,
)


def _clean_number(raw: str) -> float:
    return float(raw.replace(",", ""))


def _metric_from_context(prefix: str, unit: str | None) -> str | None:
    if unit and unit.lower() not in {"%", "percent"}:
        return unit
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]*", prefix)
    return " ".join(words[-4:]) if words else None


def extract_quantitative_claims(
    text: str,
    *,
    manuscript: str | None = None,
    page: int | None = None,
) -> list[Claim]:
    """Extract candidate numeric claims.

    This is intentionally conservative infrastructure, not the final semantic
    Claim Compiler. Later agent/model extraction can feed the same Claim schema.
    """
    claims: list[Claim] = []
    normalized = " ".join(text.split())

    for idx, match in enumerate(_QUANT_RE.finditer(normalized), start=1):
        prefix = match.group("prefix").strip()
        value = _clean_number(match.group("value"))
        uncertainty_raw = match.group("uncertainty")
        unit = match.group("unit")

        if not unit and not uncertainty_raw and value.is_integer() and 1900 <= value <= 2100:
            continue

        start = max(0, match.start() - 80)
        end = min(len(normalized), match.end() + 80)
        quote = normalized[start:end].strip()

        claims.append(
            Claim(
                id=f"C{idx:03d}",
                text=quote,
                metric=_metric_from_context(prefix, unit),
                reported_value=value / 100 if unit and unit.lower() in {"%", "percent"} else value,
                reported_uncertainty=(
                    _clean_number(uncertainty_raw) / 100
                    if uncertainty_raw and unit and unit.lower() in {"%", "percent"}
                    else _clean_number(uncertainty_raw)
                    if uncertainty_raw
                    else None
                ),
                unit="fraction" if unit and unit.lower() in {"%", "percent"} else unit,
                source=ClaimSource(
                    manuscript=manuscript,
                    page=page,
                    quote=quote,
                ),
            )
        )

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
