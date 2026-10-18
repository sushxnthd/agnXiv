from __future__ import annotations

import re
import shlex
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

_RESEARCH_TERMS = (
    "eval",
    "repro",
    "result",
    "experiment",
    "score",
    "scoring",
    "benchmark",
    "paper",
)


def _clean_readme_line(raw: str) -> str:
    line = raw.strip()
    line = line.removeprefix("$").strip()
    line = line.strip(chr(96)).strip()
    return line


def _looks_like_command_start(line: str) -> bool:
    if not line or line.startswith("--"):
        return False
    if not re.match(r"^[A-Za-z0-9_.-]+(?:\s|$)", line):
        return False
    if line.lower().startswith(("pip ", "python -m pip ", "git ", "cd ")):
        return False

    lower = line.lower()
    option_heavy = line.count("--") >= 2
    python_command = lower.startswith(("python ", "python3 "))
    return (
        option_heavy
        or python_command
        or any(term in lower for term in _RESEARCH_TERMS)
    )


def _readme_commands(text: str) -> list[tuple[list[str], str]]:
    """Extract documented research shell commands, joining wrapped option lines."""
    commands: list[tuple[list[str], str]] = []
    lines = [_clean_readme_line(raw) for raw in text.splitlines()]

    index = 0
    while index < len(lines):
        line = lines[index]
        if not _looks_like_command_start(line):
            index += 1
            continue

        parts = [line]
        cursor = index + 1
        while cursor < len(lines) and lines[cursor].startswith("--"):
            parts.append(lines[cursor])
            cursor += 1

        joined = " ".join(parts)
        try:
            tokens = shlex.split(joined)
        except ValueError:
            index = cursor
            continue

        if tokens:
            commands.append((tokens, joined))
        index = cursor

    return commands


def discover_commands(repository: str | Path, *, limit: int = 15) -> list[CommandCandidate]:
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

        for tokens, raw in _readme_commands(text):
            score = 0.84
            if "repro" in raw.lower():
                score = 0.94
            elif (
                "eval" in raw.lower()
                or "score" in raw.lower()
                or "scoring" in raw.lower()
            ):
                score = 0.90
            candidates.append(
                CommandCandidate(
                    command=tokens,
                    source=readme_name,
                    score=score,
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
