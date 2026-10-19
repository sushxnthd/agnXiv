import json
from pathlib import Path

import pytest

from research.scripts.evaluate_heldout_safety import evaluate


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_heldout_evaluator_joins_labels_only_at_evaluation(tmp_path: Path) -> None:
    predictions = tmp_path / "predictions.jsonl"
    labels = tmp_path / "labels.jsonl"
    _write(
        predictions,
        [
            {
                "schema_version": "agnxiv.heldout-prediction/1",
                "case_id": "A",
                "independence_key": "cluster-A",
                "decision": "supports",
                "source": "sealed-run",
            }
        ],
    )
    _write(
        labels,
        [
            {
                "schema_version": "agnxiv.heldout-label/1",
                "case_id": "A",
                "ground_truth": "supports",
            }
        ],
    )

    report = evaluate(predictions, labels)

    assert report["labels_loaded_only_at_evaluation"] is True
    assert report["report"]["supports_decisions"] == 1
    assert report["report"]["false_passes"] == 0
    assert report["report"]["production_pass"] is False


def test_heldout_evaluator_rejects_case_set_mismatch(tmp_path: Path) -> None:
    predictions = tmp_path / "predictions.jsonl"
    labels = tmp_path / "labels.jsonl"
    _write(
        predictions,
        [
            {
                "schema_version": "agnxiv.heldout-prediction/1",
                "case_id": "A",
                "independence_key": "cluster-A",
                "decision": "abstain",
                "source": "sealed-run",
            }
        ],
    )
    _write(
        labels,
        [
            {
                "schema_version": "agnxiv.heldout-label/1",
                "case_id": "B",
                "ground_truth": "supports",
            }
        ],
    )

    with pytest.raises(ValueError, match="case sets differ"):
        evaluate(predictions, labels)


def test_heldout_evaluator_rejects_wrong_frozen_case_commitment(tmp_path: Path) -> None:
    predictions = tmp_path / "predictions.jsonl"
    labels = tmp_path / "labels.jsonl"
    _write(
        predictions,
        [
            {
                "schema_version": "agnxiv.heldout-prediction/1",
                "case_id": "A",
                "independence_key": "cluster-A",
                "decision": "supports",
                "source": "sealed-run",
            }
        ],
    )
    _write(
        labels,
        [
            {
                "schema_version": "agnxiv.heldout-label/1",
                "case_id": "A",
                "ground_truth": "supports",
            }
        ],
    )

    with pytest.raises(ValueError, match="commitment mismatch"):
        evaluate(
            predictions,
            labels,
            expected_case_commitment="0" * 64,
        )
