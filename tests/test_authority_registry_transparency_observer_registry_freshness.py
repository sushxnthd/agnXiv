import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / (
    "research/results/authority-registry-transparency-observer-registry-freshness-summary.json"
)
AUDIT = ROOT / (
    "research/results/authority-registry-transparency-observer-registry-freshness-audit.json"
)


def test_observer_registry_freshness_blocks_rollback_matrix():
    summary = json.loads(SUMMARY.read_text())
    audit = json.loads(AUDIT.read_text())
    assert summary["passed"] is True
    assert summary["versionless_false_passes"] == 128
    assert summary["freshness_bound_false_passes"] == 0
    assert summary["versionless_controls_passed"] == 32
    assert summary["freshness_bound_controls_passed"] == 32
    assert summary["families_blocked"] == {
        "domain_policy_rollback": 32,
        "missing_minimum_epoch": 32,
        "namespace_replay": 32,
        "revoked_key_rollback": 32,
    }
    assert audit["passed"] is True
    assert audit["production_imports"] == 0
    assert audit["signature_checks"] == 640
    assert audit["root_checks"] == 160
