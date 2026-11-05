import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_digest_attestation_authentication_matrix_is_fail_closed():
    summary = json.loads(
        (
            ROOT
            / "research/results/authority-registry-checkpoint-digest-attestation-auth-summary.json"
        ).read_text()
    )
    audit = json.loads(
        (
            ROOT
            / "research/results/authority-registry-checkpoint-digest-attestation-auth-audit.json"
        ).read_text()
    )

    assert summary["attestation_scoped_false_passes"] == 128
    assert summary["authenticated_false_passes"] == 0
    assert summary["authenticated_controls_passed"] == 32
    assert summary["families_blocked"] == {
        "missing_signature": 32,
        "malformed_signature": 32,
        "untrusted_signer": 32,
        "replayed_scope": 32,
    }
    assert all(summary["negative_controls"].values())
    assert audit["independently_authenticated_envelopes"] == 32
    assert audit["authenticated_attacks"] == 0
    assert audit["authenticated_controls"] == 32
    assert audit["passed"] is True
