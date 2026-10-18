from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class ResearchCase(BaseModel):
    schema_version: Literal["agnxiv.research-case/1"] = "agnxiv.research-case/1"
    case_id: str
    source_suite: str
    source_task_id: str | None = None
    paper_url: str
    paper_url_versioned: str | None = None
    paper_alternate_urls: list[str] = Field(default_factory=list)
    repository: str | None = None
    commit: str | None = None
    origin_url: str | None = None
    known_public_ground_truth: bool = False
    evaluation_role: Literal[
        "diagnostic_nonblind", "development", "heldout_blind", "external"
    ] = "development"
    tracks: list[str] = Field(default_factory=list)
    status: Literal["queued", "running", "complete", "blocked"] = "queued"


class SelectiveOutcome(BaseModel):
    case_id: str
    gold_supports_claim: bool
    predicted: Literal["SUPPORTS", "DIVERGES", "ABSTAIN"]


class SelectiveMetrics(BaseModel):
    cases: int
    decided: int
    coverage: float
    false_passes: int
    false_divergences: int
    false_pass_rate: float
    false_divergence_rate: float
    selective_error_rate: float


def score_selective_verification(outcomes: list[SelectiveOutcome]) -> SelectiveMetrics:
    cases = len(outcomes)
    decided_rows = [row for row in outcomes if row.predicted != "ABSTAIN"]
    decided = len(decided_rows)
    false_passes = sum(
        row.predicted == "SUPPORTS" and not row.gold_supports_claim
        for row in decided_rows
    )
    false_divergences = sum(
        row.predicted == "DIVERGES" and row.gold_supports_claim
        for row in decided_rows
    )
    errors = false_passes + false_divergences

    support_predictions = sum(row.predicted == "SUPPORTS" for row in decided_rows)
    divergence_predictions = sum(row.predicted == "DIVERGES" for row in decided_rows)

    return SelectiveMetrics(
        cases=cases,
        decided=decided,
        coverage=(decided / cases) if cases else 0.0,
        false_passes=false_passes,
        false_divergences=false_divergences,
        false_pass_rate=(false_passes / support_predictions)
        if support_predictions
        else 0.0,
        false_divergence_rate=(false_divergences / divergence_predictions)
        if divergence_predictions
        else 0.0,
        selective_error_rate=(errors / decided) if decided else 0.0,
    )


def load_research_cases(path: str | Path) -> list[ResearchCase]:
    rows: list[ResearchCase] = []
    for line_number, raw in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw.strip():
            continue
        try:
            rows.append(ResearchCase.model_validate(json.loads(raw)))
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(
                f"invalid research case on line {line_number}: {exc}"
            ) from exc
    return rows


class EvidenceDependency(BaseModel):
    left_attempt: str
    right_attempt: str
    shared_factors: list[
        Literal[
            "author_code",
            "derived_code",
            "checkpoint",
            "data_split",
            "preprocessing",
            "environment",
        ]
    ] = Field(min_length=1)


class IndependenceSummary(BaseModel):
    attempts: int
    dependency_edges: int
    independent_components: int
    components: list[list[str]]


def summarize_evidence_independence(
    attempt_ids: list[str],
    dependencies: list[EvidenceDependency],
) -> IndependenceSummary:
    parent = {attempt_id: attempt_id for attempt_id in attempt_ids}

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for dependency in dependencies:
        if dependency.left_attempt not in parent or dependency.right_attempt not in parent:
            raise ValueError("dependency references an unknown attempt")
        union(dependency.left_attempt, dependency.right_attempt)

    groups: dict[str, list[str]] = {}
    for attempt_id in attempt_ids:
        groups.setdefault(find(attempt_id), []).append(attempt_id)

    components = sorted(
        (sorted(group) for group in groups.values()),
        key=lambda group: group[0] if group else "",
    )
    return IndependenceSummary(
        attempts=len(attempt_ids),
        dependency_edges=len(dependencies),
        independent_components=len(components),
        components=components,
    )
