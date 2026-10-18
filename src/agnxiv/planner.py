from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field


class CommandCandidate(BaseModel):
    command: list[str]
    source: str
    score: float = Field(ge=0.0, le=1.0)
    rationale: str


_COMMON_SCRIPTS = (
    ("evaluate.py", 0.95),
    ("eval.py", 0.92),
    ("test.py", 0.72),
    ("run.py", 0.68),
    ("main.py", 0.60),
    ("experiment.py", 0.85),
    ("experiments.py", 0.85),
    ("reproduce.py", 0.98),
    ("reproduction.py", 0.98),
)


def discover_commands(repository: str | Path, *, limit: int = 10) -> list[CommandCandidate]:
    """Discover likely reproduction/evaluation entrypoints without executing them."""
    root = Path(repository)
    if not root.is_dir():
        raise ValueError(f"repository path is not a directory: {root}")

    candidates: list[CommandCandidate] = []

    for name, score in _COMMON_SCRIPTS:
        for path in root.rglob(name):
            if path.is_symlink() or not path.is_file():
                continue
            rel_parts = path.relative_to(root).parts
            if any(part.startswith(".") for part in rel_parts):
                continue
            rel = str(path.relative_to(root))
            candidates.append(
                CommandCandidate(
                    command=["python", rel],
                    source=rel,
                    score=score,
                    rationale=f"common research entrypoint: {name}",
                )
            )

    makefile = root / "Makefile"
    if makefile.exists() and not makefile.is_symlink():
        try:
            text = makefile.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            text = ""
        for target in re.findall(r"(?m)^([A-Za-z0-9_.-]+)\s*:(?![=])", text):
            lower = target.lower()
            if lower in {"reproduce", "reproduction", "evaluate", "eval", "results", "paper"}:
                score = 0.96 if lower.startswith("repro") else 0.90
                candidates.append(
                    CommandCandidate(
                        command=["make", target],
                        source="Makefile",
                        score=score,
                        rationale=f"research-oriented Make target: {target}",
                    )
                )

    for readme_name in ("README.md", "README.rst", "README.txt"):
        readme = root / readme_name
        if not readme.exists() or readme.is_symlink():
            continue
        try:
            text = readme.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for match in re.finditer(
            r"(?m)^\s*(python(?:3)?\s+[^\n\x60]+|make\s+[A-Za-z0-9_.-]+)\s*$",
            text,
        ):
            raw = match.group(1).strip()
            if any(token in raw.lower() for token in ("eval", "repro", "result", "experiment")):
                candidates.append(
                    CommandCandidate(
                        command=raw.split(),
                        source=readme_name,
                        score=0.82,
                        rationale="documented research command",
                    )
                )

    dedup: dict[tuple[str, ...], CommandCandidate] = {}
    for candidate in candidates:
        key = tuple(candidate.command)
        existing = dedup.get(key)
        if existing is None or candidate.score > existing.score:
            dedup[key] = candidate

    return sorted(dedup.values(), key=lambda c: c.score, reverse=True)[:limit]
