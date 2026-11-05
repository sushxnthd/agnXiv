import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_transparency_inclusion_matrix_is_fail_closed():
    summary = json.loads(
        (
            ROOT
            / "research/results/authority-registry-checkpoint-transparency-inclusion-summary.json"
        ).read_text()
    )
    audit = json.loads(
        (
            ROOT
            / "research/results/authority-registry-checkpoint-transparency-inclusion-audit.json"
        ).read_text()
    )

    assert summary["signature_authenticated_false_passes"] == 128
    assert summary["inclusion_verified_false_passes"] == 0
    assert summary["inclusion_verified_controls_passed"] == 32
    assert summary["families_blocked"] == {
        "missing_witness": 32,
        "tampered_audit_path": 32,
        "wrong_leaf_index": 32,
        "wrong_tree_root": 32,
    }
    assert all(summary["negative_controls"].values())
    assert audit["independently_verified_attacks"] == 0
    assert audit["independently_verified_controls"] == 32
    assert audit["passed"] is True
