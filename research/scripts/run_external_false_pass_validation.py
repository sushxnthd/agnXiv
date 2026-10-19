from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict, deque
from pathlib import Path

from agnxiv.benchmark import RecordedBenchmarkCase, evaluate_recorded_case
from agnxiv.claims import extract_quantitative_claims
from agnxiv.models import Claim, Verdict, VerificationPolicy
from agnxiv.validation import evaluate_false_pass_gate

_SUPPORTED_METRICS = {
    "accuracy",
    "f1",
    "auroc",
    "auc",
    "mae",
    "mse",
    "rmse",
    "bleu",
    "latency",
    "runtime",
    "throughput",
    "p_value",
}

_METRIC_LABELS = {
    "p_value": "p-value",
}

_FAMILY_COUNT = 10


def _paper_key(row: dict[str, str]) -> str:
    conference = (row.get("conference") or "unknown").strip()
    year = (row.get("year") or "unknown").strip()
    identity = (
        row.get("openreview_id")
        or row.get("paper_id")
        or row.get("PaperId")
        or row.get("title")
        or row.get("Paper")
        or ""
    ).strip()
    return f"{conference}:{year}:{identity}"


def _stratum(row: dict[str, str]) -> str:
    conference = (row.get("conference") or "unknown").strip()
    year = (row.get("year") or "unknown").strip()
    return f"{conference}-{year}"


def _repository(row: dict[str, str]) -> str:
    return (
        row.get("github_repo")
        or row.get("GitHubRepo")
        or row.get("github_repos")
        or row.get("github_links_raw")
        or ""
    ).strip()


def _abstract(row: dict[str, str]) -> str:
    return (row.get("abstract") or "").strip()


def _metric_label(metric: str) -> str:
    return _METRIC_LABELS.get(metric, metric)


def _divergent_value(value: float, unit: str | None) -> float:
    if unit == "fraction" and 0.0 <= value <= 1.0:
        candidate = value - 0.15 if value >= 0.5 else value + 0.15
        return min(1.0, max(0.0, candidate))

    delta = max(abs(value) * 0.2, 0.05)
    candidate = value + delta
    if candidate == value:
        candidate = value + 1.0
    return candidate


def _fmt(value: float) -> str:
    return format(value, ".12g")


def _case_from_row(
    row: dict[str, str],
    *,
    case_index: int,
) -> tuple[RecordedBenchmarkCase, str, str] | None:
    abstract = _abstract(row)
    repository = _repository(row)
    if not abstract or not repository:
        return None

    claims = [
        claim
        for claim in extract_quantitative_claims(abstract)
        if (
            claim.metric in _SUPPORTED_METRICS
            and claim.reported_value is not None
            and math.isfinite(claim.reported_value)
        )
    ]
    if not claims:
        return None

    source_claim = claims[0]
    target = float(source_claim.reported_value)
    observed = _divergent_value(target, source_claim.unit)
    tolerance = max(abs(target) * 0.01, 1e-6)
    metric = str(source_claim.metric)
    label = _metric_label(metric)
    paper_key = _paper_key(row)
    digest = hashlib.sha256(paper_key.encode("utf-8")).hexdigest()
    family = int(digest[:8], 16) % _FAMILY_COUNT

    target_text = _fmt(target)
    observed_text = _fmt(observed)
    generic_claim = Claim(
        id=f"EXT-{case_index:04d}",
        text=f"The paper reports {label} = {target_text}.",
        metric=metric,
        reported_value=target,
        unit=source_claim.unit,
    )

    if family == 0:
        output = (
            f"reported {label}: {target_text}\n"
            f"observed {label}: {observed_text}\n"
        )
        expected = Verdict.CONTRADICTED
    elif family == 1:
        output = (
            f"reference {label}: {target_text}\n"
            f"evaluation {label}: {observed_text}\n"
        )
        expected = Verdict.CONTRADICTED
    elif family == 2:
        output = (
            f"expected {label}: {target_text}\n"
            f"measured {label}: {observed_text}\n"
        )
        expected = Verdict.CONTRADICTED
    elif family == 3:
        output = (
            f"claimed {label}: {target_text}\n"
            f"result {label}: {observed_text}\n"
        )
        expected = Verdict.CONTRADICTED
    elif family == 4:
        output = (
            f"target {label}={target_text}; "
            f"observed {label}={observed_text}\n"
        )
        expected = Verdict.UNABLE_TO_VERIFY
    elif family == 5:
        output = (
            f"validation {label}: {target_text}\n"
            f"test {label}: {observed_text}\n"
        )
        expected = Verdict.UNABLE_TO_VERIFY
    elif family == 6:
        output = (
            f"{label}: {target_text}\n"
            f"{label}: {observed_text}\n"
        )
        expected = Verdict.UNABLE_TO_VERIFY
    elif family == 7:
        output = (
            f"loss: {target_text}\n"
            f"observed {label}: {observed_text}\n"
        )
        expected = Verdict.CONTRADICTED
    elif family == 8:
        output = (
            f"paper value {label}: {target_text}\n"
            f"evaluation {label}: {observed_text}\n"
        )
        expected = Verdict.CONTRADICTED
    else:
        output = (
            f"target {label}: {target_text}\n"
            f"measured {label}: {observed_text}\n"
        )
        expected = Verdict.CONTRADICTED

    case = RecordedBenchmarkCase(
        id=f"REPRO-{digest[:12]}",
        description=(
            "Externally seeded answer-leakage negative control from one "
            f"ReproRepo paper/repository pair ({paper_key})."
        ),
        claim=generic_claim,
        output=output,
        policy=VerificationPolicy(
            kind="absolute",
            tolerance=tolerance,
            minimum_repetitions=1,
        ),
        expected_verdict=expected,
    )
    return case, paper_key, _stratum(row)


