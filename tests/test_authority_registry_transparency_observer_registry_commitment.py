import json
from pathlib import Path

from agnxiv.authority import (
    TrustedRegistryCheckpointTransparencyGossipObserver,
    trusted_registry_checkpoint_transparency_gossip_observer_registry_sha256,
)

ROOT = Path(__file__).resolve().parents[1]


def test_observer_registry_commitment_blocks_substitution_matrix():
    summary = json.loads(
        (
            ROOT
            / "research/results/authority-registry-transparency-observer-registry-commitment-summary.json"
        ).read_text()
    )
    audit = json.loads(
        (
            ROOT
            / "research/results/authority-registry-transparency-observer-registry-commitment-audit.json"
        ).read_text()
    )
    assert summary["baseline_false_passes"] == 128
    assert summary["commitment_bound_false_passes"] == 0
    assert summary["commitment_bound_controls_passed"] == 32
    assert all(value == 32 for value in summary["families_blocked"].values())
    assert audit["passed"] is True
    assert audit["production_imports"] == 0
    assert audit["signature_checks"] == 640


def test_observer_registry_digest_is_order_invariant_but_domain_sensitive():
    base = {
        "key_id": "a" * 64,
        "public_key_pem": "public-key",
        "status": "active",
    }
    first = TrustedRegistryCheckpointTransparencyGossipObserver(
        observer_id="a", administrative_domain="Alpha.Example", **base
    )
    second = TrustedRegistryCheckpointTransparencyGossipObserver(
        observer_id="b", administrative_domain="beta.example", **base
    )
    digest = trusted_registry_checkpoint_transparency_gossip_observer_registry_sha256(
        [first, second]
    )
    assert digest == (
        trusted_registry_checkpoint_transparency_gossip_observer_registry_sha256(
            [second, first]
        )
    )
    changed = second.model_copy(update={"administrative_domain": "gamma.example"})
    assert digest != (
        trusted_registry_checkpoint_transparency_gossip_observer_registry_sha256(
            [first, changed]
        )
    )
