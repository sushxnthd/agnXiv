#!/usr/bin/env python3
"""Execute the frozen current-view gossip-quorum matrix."""
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

OUT = Path("research/results/authority-registry-transparency-current-view-quorum.json.gz")
SUMMARY = Path(
    "research/results/authority-registry-transparency-current-view-quorum-summary.json"
)
NOW = datetime(2026, 11, 12, 6, 0, tzinfo=UTC)
FAMILIES = (
    "two_old_observers",
    "two_old_one_current",
    "three_old_observers",
    "one_old_one_current",
)
OBSERVER_IDS = ("observer-a", "observer-b", "observer-c")
OBSERVER_PRIVATE = {
    observer_id: G.private_pem(f"agnxiv-current-view-{observer_id}")
    for observer_id in OBSERVER_IDS
}


def trusted(observer_id: str):
    public_key = G.public_pem(OBSERVER_PRIVATE[observer_id])
    return TrustedRegistryCheckpointTransparencyGossipObserver(
        observer_id=observer_id,
        key_id=registry_checkpoint_transparency_key_sha256(public_key),
        public_key_pem=public_key,
        administrative_domain=f"{observer_id}.example",
    )


TRUSTED = [trusted(observer_id) for observer_id in OBSERVER_IDS]


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


def row(seed: int, family: str | None):
    old_values = G.statements(seed + 20_000, 8)
    current_values = G.statements(seed + 20_000, 16)
    old = G.signed_checkpoint(old_values, NOW - timedelta(minutes=20))
    current = G.signed_checkpoint(current_values, NOW - timedelta(minutes=10))
    proof = G.witness(old_values, current_values)
    if family == "two_old_observers":
        views = [("observer-a", old), ("observer-b", old)]
    elif family == "two_old_one_current":
        views = [
            ("observer-a", old),
            ("observer-b", old),
            ("observer-c", current),
        ]
    elif family == "three_old_observers":
        views = [(observer_id, old) for observer_id in OBSERVER_IDS]
    elif family == "one_old_one_current":
        views = [("observer-a", old), ("observer-b", current)]
    else:
        views = [("observer-a", current), ("observer-b", current)]
    observations = [
        observation(observer_id, checkpoint, index + 1)
        for index, (observer_id, checkpoint) in enumerate(views)
    ]
    witnesses = [proof] if any(checkpoint == old for _, checkpoint in views) and any(
        checkpoint == current for _, checkpoint in views
    ) else []
    baseline_blockers = registry_checkpoint_transparency_gossip_blockers(
        observations,
        TRUSTED,
        G.LOG_PUBLIC,
        witnesses,
        now=NOW,
        max_age_seconds=3600,
        minimum_observers=2,
        minimum_administrative_domains=2,
    )
    bound_blockers = registry_checkpoint_transparency_gossip_blockers(
        observations,
        TRUSTED,
        G.LOG_PUBLIC,
        witnesses,
        now=NOW,
        max_age_seconds=3600,
        minimum_observers=2,
        minimum_administrative_domains=2,
        required_checkpoint=current,
        minimum_required_checkpoint_observers=2,
        minimum_required_checkpoint_administrative_domains=2,
    )
    return {
        "seed": seed,
        "family": family or "control",
        "attack": family is not None,
        "baseline_definitive": not baseline_blockers,
        "current_view_quorum_definitive": not bound_blockers,
        "baseline_blockers": baseline_blockers,
        "current_view_quorum_blockers": bound_blockers,
        "old_statements": [value.hex() for value in old_values],
        "current_statements": [value.hex() for value in current_values],
        "current_checkpoint": current.model_dump(mode="json"),
        "observations": [value.model_dump(mode="json") for value in observations],
        "trusted_observers": [value.model_dump(mode="json") for value in TRUSTED],
        "log_public_key_pem": G.LOG_PUBLIC,
        "consistency_witnesses": [value.model_dump(mode="json") for value in witnesses],
    }


def main() -> None:
    rows = [row(seed, family) for seed in range(32) for family in FAMILIES]
    rows.extend(row(seed, None) for seed in range(32))
    attacks = [value for value in rows if value["attack"]]
    controls = [value for value in rows if not value["attack"]]
    summary = {
        "schema_version": "agnxiv.transparency-current-view-quorum-summary/1",
        "attack_cases": len(attacks),
        "control_cases": len(controls),
        "baseline_false_passes": sum(value["baseline_definitive"] for value in attacks),
        "current_view_quorum_false_passes": sum(
            value["current_view_quorum_definitive"] for value in attacks
        ),
        "baseline_controls_passed": sum(
            value["baseline_definitive"] for value in controls
        ),
        "current_view_quorum_controls_passed": sum(
            value["current_view_quorum_definitive"] for value in controls
        ),
        "families_blocked": {
            family: sum(
                not value["current_view_quorum_definitive"]
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
        and summary["current_view_quorum_false_passes"] == 0
        and summary["baseline_controls_passed"] == 32
        and summary["current_view_quorum_controls_passed"] == 32
        and all(value == 32 for value in summary["families_blocked"].values())
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    OUT.write_bytes(gzip.compress(payload, mtime=0))
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["passed"]:
        raise SystemExit("frozen current-view quorum matrix failed")


if __name__ == "__main__":
    main()