def _load_candidates(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    for path in paths:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                key = _paper_key(row)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)
    return rows


def _balanced_sample(
    rows: list[dict[str, str]],
    *,
    maximum: int,
) -> list[dict[str, str]]:
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[_stratum(row)].append(row)

    queues: dict[str, deque[dict[str, str]]] = {}
    for stratum, group in groups.items():
        ordered = sorted(
            group,
            key=lambda row: hashlib.sha256(
                (_paper_key(row) + "|agnxiv-heldout-v1").encode("utf-8")
            ).hexdigest(),
        )
        queues[stratum] = deque(ordered)

    selected: list[dict[str, str]] = []
    strata = sorted(queues)
    while len(selected) < maximum:
        progressed = False
        for stratum in strata:
            queue = queues[stratum]
            if not queue:
                continue
            selected.append(queue.popleft())
            progressed = True
            if len(selected) >= maximum:
                break
        if not progressed:
            break
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        help="Pinned ReproRepo paper-list CSV. Repeat for multiple strata.",
    )
    parser.add_argument("--max-cases", type=int, default=320)
    parser.add_argument("--minimum-independent", type=int, default=299)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    source_rows = _load_candidates([Path(value) for value in args.input])

    eligible_rows = []
    for row in source_rows:
        preview = _case_from_row(row, case_index=len(eligible_rows) + 1)
        if preview is not None:
            eligible_rows.append(row)

    sampled = _balanced_sample(eligible_rows, maximum=args.max_cases)
    results = []
    family_counts: Counter[str] = Counter()
    stratum_counts: Counter[str] = Counter()
    false_passes = 0
    mismatches = 0
    paper_keys: set[str] = set()

    for index, row in enumerate(sampled, start=1):
        built = _case_from_row(row, case_index=index)
        if built is None:
            continue
        case, paper_key, stratum = built
        actual = evaluate_recorded_case(case)
        digest = hashlib.sha256(paper_key.encode("utf-8")).hexdigest()
        family = str(int(digest[:8], 16) % _FAMILY_COUNT)
        false_pass = (
            actual == Verdict.VERIFIED
            and case.expected_verdict != Verdict.VERIFIED
        )
        false_passes += int(false_pass)
        mismatches += int(actual != case.expected_verdict)
        family_counts[family] += 1
        stratum_counts[stratum] += 1
        paper_keys.add(paper_key)
        results.append(
            {
                "case_id": case.id,
                "paper_cluster": paper_key,
                "stratum": stratum,
                "family": family,
                "metric": case.claim.metric,
                "expected_verdict": case.expected_verdict.value,
                "actual_verdict": actual.value,
                "matched": actual == case.expected_verdict,
                "false_pass": false_pass,
            }
        )

    gate = evaluate_false_pass_gate(
        independent_trials=len(paper_keys),
        false_passes=false_passes,
        minimum_independent_trials=args.minimum_independent,
        maximum_upper_bound=0.01,
    )

    report = {
        "schema_version": "agnxiv.external-false-pass/1",
        "evaluation_role": "heldout_external_seeded_negative_control",
        "source": {
            "dataset": "ReproRepo",
            "repository": "LithiumDA/ReproRepo",
            "commit": "470a4c69d9f11df15526464e0a5bb66d95a12f55",
            "sampling_seed": "agnxiv-heldout-v1",
        },
        "cases": len(results),
        "independent_paper_clusters": len(paper_keys),
        "strata": dict(sorted(stratum_counts.items())),
        "families": dict(sorted(family_counts.items())),
        "false_passes": false_passes,
        "mismatched_expected_actions": mismatches,
        "gate": gate.model_dump(mode="json"),
        "results": results,
        "interpretation": (
            "Each trial is seeded by a distinct external paper/repository pair. "
            "The benchmark stresses answer-value echoes, decoys, split ambiguity, "
            "and observation cues. It is a false-pass safety validation, not a "
            "measurement of real-paper execution coverage."
        ),
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))

    if len(stratum_counts) < 3:
        raise SystemExit("external validation requires at least three paper strata")
    if len(family_counts) < 8:
        raise SystemExit("external validation requires at least eight adversarial families")
    if mismatches:
        raise SystemExit(
            f"external validation had {mismatches} unexpected verifier decisions"
        )
    if not gate.passed:
        raise SystemExit(
            "false-pass production gate failed: "
            f"n={gate.independent_trials}, false_passes={gate.false_passes}, "
            f"upper95={gate.zero_false_pass_upper_bound:.6f}"
        )


if __name__ == "__main__":
    main()
