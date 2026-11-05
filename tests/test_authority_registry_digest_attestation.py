import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_digest_attestation_attack_matrix_is_fail_closed():
    summary = json.loads(
        (
            ROOT
            / "research/results/authority-registry-checkpoint-digest-attestation-summary.json"
        ).read_text()
    )
    audit = json.loads(
        (
            ROOT
            / "research/results/authority-registry-checkpoint-digest-attestation-audit.json"
        ).read_text()
    )

    assert summary["producer_scoped_false_passes"] == 128
    assert summary["attestation_scoped_false_passes"] == 0
    assert summary["attestation_scoped_controls_passed"] == 32
    assert summary["families_blocked"] == {
        "predicate_type": 32,
        "provenance_statement": 32,
        "attestation_signer": 32,
        "transparency_witness": 32,
    }
    assert all(summary["negative_controls"].values())
    assert audit["source_commitments_reconstructed"] == 160
    assert audit["effective_commitments_matching"] == 32
    assert audit["passed"] is True
