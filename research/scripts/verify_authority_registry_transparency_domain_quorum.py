#!/usr/bin/env python3
"""Execute the frozen administrative-domain quorum matrix."""
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
)

SPEC = importlib.util.spec_from_file_location(
    "gossip", Path("research/scripts/verify_authority_registry_transparency_gossip.py")
)
assert SPEC and SPEC.loader
G = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(G)

OUT = Path("research/results/authority-registry-transparency-domain-quorum.json.gz")
SUMMARY = Path(
    "research/results/authority-registry-transparency-domain-quorum-summary.json"
)
NOW = datetime(2026, 11, 12, 2, 0, tzinfo=UTC)
FAMILIES = (
    "same_domain_two_identities",
    "same_domain_three_identities",
    "canonical_domain_alias",
    "legacy_unscoped_observers",
)
OBSERVER_IDS = ("observer-a", "observer-b", "observer-c")
OBSERVER_PRIVATE = {
    observer_id: G.private_pem(f"agnxiv-domain-quorum-{observer_id}")
    for observer_id in OBSERVER_IDS
}


def trusted(observer_id: str, domain: str | None):
    public_key = G.public_pem(OBSERVER_PRIVATE[observer_id])
    return TrustedRegistryCheckpointTransparencyGossipObserver(
        observer_id=observer_id,
        key_id=registry_checkpoint_transparency_key_sha256(public_key),
        public_key_pem=public_key,
        administrative_domain=domain,
    )


def observation(observer_id: str, checkpoint, minute: int):
    scope = RegistryCheckpointTransparencyGossipObservation(
        observer_id=observer_id,
        observed_at=NOW - timedelta(minutes=minute),
        checkpoint_sha256=registry_checkpoint_transparency_checkpoint_sha256(
            checkpoint
        ),
    )
    return sign_registry_checkpoint_transparency_gossip_observation(
        scope, checkpoint, OBSERVER_PRIVATE[observer_id]
    )


def observer_configuration(family: str | None):
    if family == "same_domain_three_identities":
        ids = list(OBSERVER_IDS)
        domains = ["operator.example"] * 3
    elif family == "canonical_domain_alias":
        ids = ["observer-a", "observer-b"]
        domains = ["  Example.ORG  ", "example.org"]
    elif family == "legacy_unscoped_observers":
        ids = ["observer-a", "observer-b"]
        domains = [None, None]
    elif family == "same_domain_two_identities":
        ids = ["observer-a", "observer-b"]
        domains = ["operator.example", "operator.example"]
    else:
        ids = ["observer-a", "observer-b"]
        domains = ["observer-a.example", "observer-b.example"]
    return ids, [trusted(observer_id, domain) for observer_id, domain in zip(ids, domains)]


def row(seed: int, family: str | None):
    values = G.statements(seed + 10_000, 16)
    checkpoint = G.signed_checkpoint(values, NOW - timedelta(minutes=10))
    observer_ids, trusted_observers = observer_configuration(family)
    observations = [
        observation(observer_id, checkpoint, index + 1)
        for index, observer_id in enumerate(observer_ids)
    ]
    baseline_blockers = registry_checkpoint_transparency_gossip_blockers(
        observations,
        trusted_observers,
        G.LOG_PUBLIC,
        [],
        now=NOW,
        max_age_seconds=3600,
        minimum_observers=2,
        minimum_administrative_domains=0,
    )
    domain_blockers = registry_checkpoint_transparency_gossip_blockers(
        observations,
        trusted_observers,
        G.LOG_PUBLIC,
        [],
        now=NOW,
        max_age_seconds=3600,
        minimum_observers=2,
        minimum_administrative_domains=2,
    )
    return {
        "seed": seed,
        "family": family or "control",
        "attack": family is not None,
        "baseline_definitive": not baseline_blockers,
        "domain_quorum_definitive": not domain_blockers,
        "baseline_blockers": baseline_blockers,
        "domain_quorum_blockers": domain_blockers,
        "statements": [value.hex() for value in values],
        "observations": [value.model_dump(mode="json") for value in observations],
        "trusted_observers": [
            value.model_dump(mode="json") for value in trusted_observers
        ],
        "log_public_key_pem": G.LOG_PUBLIC,
    }


def main() -> None:
    rows = [row(seed, family) for seed in range(32) for family in FAMILIES]
    rows.extend(row(seed, None) for seed in range(32))
    attacks = [value for value in rows if value["attack"]]
    controls = [value for value in rows if not value["attack"]]
    summary = {
        "schema_version": "agnxiv.transparency-domain-quorum-summary/1",
        "attack_cases": len(attacks),
        "control_cases": len(controls),
        "baseline_false_passes": sum(
            value["baseline_definitive"] for value in attacks
        ),
        "domain_quorum_false_passes": sum(
            value["domain_quorum_definitive"] for value in attacks
        ),
        "baseline_controls_passed": sum(
            value["baseline_definitive"] for value in controls
        ),
        "domain_quorum_controls_passed": sum(
            value["domain_quorum_definitive"] for value in controls
        ),
        "families_blocked": {
            family: sum(
                not value["domain_quorum_definitive"]
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
        and summary["domain_quorum_false_passes"] == 0
        and summary["baseline_controls_passed"] == 32
        and summary["domain_quorum_controls_passed"] == 32
        and all(value == 32 for value in summary["families_blocked"].values())
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    OUT.write_bytes(gzip.compress(payload, mtime=0))
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["passed"]:
        raise SystemExit("frozen administrative-domain quorum matrix failed")


if __name__ == "__main__":
    main()
