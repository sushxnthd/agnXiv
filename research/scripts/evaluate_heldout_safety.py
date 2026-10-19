from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from agnxiv.safety_confidence import SafetyDecision, false_pass_confidence


class HeldoutPrediction(BaseModel):
    schema_version: Literal["agnxiv.heldout-prediction/1"] = (
        "agnxiv.heldout-prediction/1"
    )
    case_id: str = Field(min_length=1)
    independence_key: str = Field(min_length=1)
    decision: Literal["supports", "contradicts", "abstain"]
    source: str = Field(min_length=1)


class HeldoutLabel(BaseModel):
    schema_version: Literal["agnxiv.heldout-label/1"] = "agnxiv.heldout-label/1"
    case_id: str = Field(min_length=1)
    ground_truth: Literal["supports", "not_supports"]


def _canonical_case_commitment(case_ids: list[str]) -> str:
    payload = json.dumps(
        sorted(case_ids),
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_jsonl(path: Path, model):
    rows = []
    seen: set[str] = set()
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = model.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"invalid row on line {number} of {path.name}: {exc}") from exc
        if row.case_id in seen:
            raise ValueError(f"duplicate case_id in {path.name}: {row.case_id}")
        seen.add(row.case_id)
        rows.append(row)
    return rows


def evaluate(
    predictions_path: Path,
    labels_path: Path,
    *,
    expected_case_commitment: str | None = None,
) -> dict:
    predictions = _load_jsonl(predictions_path, HeldoutPrediction)
    labels = _load_jsonl(labels_path, HeldoutLabel)

    prediction_ids = [row.case_id for row in predictions]
    label_ids = [row.case_id for row in labels]
    if set(prediction_ids) != set(label_ids):
        missing_predictions = sorted(set(label_ids) - set(prediction_ids))
        missing_labels = sorted(set(prediction_ids) - set(label_ids))
        raise ValueError(
            "prediction/label case sets differ; "
            f"missing_predictions={missing_predictions}; missing_labels={missing_labels}"
        )

    commitment = _canonical_case_commitment(prediction_ids)
    if expected_case_commitment is not None and commitment != expected_case_commitment:
        raise ValueError(
            "held-out case-set commitment mismatch: "
            f"expected {expected_case_commitment}, observed {commitment}"
        )

    label_map = {row.case_id: row.ground_truth for row in labels}
    joined = [
        SafetyDecision(
            case_id=row.case_id,
            independence_key=row.independence_key,
            ground_truth=label_map[row.case_id],
            decision=row.decision,
            source=row.source,
        )
        for row in predictions
    ]
    confidence = false_pass_confidence(joined)
    return {
        "schema_version": "agnxiv.heldout-safety-report/1",
        "case_commitment_sha256": commitment,
        "predictions_sha256": hashlib.sha256(predictions_path.read_bytes()).hexdigest(),
        "labels_sha256": hashlib.sha256(labels_path.read_bytes()).hexdigest(),
        "labels_loaded_only_at_evaluation": True,
        "report": confidence.model_dump(mode="json"),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--expected-case-commitment")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    report = evaluate(
        Path(args.predictions),
        Path(args.labels),
        expected_case_commitment=args.expected_case_commitment,
    )
    Path(args.output).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
