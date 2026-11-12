import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_current_view_quorum_blocks_partition_coverage_gap():
    summary = json.loads(
        (
            ROOT
            / "research/results/authority-registry-transparency-current-view-quorum-summary.json"
        ).read_text()
    )
    audit = json.loads(
        (
            ROOT
            / "research/results/authority-registry-transparency-current-view-quorum-audit.json"
        ).read_text()
    )
    assert summary["baseline_false_passes"] == 128
    assert summary["current_view_quorum_false_passes"] == 0
    assert summary["current_view_quorum_controls_passed"] == 32
    assert all(value == 32 for value in summary["families_blocked"].values())
    assert summary["passed"] is True
    assert audit["production_imports"] == 0
    assert audit["signature_checks"] == 768
    assert audit["root_checks"] == 320
    assert audit["attack_false_passes"] == 0
    assert audit["controls_passed"] == 32
    assert audit["passed"] is True
