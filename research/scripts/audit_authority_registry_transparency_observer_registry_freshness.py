#!/usr/bin/env python3
"""Independent zero-production-import audit of observer-registry freshness."""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

RAW = Path(
    "research/results/authority-registry-transparency-observer-registry-freshness.json.gz"
)
OUT = Path(
    "research/results/authority-registry-transparency-observer-registry-freshness-audit.json"
)


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def versionless_digest(observers: list[dict]) -> str:
    entries = sorted(observers, key=lambda entry: (entry["observer_id"], entry["key_id"]))
    return hashlib.sha256(
        canonical(
            {
                "observers": entries,
                "schema_version": "agnxiv.transparency-gossip-observer-registry/1",
            }
        )
    ).hexdigest()


def versioned_digest(observers: list[dict], namespace: str, epoch: int) -> str:
    entries = sorted(observers, key=lambda entry: (entry["observer_id"], entry["key_id"]))
    return hashlib.sha256(
        canonical(
            {
                "observers": entries,
                "registry_epoch": epoch,
                "registry_namespace": namespace.strip().casefold(),
                "schema_version": "agnxiv.transparency-gossip-observer-registry/2",
            }
        )
    ).hexdigest()


def leaf_hash(value: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + value).digest()


def tree_hash(values: list[bytes]) -> bytes:
    if len(values) == 1:
        return leaf_hash(values[0])
    split = 1 << ((len(values) - 1).bit_length() - 1)
    if split == len(values):
        split //= 2
    return hashlib.sha256(
        b"\x01" + tree_hash(values[:split]) + tree_hash(values[split:])
    ).digest()


def public_key(value: str) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(value.encode())
    assert isinstance(key, Ed25519PublicKey)
    return key


def main() -> None:
    rows = json.loads(gzip.decompress(RAW.read_bytes()))
    signatures = roots = versionless_accepts = freshness_accepts = 0
    for row in rows:
        checkpoint = row["current_checkpoint"]
        assert checkpoint["checkpoint"]["root_sha256"] == tree_hash(
            [bytes.fromhex(value) for value in row["statements"]]
        ).hex()
        roots += 1
        checkpoint_digest = hashlib.sha256(canonical(checkpoint)).hexdigest()
        registry = row["trusted_observers"]
        v1 = versionless_digest(registry)
        v2 = versioned_digest(
            registry,
            row["supplied_registry_namespace"],
            row["supplied_registry_epoch"],
        )
        assert v1 == row["versionless_registry_sha256"]
        assert v2 == row["supplied_versioned_registry_sha256"]
        trusted = {
            (value["observer_id"], value["key_id"]): value for value in registry
        }
        valid_ids, valid_domains = set(), set()
        for signed in row["observations"]:
            observation = signed["observation"]
            observer = trusted[(observation["observer_id"], signed["key_id"])]
            assert observer["status"] == "active"
            assert observation["checkpoint_sha256"] == checkpoint_digest
            assert signed["checkpoint"] == checkpoint
            public_key(observer["public_key_pem"]).verify(
                base64.b64decode(signed["signature_b64"]), canonical(observation)
            )
            public_key(row["log_public_key_pem"]).verify(
                base64.b64decode(checkpoint["signature_b64"]),
                canonical(checkpoint["checkpoint"]),
            )
            signatures += 2
            valid_ids.add(observation["observer_id"])
            valid_domains.add(observer["administrative_domain"].strip().casefold())
        quorum = len(valid_ids) >= 2 and len(valid_domains) >= 2
        versionless = quorum and v1 == row["versionless_registry_sha256"]
        floor = row["minimum_registry_epoch"]
        freshness = (
            quorum
            and floor is not None
            and row["supplied_registry_epoch"] >= floor
            and row["supplied_registry_namespace"].strip().casefold()
            == row["expected_registry_namespace"].strip().casefold()
            and v2 == row["current_versioned_registry_sha256"]
        )
        versionless_accepts += versionless
        freshness_accepts += freshness
        assert row["versionless_definitive"] is versionless
        assert row["freshness_bound_definitive"] is freshness

    attacks = [row for row in rows if row["attack"]]
    controls = [row for row in rows if not row["attack"]]
    result = {
        "schema_version": "agnxiv.transparency-observer-registry-freshness-audit/1",
        "production_imports": 0,
        "rows": len(rows),
        "signature_checks": signatures,
        "root_checks": roots,
        "versionless_digests_recomputed": len(rows),
        "versioned_digests_recomputed": len(rows),
        "independent_versionless_accepts": versionless_accepts,
        "independent_freshness_bound_accepts": freshness_accepts,
        "attack_false_passes": sum(
            row["freshness_bound_definitive"] for row in attacks
        ),
        "controls_passed": sum(
            row["freshness_bound_definitive"] for row in controls
        ),
        "passed": (
            len(rows) == 160
            and len(attacks) == 128
            and len(controls) == 32
            and signatures == 640
            and roots == 160
            and versionless_accepts == 160
            and freshness_accepts == 32
        ),
    }
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit("independent observer-registry freshness audit failed")


if __name__ == "__main__":
    main()
