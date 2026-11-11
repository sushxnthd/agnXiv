#!/usr/bin/env python3
"""Execute the frozen authenticated transparency-gossip matrix."""
from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agnxiv.authority import (
    RegistryCheckpointTransparencyCheckpoint,
    RegistryCheckpointTransparencyConsistencyWitness,
    RegistryCheckpointTransparencyGossipObservation,
    TrustedRegistryCheckpointTransparencyGossipObserver,
    registry_checkpoint_transparency_checkpoint_sha256,
    registry_checkpoint_transparency_gossip_blockers,
    registry_checkpoint_transparency_key_sha256,
    sign_registry_checkpoint_transparency_checkpoint,
    sign_registry_checkpoint_transparency_gossip_observation,
    verify_registry_checkpoint_transparency_consistency,
)

OUT = Path("research/results/authority-registry-transparency-gossip.json.gz")
SUMMARY = Path("research/results/authority-registry-transparency-gossip-summary.json")
NOW = datetime(2026, 11, 12, 0, 0, tzinfo=UTC)
LOG_ID = "agnxiv-research-log-v1"
FAMILIES = (
    "same_size_fork",
    "parallel_append_only_forks",
    "missing_cross_view_proof",
    "tampered_cross_view_proof",
)


def private_pem(label: str) -> bytes:
    seed = hashlib.sha256(label.encode()).digest()
    key = Ed25519PrivateKey.from_private_bytes(seed)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def public_pem(private: bytes) -> str:
    key = serialization.load_pem_private_key(private, password=None)
    return key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


LOG_PRIVATE = private_pem("agnxiv-gossip-log")
LOG_PUBLIC = public_pem(LOG_PRIVATE)
OBSERVER_PRIVATE = {
    name: private_pem(f"agnxiv-gossip-{name}") for name in ("observer-a", "observer-b")
}
TRUSTED = [
    TrustedRegistryCheckpointTransparencyGossipObserver(
        observer_id=name,
        key_id=registry_checkpoint_transparency_key_sha256(public_pem(key)),
        public_key_pem=public_pem(key),
    )
    for name, key in OBSERVER_PRIVATE.items()
]


def leaf_hash(value: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + value).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def tree_hash(values: list[bytes]) -> bytes:
    if len(values) == 1:
        return leaf_hash(values[0])
    split = 1 << (len(values) - 1).bit_length() - 1
    if split == len(values):
        split //= 2
    return node_hash(tree_hash(values[:split]), tree_hash(values[split:]))


def subproof(old_size: int, values: list[bytes], complete: bool) -> list[bytes]:
    if old_size == len(values):
        return [] if complete else [tree_hash(values)]
    split = 1 << (len(values) - 1).bit_length() - 1
    if split == len(values):
        split //= 2
    if old_size <= split:
        return subproof(old_size, values[:split], complete) + [tree_hash(values[split:])]
    return subproof(old_size - split, values[split:], False) + [tree_hash(values[:split])]


def statements(seed: int, size: int) -> list[bytes]:
    return [hashlib.sha256(f"{seed}:{index}".encode()).digest() for index in range(size)]


def signed_checkpoint(values: list[bytes], issued_at: datetime):
    checkpoint = RegistryCheckpointTransparencyCheckpoint(
        log_id=LOG_ID,
        tree_size=len(values),
        root_sha256=tree_hash(values).hex(),
        issued_at=issued_at,
    )
    return sign_registry_checkpoint_transparency_checkpoint(checkpoint, LOG_PRIVATE)


def witness(old_values: list[bytes], new_values: list[bytes]):
    return RegistryCheckpointTransparencyConsistencyWitness(
        log_id=LOG_ID,
        old_tree_size=len(old_values),
        old_root_sha256=tree_hash(old_values).hex(),
        new_tree_size=len(new_values),
        new_root_sha256=tree_hash(new_values).hex(),
        audit_path_sha256=[
            value.hex() for value in subproof(len(old_values), new_values, True)
        ],
    )


