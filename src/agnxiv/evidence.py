from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from .models import Claim, EvidenceRef

TEXT_EXTENSIONS = {
    ".py", ".r", ".jl", ".m", ".sh", ".yaml", ".yml", ".json", ".toml",
    ".csv", ".tsv", ".txt", ".md", ".tex",
}
IGNORE_DIRS = {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__"}


class EvidenceCandidate(BaseModel):
    ref: EvidenceRef
    score: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text)
        if token.lower() not in {"the", "and", "for", "with", "from", "this", "that"}
    }


def map_claim_to_repository(
    claim: Claim,
    repository: str | Path,
    *,
    limit: int = 10,
) -> list[EvidenceCandidate]:
    """Rank repository files/lines that may produce or encode a claim.

    Reported values may be used here only as retrieval hints. They are never
    used by the output parser to choose the observation that determines a
    verification verdict.
    """
    root = Path(repository)
    if not root.is_dir():
        raise ValueError(f"repository path is not a directory: {root}")

    claim_tokens = _tokens(" ".join(filter(None, [claim.text, claim.metric])))
    numeric_forms: set[str] = set()
    if claim.reported_value is not None:
        value = claim.reported_value
        numeric_forms.update({str(value), f"{value:.3f}", f"{value:.4f}", f"{value:.6g}"})
        if claim.unit == "fraction" and 0 <= value <= 1:
            numeric_forms.update({f"{value * 100:.1f}", f"{value * 100:.2f}"})

    candidates: list[EvidenceCandidate] = []

    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if any(part in IGNORE_DIRS for part in path.parts):
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        path_tokens = _tokens(str(path.relative_to(root)))
        for line_no, line in enumerate(text.splitlines(), start=1):
            line_tokens = _tokens(line)
            token_overlap = len(claim_tokens & (line_tokens | path_tokens))
            numeric_hits = sum(form in line for form in numeric_forms if form)

            score = 0.0
            reasons: list[str] = []

            if token_overlap:
                score += min(0.6, 0.12 * token_overlap)
                reasons.append(f"{token_overlap} semantic token matches")

            if numeric_hits:
                score += min(0.7, 0.35 * numeric_hits)
                reasons.append(f"{numeric_hits} claim-value retrieval hints")

            if path.suffix.lower() in {".py", ".r", ".jl", ".m", ".sh"} and score:
                score += 0.1
                reasons.append("executable source")

            if score <= 0:
                continue

            candidates.append(
                EvidenceCandidate(
                    ref=EvidenceRef(path=f"{path.relative_to(root)}:{line_no}"),
                    score=min(score, 1.0),
                    reasons=reasons,
                )
            )

    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates[:limit]
