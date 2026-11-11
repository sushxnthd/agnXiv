import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_authenticated_gossip_matrix_blocks_split_views():
    summary = json.loads(
        (
            ROOT
            / "research/results/authority-registry-transparency-gossip-summary.json"
        ).read_text()
    )
    audit = json.loads(
        (
            ROOT
            / "research/results/authority-registry-transparency-gossip-audit.json"
        ).read_text()
    )
    assert summary["attack_cases"] == 128
    assert summary["control_cases"] == 32
    assert summary["baseline_false_passes"] == 128
    assert summary["gossip_false_passes"] == 0
    assert summary["gossip_controls_passed"] == 32
    assert summary["direct_split_views_detected"] == 64
    assert all(value == 32 for value in summary["families_blocked"].values())
    assert summary["passed"] is True
    assert audit["production_imports"] == 0
    assert audit["rows"] == 160
    assert audit["signature_checks"] == 640
    assert audit["root_checks"] == 480
    assert audit["independently_verified_attacks"] == 0
    assert audit["independently_verified_controls"] == 32
    assert audit["passed"] is True
