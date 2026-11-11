import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_transparency_checkpoint_matrix_is_fail_closed():
    summary = json.loads(
        (
            ROOT
            / "research/results/authority-registry-transparency-checkpoint-summary.json"
        ).read_text()
    )
    audit = json.loads(
        (
            ROOT
            / "research/results/authority-registry-transparency-checkpoint-audit.json"
        ).read_text()
    )

    assert summary["inclusion_verified_false_passes"] == 128
    assert summary["checkpoint_verified_false_passes"] == 0
    assert summary["checkpoint_verified_controls_passed"] == 32
    assert summary["families_blocked"] == {
        "missing_checkpoint": 32,
        "wrong_signing_key": 32,
        "expired_checkpoint": 32,
        "future_checkpoint": 32,
    }
    assert all(summary["negative_controls"].values())
    assert audit["production_imports"] == 0
    assert audit["independently_verified_attacks"] == 0
    assert audit["independently_verified_controls"] == 32
    assert audit["passed"] is True
