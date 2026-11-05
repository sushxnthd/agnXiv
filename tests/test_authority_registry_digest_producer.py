import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_digest_producer_attack_matrix_is_fail_closed():
    summary = json.loads(
        (
            ROOT
            / "research/results/authority-registry-checkpoint-digest-producer-summary.json"
        ).read_text()
    )
    audit = json.loads(
        (
            ROOT
            / "research/results/authority-registry-checkpoint-digest-producer-audit.json"
        ).read_text()
    )

    assert summary["profile_scoped_false_passes"] == 128
    assert summary["producer_scoped_false_passes"] == 0
    assert summary["producer_scoped_controls_passed"] == 32
    assert summary["families_blocked"] == {
        "producer_identity": 32,
        "producer_implementation": 32,
        "producer_runtime_image": 32,
        "producer_toolchain": 32,
    }
    assert all(summary["negative_controls"].values())
    assert audit["source_commitments_reconstructed"] == 160
    assert audit["effective_commitments_matching"] == 32
    assert audit["passed"] is True
