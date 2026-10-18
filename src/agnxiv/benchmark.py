from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from .models import Claim, Verdict, VerificationPolicy
from .outputs import extract_observation_candidates, select_unambiguous_observation
from .verify import verify_numeric_claim


class RecordedBenchmarkCase(BaseModel):
    id: str
    claim: Claim
    output: str
    policy: VerificationPolicy
    expected_verdict: Verdict
    description: str | None = None


class BenchmarkCaseResult(BaseModel):
    id: str
    expected_verdict: Verdict
    actual_verdict: Verdict
    matched: bool
    false_pass: bool
    false_contradiction: bool


class BenchmarkReport(BaseModel):
    total: int = Field(ge=0)
    matched: int = Field(ge=0)
    false_passes: int = Field(ge=0)
    false_contradictions: int = Field(ge=0)
    abstentions: int = Field(ge=0)
    coverage: float = Field(ge=0.0, le=1.0)
    accuracy: float = Field(ge=0.0, le=1.0)
    false_pass_rate: float = Field(ge=0.0, le=1.0)
    results: list[BenchmarkCaseResult]


def evaluate_recorded_case(case: RecordedBenchmarkCase) -> Verdict:
    """Evaluate a captured program output without allowing answer-guided selection."""
    candidates = extract_observation_candidates(case.output, case.claim)
    observation = select_unambiguous_observation(candidates)
    if observation is None:
        return Verdict.UNABLE_TO_VERIFY

    record = verify_numeric_claim(case.claim, [observation], case.policy)
    return record.verdict


def run_recorded_benchmark(cases: list[RecordedBenchmarkCase]) -> BenchmarkReport:
    results: list[BenchmarkCaseResult] = []

    for case in cases:
        actual = evaluate_recorded_case(case)
        false_pass = actual == Verdict.VERIFIED and case.expected_verdict != Verdict.VERIFIED
        false_contradiction = (
            actual == Verdict.CONTRADICTED
            and case.expected_verdict == Verdict.VERIFIED
        )
        results.append(
            BenchmarkCaseResult(
                id=case.id,
                expected_verdict=case.expected_verdict,
                actual_verdict=actual,
                matched=actual == case.expected_verdict,
                false_pass=false_pass,
                false_contradiction=false_contradiction,
            )
        )

    total = len(results)
    false_pass_eligible = sum(
        case.expected_verdict != Verdict.VERIFIED for case in cases
    )
    abstentions = sum(
        result.actual_verdict == Verdict.UNABLE_TO_VERIFY for result in results
    )
    return BenchmarkReport(
        total=total,
        matched=sum(result.matched for result in results),
        false_passes=sum(result.false_pass for result in results),
        false_contradictions=sum(result.false_contradiction for result in results),
        abstentions=abstentions,
        coverage=((total - abstentions) / total) if total else 0.0,
        accuracy=(sum(result.matched for result in results) / total) if total else 0.0,
        false_pass_rate=(
            sum(result.false_pass for result in results) / false_pass_eligible
            if false_pass_eligible
            else 0.0
        ),
        results=results,
    )


def load_jsonl_cases(path: str | Path) -> list[RecordedBenchmarkCase]:
    cases: list[RecordedBenchmarkCase] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            cases.append(RecordedBenchmarkCase.model_validate(json.loads(stripped)))
    return cases
