#!/usr/bin/env python3
"""Execute the frozen trusted-observer-registry substitution matrix."""
from __future__ import annotations

import gzip
import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agnxiv.authority import (
    RegistryCheckpointTransparencyGossipObservation,
    TrustedRegistryCheckpointTransparencyGossipObserver,
    registry_checkpoint_transparency_checkpoint_sha256,
    registry_checkpoint_transparency_gossip_blockers,
    registry_checkpoint_transparency_key_sha256,
    sign_registry_checkpoint_transparency_gossip_observation,
    trusted_registry_checkpoint_transparency_gossip_observer_registry_sha256,
)

SPEC = importlib.util.spec_from_file_location(
    "gossip", Path("research/scripts/verify_authority_registry_transparency_gossip.py")
)
assert SPEC and SPEC.loader
G = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(G)

OUT = Path(
    "research/results/authority-registry-transparency-observer-registry-commitment.json.gz"
)
SUMMARY = Path(
    "research/results/authority-registry-transparency-observer-registry-commitment-summary.json"
)
NOW = datetime(2026, 11, 12, 12, 30, tzinfo=UTC)
FAMILIES = (
    "new_sybil_identities",
    "trusted_id_key_rebinding",
    "revocation_metadata_rollback",
    "missing_protected_commitment",
)


def private(label: str) -> bytes:
    return G.private_pem(f"agnxiv-observer-registry-{label}")


def trusted(observer_id: str, key: bytes, domain: str, status: str = "active"):
    public_key = G.public_pem(key)
    return TrustedRegistryCheckpointTransparencyGossipObserver(
        observer_id=observer_id,
        key_id=registry_checkpoint_transparency_key_sha256(public_key),
        public_key_pem=public_key,
        administrative_domain=domain,
        status=status,
    )


LEGIT_PRIVATE = {"observer-a": private("legit-a"), "observer-b": private("legit-b")}
LEGIT = [
    trusted("observer-a", LEGIT_PRIVATE["observer-a"], "alpha.example"),
    trusted("observer-b", LEGIT_PRIVATE["observer-b"], "beta.example"),
]
LEGIT_DIGEST = (
    trusted_registry_checkpoint_transparency_gossip_observer_registry_sha256(LEGIT)
)


def attack_configuration(family: str):
    if family == "new_sybil_identities":
        identities = (("sybil-a", "sybil-a"), ("sybil-b", "sybil-b"))
    elif family == "trusted_id_key_rebinding":
        identities = (("observer-a", "rebound-a"), ("observer-b", "rebound-b"))
    elif family == "revocation_metadata_rollback":
        identities = (("retired-a", "retired-a"), ("retired-b", "retired-b"))
    else:
        identities = (("unbound-a", "unbound-a"), ("unbound-b", "unbound-b"))
    private_keys = {observer_id: private(label) for observer_id, label in identities}
    registry = [
        trusted(observer_id, private_keys[observer_id], f"domain-{index}.example")
        for index, (observer_id, _) in enumerate(identities)
    ]
    return registry, private_keys


def observation(observer_id: str, key: bytes, checkpoint, minute: int):
    scope = RegistryCheckpointTransparencyGossipObservation(
        observer_id=observer_id,
        observed_at=NOW - timedelta(minutes=minute),
        checkpoint_sha256=registry_checkpoint_transparency_checkpoint_sha256(checkpoint),
    )
    return sign_registry_checkpoint_transparency_gossip_observation(scope, checkpoint, key)


def row(seed: int, family: str | None):
    statements = G.statements(seed + 30_000, 16)
    current = G.signed_checkpoint(statements, NOW - timedelta(minutes=10))
    if family is None:
        registry, private_keys = LEGIT, LEGIT_PRIVATE
    else:
        registry, private_keys = attack_configuration(family)
    observations = [
        observation(observer.observer_id, private_keys[observer.observer_id], current, i + 1)
        for i, observer in enumerate(registry)
    ]
    common = {
        "now": NOW,
        "max_age_seconds": 3600,
        "minimum_observers": 2,
        "minimum_administrative_domains": 2,
        "required_checkpoint": current,
        "minimum_required_checkpoint_observers": 2,
        "minimum_required_checkpoint_administrative_domains": 2,
    }
    baseline_blockers = registry_checkpoint_transparency_gossip_blockers(
        observations, registry, G.LOG_PUBLIC, [], **common
    )
    expected_digest = None if family == "missing_protected_commitment" else LEGIT_DIGEST
    bound_blockers = registry_checkpoint_transparency_gossip_blockers(
        observations,
        registry,
        G.LOG_PUBLIC,
        [],
        **common,
        expected_trusted_observer_registry_sha256=expected_digest,
        require_trusted_observer_registry_commitment=True,
    )
    return {
        "seed": seed,
        "family": family or "control",
        "attack": family is not None,
        "baseline_definitive": not baseline_blockers,
        "commitment_bound_definitive": not bound_blockers,
        "baseline_blockers": baseline_blockers,
        "commitment_bound_blockers": bound_blockers,
        "expected_observer_registry_sha256": expected_digest,
        "legitimate_observer_registry_sha256": LEGIT_DIGEST,
        "supplied_observer_registry_sha256": (
            trusted_registry_checkpoint_transparency_gossip_observer_registry_sha256(
                registry
            )
        ),
        "statements": [value.hex() for value in statements],
        "current_checkpoint": current.model_dump(mode="json"),
        "observations": [value.model_dump(mode="json") for value in observations],
        "trusted_observers": [value.model_dump(mode="json") for value in registry],
        "log_public_key_pem": G.LOG_PUBLIC,
    }


def main() -> None:
    rows = [row(seed, family) for seed in range(32) for family in FAMILIES]
    rows.extend(row(seed, None) for seed in range(32))
    attacks = [value for value in rows if value["attack"]]
    controls = [value for value in rows if not value["attack"]]
    summary = {
        "schema_version": "agnxiv.transparency-observer-registry-commitment-summary/1",
        "attack_cases": len(attacks),
        "control_cases": len(controls),
        "baseline_false_passes": sum(value["baseline_definitive"] for value in attacks),
        "commitment_bound_false_passes": sum(
            value["commitment_bound_definitive"] for value in attacks
        ),
        "baseline_controls_passed": sum(
            value["baseline_definitive"] for value in controls
        ),
        "commitment_bound_controls_passed": sum(
            value["commitment_bound_definitive"] for value in controls
        ),
        "families_blocked": {
            family: sum(
                not value["commitment_bound_definitive"]
                for value in attacks
                if value["family"] == family
            )
            for family in FAMILIES
        },
        "passed": False,
    }
    summary["passed"] = (
        summary["attack_cases"] == 128
        and summary["control_cases"] == 32
        and summary["baseline_false_passes"] == 128
        and summary["commitment_bound_false_passes"] == 0
        and summary["baseline_controls_passed"] == 32
        and summary["commitment_bound_controls_passed"] == 32
        and all(value == 32 for value in summary["families_blocked"].values())
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    OUT.write_bytes(gzip.compress(payload, mtime=0))
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["passed"]:
        raise SystemExit("frozen observer-registry commitment matrix failed")


if __name__ == "__main__":
    main()
