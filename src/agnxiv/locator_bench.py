from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .models import Claim
from .outputs import extract_observation_candidates, select_unambiguous_observation


class LocatorBenchmarkCase(BaseModel):
    case_id: str
    claim_text: str
    metric: str | None = None
    unit: str | None = None
    output: str
    expected_action: Literal["SELECT", "ABSTAIN"]
    expected_value: float | None = None


class LocatorBenchmarkResult(BaseModel):
    cases: int
    correct: int
    accuracy: float
    selection_cases: int
    correct_selections: int
    selection_accuracy: float
    abstain_cases: int
    correct_abstentions: int
    abstention_accuracy: float
    false_selections: int
    missed_selections: int
    per_case: list[dict]


def load_locator_cases(path: str | Path) -> list[LocatorBenchmarkCase]:
    rows: list[LocatorBenchmarkCase] = []
    for line_number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            rows.append(LocatorBenchmarkCase.model_validate(json.loads(raw)))
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"invalid locator row on line {line_number}: {exc}") from exc
    return rows


def run_locator_benchmark(cases: list[LocatorBenchmarkCase]) -> LocatorBenchmarkResult:
    rows: list[dict] = []
    correct = selection_cases = correct_selections = 0
    abstain_cases = correct_abstentions = false_selections = missed_selections = 0

    for case in cases:
        claim = Claim(
            id=case.case_id,
            text=case.claim_text,
            metric=case.metric,
            reported_value=None,
            unit=case.unit,
        )
        candidates = extract_observation_candidates(case.output, claim)
        selected = select_unambiguous_observation(candidates)
        observed = selected.value if selected is not None else None

        if case.expected_action == "ABSTAIN":
            abstain_cases += 1
            case_correct = selected is None
            if case_correct:
                correct_abstentions += 1
            else:
                false_selections += 1
        else:
            selection_cases += 1
            case_correct = (
                selected is not None
                and case.expected_value is not None
                and abs(selected.value - case.expected_value) <= 1e-9
            )
            if case_correct:
                correct_selections += 1
            elif selected is None:
                missed_selections += 1

        if case_correct:
            correct += 1
        rows.append({
            "case_id": case.case_id,
            "expected_action": case.expected_action,
            "expected_value": case.expected_value,
            "observed_value": observed,
            "correct": case_correct,
            "top_candidates": [
                {
                    "line_number": candidate.line_number,
                    "line": candidate.line,
                    "normalized_value": candidate.normalized_value,
                    "score": candidate.score,
                }
                for candidate in candidates[:4]
            ],
        })

    total = len(cases)
    return LocatorBenchmarkResult(
        cases=total,
        correct=correct,
        accuracy=(correct / total) if total else 0.0,
        selection_cases=selection_cases,
        correct_selections=correct_selections,
        selection_accuracy=correct_selections / selection_cases if selection_cases else 0.0,
        abstain_cases=abstain_cases,
        correct_abstentions=correct_abstentions,
        abstention_accuracy=correct_abstentions / abstain_cases if abstain_cases else 0.0,
        false_selections=false_selections,
        missed_selections=missed_selections,
        per_case=rows,
    )
