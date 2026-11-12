#!/usr/bin/env python3
"""Execute the frozen observer-registry rollback and namespace matrix."""
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
    versioned_trusted_registry_checkpoint_transparency_gossip_observer_registry_sha256,
)

SPEC = importlib.util.spec_from_file_location(
    "gossip", Path("research/scripts/verify_authority_registry_transparency_gossip.py")
)
assert SPEC and SPEC.loader
G = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(G)

OUT = Path(
    "research/results/authority-registry-transparency-observer-registry-freshness.json.gz"
)
SUMMARY = Path(
    "research/results/authority-registry-transparency-observer-registry-freshness-summary.json"
)
NOW = datetime(2026, 11, 12, 15, 45, tzinfo=UTC)
CURRENT_NAMESPACE = "production"
CURRENT_EPOCH = 41
FAMILIES = (
    "revoked_key_rollback",
    "domain_policy_rollback",
    "namespace_replay",
    "missing_minimum_epoch",
)


def private(label: str) -> bytes:
    return G.private_pem(f"agnxiv-observer-registry-freshness-{label}")


def trusted(observer_id: str, key: bytes, domain: str, status: str = "active"):
    public_key = G.public_pem(key)
    return TrustedRegistryCheckpointTransparencyGossipObserver(
        observer_id=observer_id,
        key_id=registry_checkpoint_transparency_key_sha256(public_key),
        public_key_pem=public_key,
        administrative_domain=domain,
        status=status,
    )


CURRENT_PRIVATE = {
    "observer-c": private("current-c"),
    "observer-d": private("current-d"),
}
CURRENT = [
    trusted("observer-c", CURRENT_PRIVATE["observer-c"], "gamma.example"),
    trusted("observer-d", CURRENT_PRIVATE["observer-d"], "delta.example"),
]
CURRENT_VERSIONED_DIGEST = (
    versioned_trusted_registry_checkpoint_transparency_gossip_observer_registry_sha256(
        CURRENT,
        CURRENT_NAMESPACE,
        CURRENT_EPOCH,
    )
)


def attack_configuration(family: str):
    if family in {"namespace_replay", "missing_minimum_epoch"}:
        namespace = "staging" if family == "namespace_replay" else CURRENT_NAMESPACE
        return CURRENT, CURRENT_PRIVATE, namespace, CURRENT_EPOCH
    label = "revoked" if family == "revoked_key_rollback" else "domain-policy"
    identities = (f"{label}-a", f"{label}-b")
    private_keys = {
        observer_id: private(observer_id) for observer_id in identities
    }
    registry = [
        trusted(observer_id, private_keys[observer_id], f"old-{index}.example")
        for index, observer_id in enumerate(identities)
    ]
    return registry, private_keys, CURRENT_NAMESPACE, CURRENT_EPOCH - 1


def observation(observer_id: str, key: bytes, checkpoint, minute: int):
    scope = RegistryCheckpointTransparencyGossipObservation(
        observer_id=observer_id,
        observed_at=NOW - timedelta(minutes=minute),
        checkpoint_sha256=registry_checkpoint_transparency_checkpoint_sha256(checkpoint),
    )
    return sign_registry_checkpoint_transparency_gossip_observation(scope, checkpoint, key)


def row(seed: int, family: str | None):
    statements = G.statements(seed + 40_000, 16)
    current_checkpoint = G.signed_checkpoint(statements, NOW - timedelta(minutes=10))
    if family is None:
        registry = CURRENT
        private_keys = CURRENT_PRIVATE
        namespace = CURRENT_NAMESPACE
        epoch = CURRENT_EPOCH
    else:
        registry, private_keys, namespace, epoch = attack_configuration(family)
    observations = [
        observation(observer.observer_id, private_keys[observer.observer_id], current_checkpoint, index + 1)
        for index, observer in enumerate(registry)
    ]
    common = {
        "now": NOW,
        "max_age_seconds": 3600,
        "minimum_observers": 2,
        "minimum_administrative_domains": 2,
        "required_checkpoint": current_checkpoint,
        "minimum_required_checkpoint_observers": 2,
        "minimum_required_checkpoint_administrative_domains": 2,
    }
    versionless_digest = (
        trusted_registry_checkpoint_transparency_gossip_observer_registry_sha256(registry)
    )
    versionless_blockers = registry_checkpoint_transparency_gossip_blockers(
        observations,
        registry,
        G.LOG_PUBLIC,
        [],
        **common,
        expected_trusted_observer_registry_sha256=versionless_digest,
        require_trusted_observer_registry_commitment=True,
    )
    minimum_epoch = None if family == "missing_minimum_epoch" else CURRENT_EPOCH
    fresh_blockers = registry_checkpoint_transparency_gossip_blockers(
        observations,
        registry,
        G.LOG_PUBLIC,
        [],
        **common,
        expected_trusted_observer_registry_sha256=CURRENT_VERSIONED_DIGEST,
        require_trusted_observer_registry_commitment=True,
        trusted_observer_registry_namespace=namespace,
        trusted_observer_registry_epoch=epoch,
        expected_trusted_observer_registry_namespace=CURRENT_NAMESPACE,
        minimum_trusted_observer_registry_epoch=minimum_epoch,
        require_trusted_observer_registry_freshness=True,
    )
    return {
        "seed": seed,
        "family": family or "control",
        "attack": family is not None,
        "versionless_definitive": not versionless_blockers,
        "freshness_bound_definitive": not fresh_blockers,
        "versionless_blockers": versionless_blockers,
        "freshness_bound_blockers": fresh_blockers,
        "supplied_registry_namespace": namespace,
        "supplied_registry_epoch": epoch,
        "expected_registry_namespace": CURRENT_NAMESPACE,
        "minimum_registry_epoch": minimum_epoch,
        "versionless_registry_sha256": versionless_digest,
        "current_versioned_registry_sha256": CURRENT_VERSIONED_DIGEST,
        "supplied_versioned_registry_sha256": (
            versioned_trusted_registry_checkpoint_transparency_gossip_observer_registry_sha256(
                registry,
                namespace,
                epoch,
            )
        ),
        "statements": [value.hex() for value in statements],
        "current_checkpoint": current_checkpoint.model_dump(mode="json"),
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
        "schema_version": "agnxiv.transparency-observer-registry-freshness-summary/1",
        "attack_cases": len(attacks),
        "control_cases": len(controls),
        "versionless_false_passes": sum(value["versionless_definitive"] for value in attacks),
        "freshness_bound_false_passes": sum(
            value["freshness_bound_definitive"] for value in attacks
        ),
        "versionless_controls_passed": sum(
            value["versionless_definitive"] for value in controls
        ),
        "freshness_bound_controls_passed": sum(
            value["freshness_bound_definitive"] for value in controls
        ),
        "families_blocked": {
            family: sum(
                not value["freshness_bound_definitive"]
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
        and summary["versionless_false_passes"] == 128
        and summary["freshness_bound_false_passes"] == 0
        and summary["versionless_controls_passed"] == 32
        and summary["freshness_bound_controls_passed"] == 32
        and all(value == 32 for value in summary["families_blocked"].values())
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    OUT.write_bytes(gzip.compress(payload, mtime=0))
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["passed"]:
        raise SystemExit("frozen observer-registry freshness matrix failed")


if __name__ == "__main__":
    main()
