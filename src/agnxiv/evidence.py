from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from .models import Claim, EvidenceRef

TEXT_EXTENSIONS = {
    ".py", ".r", ".jl", ".m", ".sh", ".yaml", ".yml", ".json", ".toml",
    ".csv", ".tsv", ".txt", ".md", ".tex",
}
IGNORE_DIRS = {
    ".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__",
    ".tox", "site-packages",
}
AUXILIARY_DIRS = {
    "example", "examples", "docs", "doc", "notebook", "notebooks",
    "third_party", "third-party", "vendor",
}


class EvidenceCandidate(BaseModel):
    ref: EvidenceRef
    score: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class IndexedEvidenceLine:
    path: str
    line_number: int
    text: str
    line_tokens: frozenset[str]
    path_tokens: frozenset[str]
    executable_source: bool


@dataclass(frozen=True)
class RepositoryEvidenceIndex:
    root: Path
    lines: tuple[IndexedEvidenceLine, ...]
    scanned_files: int
    scanned_lines: int
    truncated: bool


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text)
        if token.lower() not in {"the", "and", "for", "with", "from", "this", "that"}
    }


def _path_priority(path: Path, root: Path) -> tuple[int, int, str]:
    relative = path.relative_to(root)
    auxiliary = int(
        any(part.lower() in AUXILIARY_DIRS for part in relative.parts[:-1])
    )
    return auxiliary, len(relative.parts), str(relative)


def build_repository_evidence_index(
    repository: str | Path,
    *,
    file_budget: int = 1200,
    line_budget: int = 150_000,
) -> RepositoryEvidenceIndex:
    """Index repository text once for repeated claim→evidence retrieval."""
    root = Path(repository)
    if not root.is_dir():
        raise ValueError(f"repository path is not a directory: {root}")

    paths: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        relative = path.relative_to(root)
        if any(part in IGNORE_DIRS for part in relative.parts):
            continue
        paths.append(path)

    paths.sort(key=lambda path: _path_priority(path, root))

    indexed: list[IndexedEvidenceLine] = []
    scanned_files = 0
    scanned_lines = 0
    truncated = False

    for path in paths:
        if scanned_files >= file_budget or scanned_lines >= line_budget:
            truncated = True
            break
        try:
            if path.stat().st_size > 2_000_000:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        scanned_files += 1
        relative = str(path.relative_to(root))
        path_tokens = frozenset(_tokens(relative))
        executable = path.suffix.lower() in {".py", ".r", ".jl", ".m", ".sh"}

        for line_number, line in enumerate(text.splitlines(), start=1):
            if scanned_lines >= line_budget:
                truncated = True
                break
            scanned_lines += 1
            line_tokens = frozenset(_tokens(line))
            if not line_tokens and not any(character.isdigit() for character in line):
                continue
            indexed.append(
                IndexedEvidenceLine(
                    path=relative,
                    line_number=line_number,
                    text=line,
                    line_tokens=line_tokens,
                    path_tokens=path_tokens,
                    executable_source=executable,
                )
            )

    return RepositoryEvidenceIndex(
        root=root,
        lines=tuple(indexed),
        scanned_files=scanned_files,
        scanned_lines=scanned_lines,
        truncated=truncated,
    )


def map_claim_to_index(
    claim: Claim,
    index: RepositoryEvidenceIndex,
    *,
    limit: int = 10,
) -> list[EvidenceCandidate]:
    """Rank indexed repository evidence for one claim."""
    claim_tokens = _tokens(" ".join(filter(None, [claim.text, claim.metric])))
    numeric_forms: set[str] = set()
    if claim.reported_value is not None:
        value = claim.reported_value
        numeric_forms.update({str(value), f"{value:.3f}", f"{value:.4f}", f"{value:.6g}"})
        if claim.unit == "fraction" and 0 <= value <= 1:
            numeric_forms.update({f"{value * 100:.1f}", f"{value * 100:.2f}"})

    candidates: list[EvidenceCandidate] = []

    for item in index.lines:
        token_overlap = len(claim_tokens & (set(item.line_tokens) | set(item.path_tokens)))
        numeric_hits = sum(form in item.text for form in numeric_forms if form)

        score = 0.0
        reasons: list[str] = []

        if token_overlap:
            score += min(0.6, 0.12 * token_overlap)
            reasons.append(f"{token_overlap} semantic token matches")

        if numeric_hits:
            score += min(0.7, 0.35 * numeric_hits)
            reasons.append(f"{numeric_hits} claim-value retrieval hints")

        if item.executable_source and score:
            score += 0.1
            reasons.append("executable source")

        if score <= 0:
            continue

        candidates.append(
            EvidenceCandidate(
                ref=EvidenceRef(path=f"{item.path}:{item.line_number}"),
                score=min(score, 1.0),
                reasons=reasons,
            )
        )

    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates[:limit]


def map_claim_to_repository(
    claim: Claim,
    repository: str | Path,
    *,
    limit: int = 10,
) -> list[EvidenceCandidate]:
    """Rank repository files/lines that may produce or encode a claim.

    This compatibility wrapper builds a bounded index once for this call.
    Multi-claim workflows should build the index once and reuse it.
    Reported values are retrieval hints only; they never select the executed
    observation used for a scientific verdict.
    """
    index = build_repository_evidence_index(repository)
    return map_claim_to_index(claim, index, limit=limit)