def observation(observer_id: str, checkpoint, minute: int):
    scope = RegistryCheckpointTransparencyGossipObservation(
        observer_id=observer_id,
        observed_at=NOW - timedelta(minutes=minute),
        checkpoint_sha256=registry_checkpoint_transparency_checkpoint_sha256(checkpoint),
    )
    return sign_registry_checkpoint_transparency_gossip_observation(
        scope, checkpoint, OBSERVER_PRIVATE[observer_id]
    )


def row(seed: int, family: str | None):
    base = statements(seed, 8)
    branch_a = statements(seed, 16)
    branch_b = list(branch_a)
    branch_b[12] = hashlib.sha256(f"fork:{seed}".encode()).digest()
    old = signed_checkpoint(base, NOW - timedelta(minutes=20))
    current_a = signed_checkpoint(branch_a, NOW - timedelta(minutes=10))
    current_b = signed_checkpoint(branch_b, NOW - timedelta(minutes=9))
    local_a = witness(base, branch_a)
    local_b = witness(base, branch_b)
    baseline_definitive = (
        verify_registry_checkpoint_transparency_consistency(local_a)
        and verify_registry_checkpoint_transparency_consistency(local_b)
    )

    if family in {"same_size_fork", "parallel_append_only_forks"}:
        checkpoints = [current_a, current_b]
        proofs = []
    elif family == "missing_cross_view_proof":
        checkpoints = [old, current_a]
        proofs = []
    elif family == "tampered_cross_view_proof":
        checkpoints = [old, current_a]
        proofs = [local_a.model_copy(update={"audit_path_sha256": ["e" * 64]})]
    else:
        checkpoints = [old, current_a]
        proofs = [local_a]

    observations = [
        observation("observer-a", checkpoints[0], 2),
        observation("observer-b", checkpoints[1], 1),
    ]
    blockers = registry_checkpoint_transparency_gossip_blockers(
        observations,
        TRUSTED,
        LOG_PUBLIC,
        proofs,
        now=NOW,
        max_age_seconds=3600,
    )
    return {
        "seed": seed,
        "family": family or "control",
        "attack": family is not None,
        "baseline_definitive": baseline_definitive,
        "gossip_definitive": not blockers,
        "split_view_detected": any("split view detected" in value for value in blockers),
        "blockers": blockers,
        "base_statements": [value.hex() for value in base],
        "branch_a_statements": [value.hex() for value in branch_a],
        "branch_b_statements": [value.hex() for value in branch_b],
        "observations": [value.model_dump(mode="json") for value in observations],
        "trusted_observers": [value.model_dump(mode="json") for value in TRUSTED],
        "log_public_key_pem": LOG_PUBLIC,
        "consistency_witnesses": [value.model_dump(mode="json") for value in proofs],
    }


def main() -> None:
    rows = [row(seed, family) for seed in range(32) for family in FAMILIES]
    rows.extend(row(seed, None) for seed in range(32))
    attacks = [value for value in rows if value["attack"]]
    controls = [value for value in rows if not value["attack"]]
    summary = {
        "schema_version": "agnxiv.transparency-gossip-summary/1",
        "attack_cases": len(attacks),
        "control_cases": len(controls),
        "baseline_false_passes": sum(value["baseline_definitive"] for value in attacks),
        "gossip_false_passes": sum(value["gossip_definitive"] for value in attacks),
        "gossip_controls_passed": sum(value["gossip_definitive"] for value in controls),
        "families_blocked": {
            family: sum(
                not value["gossip_definitive"]
                for value in attacks
                if value["family"] == family
            )
            for family in FAMILIES
        },
        "direct_split_views_detected": sum(
            value["split_view_detected"] for value in attacks
        ),
        "passed": False,
    }
    summary["passed"] = (
        summary["attack_cases"] == 128
        and summary["control_cases"] == 32
        and summary["baseline_false_passes"] == 128
        and summary["gossip_false_passes"] == 0
        and summary["gossip_controls_passed"] == 32
        and all(value == 32 for value in summary["families_blocked"].values())
        and summary["direct_split_views_detected"] == 64
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    OUT.write_bytes(gzip.compress(payload, mtime=0))
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["passed"]:
        raise SystemExit("frozen gossip matrix failed")


if __name__ == "__main__":
    main()
