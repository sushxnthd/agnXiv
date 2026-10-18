from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .research import ResearchCase


class DiscrepancyGold(BaseModel):
    case_id: str
    category: Literal[
        "algorithm_state_update",
        "implementation_scope_initialization",
        "objective_loss_masking",
        "evaluation_protocol_leakage",
    ]
    severity: Literal[
        "clarified_scope",
        "material_unclear",
        "potentially_material",
    ]
    target_summary: str
    author_response_status: Literal["none", "clarified", "community_discussion"]
    origin_url: str
    detector_visible: Literal[False] = False


class DetectorCase(BaseModel):
    case_id: str
    paper_url: str
    repository: str
    commit: str


class LocalizationGold(BaseModel):
    case_id: str
    target_path: str
    target_line_terms: list[str] = Field(default_factory=list)
    detector_visible: Literal[False] = False


class AlignmentCandidate(BaseModel):
    path: str
    line_number: int = Field(ge=1)
    code_line: str
    paper_sentence: str
    shared_tokens: list[str]
    score: float = Field(ge=0.0)


class LocalizationResult(BaseModel):
    case_id: str
    target_path: str
    first_target_path_rank: int | None
    recall_at_5: bool
    recall_at_10: bool
    recall_at_25: bool
    top_paths: list[str]


_STOPWORDS = {
    "about", "after", "again", "against", "also", "among", "because", "been",
    "before", "being", "between", "both", "could", "data", "does", "during",
    "each", "from", "have", "into", "method", "model", "more", "most", "other",
    "paper", "results", "same", "such", "than", "that", "their", "then", "there",
    "these", "they", "this", "through", "using", "were", "which", "while", "with",
    "would", "when", "where", "will", "your", "ours", "proposed", "approach",
}

_PROCEDURE_CUES = {
    "backcast", "cross", "entropy", "evaluation", "forecast", "gaussian",
    "hyperparameter", "initialization", "initialize", "loss", "mask", "masked",
    "objective", "residual", "split", "test", "training", "tuning", "update",
    "validation", "zero",
}


def detector_view(case: ResearchCase) -> DetectorCase:
    """Return the information allowed to a blind paper-code discrepancy detector."""
    if not case.repository or not case.commit:
        raise ValueError("detector case requires repository and pinned commit")
    paper_url = case.paper_url_versioned or case.paper_url
    return DetectorCase(
        case_id=case.case_id,
        paper_url=paper_url,
        repository=case.repository,
        commit=case.commit,
    )


def _load_jsonl(path: str | Path, model_type):
    rows = {}
    for line_number, raw in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw.strip():
            continue
        try:
            item = model_type.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(
                f"invalid alignment gold row on line {line_number}: {exc}"
            ) from exc
        if item.case_id in rows:
            raise ValueError(f"duplicate alignment gold case: {item.case_id}")
        rows[item.case_id] = item
    return rows


def load_discrepancy_gold(path: str | Path) -> dict[str, DiscrepancyGold]:
    return _load_jsonl(path, DiscrepancyGold)


def load_localization_gold(path: str | Path) -> dict[str, LocalizationGold]:
    return _load_jsonl(path, LocalizationGold)


def _tokens(text: str) -> set[str]:
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    expanded = expanded.replace("_", " ").replace("-", " ")
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", expanded)
        if token.lower() not in _STOPWORDS
    }


def _paper_sentences(text: str) -> list[tuple[str, set[str]]]:
    normalized = " ".join(text.split())
    chunks = re.split(r"(?<=[!?])\s+|(?<!\d)\.\s+(?!\d)", normalized)
    rows: list[tuple[str, set[str]]] = []
    for raw in chunks:
        sentence = raw.strip()
        tokens = _tokens(sentence)
        if len(tokens) >= 3 and len(sentence) >= 20:
            rows.append((sentence, tokens))
    return rows[:3000]


def _code_lines(repository: Path):
    for path in repository.rglob("*.py"):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(repository)
        if any(part.startswith(".") for part in relative.parts):
            continue
        try:
            if path.stat().st_size > 750_000:
                continue
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue

        for line_number, raw in enumerate(lines, start=1):
            line = raw.strip()
            if not line or line.startswith("#") or len(line) > 500:
                continue
            tokens = _tokens(line)
            if len(tokens) >= 2:
                yield str(relative), line_number, line, tokens


def localize_paper_code(
    paper_text: str,
    repository: str | Path,
    *,
    limit: int = 100,
) -> list[AlignmentCandidate]:
    """Retrieve paper↔code evidence pairs using lexical structure only.

    This is a localization baseline, not a discrepancy verdict. It receives no
    gold issue text, target path, expected mismatch category, or author response.
    """
    root = Path(repository)
    if not root.is_dir():
        raise ValueError(f"repository path is not a directory: {root}")

    sentences = _paper_sentences(paper_text)
    if not sentences:
        return []

    document_frequency: Counter[str] = Counter()
    inverted: dict[str, set[int]] = defaultdict(set)
    for index, (_, tokens) in enumerate(sentences):
        for token in tokens:
            document_frequency[token] += 1
            inverted[token].add(index)

    total_sentences = len(sentences)
    best: list[AlignmentCandidate] = []

    for path, line_number, line, code_tokens in _code_lines(root):
        sentence_indices: set[int] = set()
        for token in code_tokens:
            sentence_indices.update(inverted.get(token, ()))
        if not sentence_indices:
            continue

        best_for_line: AlignmentCandidate | None = None
        for index in sentence_indices:
            sentence, paper_tokens = sentences[index]
            shared = code_tokens & paper_tokens
            if not shared:
                continue

            rarity = sum(
                math.log((total_sentences + 1) / (document_frequency[token] + 1)) + 1.0
                for token in shared
            )
            normalization = math.sqrt(max(1, len(code_tokens) * len(paper_tokens)))
            score = rarity / normalization

            procedure_overlap = shared & _PROCEDURE_CUES
            if procedure_overlap:
                score += 0.35 + 0.08 * min(3, len(procedure_overlap))

            candidate = AlignmentCandidate(
                path=path,
                line_number=line_number,
                code_line=line,
                paper_sentence=sentence,
                shared_tokens=sorted(shared),
                score=score,
            )
            if best_for_line is None or candidate.score > best_for_line.score:
                best_for_line = candidate

        if best_for_line is not None:
            best.append(best_for_line)

    best.sort(key=lambda item: item.score, reverse=True)
    return best[:limit]


def ranked_paths(candidates: list[AlignmentCandidate]) -> list[str]:
    seen: set[str] = set()
    paths: list[str] = []
    for candidate in candidates:
        if candidate.path not in seen:
            seen.add(candidate.path)
            paths.append(candidate.path)
    return paths


def score_localization(
    case_id: str,
    candidates: list[AlignmentCandidate],
    gold: LocalizationGold,
) -> LocalizationResult:
    if gold.case_id != case_id:
        raise ValueError("localization gold case does not match evaluated case")

    paths = ranked_paths(candidates)
    rank = paths.index(gold.target_path) + 1 if gold.target_path in paths else None
    return LocalizationResult(
        case_id=case_id,
        target_path=gold.target_path,
        first_target_path_rank=rank,
        recall_at_5=rank is not None and rank <= 5,
        recall_at_10=rank is not None and rank <= 10,
        recall_at_25=rank is not None and rank <= 25,
        top_paths=paths[:25],
    )
