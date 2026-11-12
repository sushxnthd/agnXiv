#!/usr/bin/env python3
"""Independent zero-production-import audit of observer-registry binding."""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

RAW = Path(
    "research/results/authority-registry-transparency-observer-registry-commitment.json.gz"
)
OUT = Path(
    "research/results/authority-registry-transparency-observer-registry-commitment-audit.json"
)


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def observer_registry_digest(observers: list[dict]) -> str:
    entries = sorted(observers, key=lambda entry: (entry["observer_id"], entry["key_id"]))
    return hashlib.sha256(
        canonical(
            {
                "schema_version": "agnxiv.transparency-gossip-observer-registry/1",
                "observers": entries,
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
    signature_checks = root_checks = baseline_accepts = bound_accepts = 0
    legitimate_digests = set()
    supplied_digests = set()
    for row in rows:
        checkpoint = row["current_checkpoint"]
        root = tree_hash([bytes.fromhex(value) for value in row["statements"]]).hex()
        assert checkpoint["checkpoint"]["root_sha256"] == root
        root_checks += 1
        checkpoint_digest = hashlib.sha256(canonical(checkpoint)).hexdigest()
        registry = row["trusted_observers"]
        registry_digest = observer_registry_digest(registry)
        assert registry_digest == row["supplied_observer_registry_sha256"]
        supplied_digests.add(registry_digest)
        legitimate_digests.add(row["legitimate_observer_registry_sha256"])
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
            signature_checks += 2
            valid_ids.add(observation["observer_id"])
            valid_domains.add(observer["administrative_domain"].strip().casefold())
        baseline = len(valid_ids) >= 2 and len(valid_domains) >= 2
        expected = row["expected_observer_registry_sha256"]
        bound = baseline and expected is not None and registry_digest == expected
        baseline_accepts += baseline
        bound_accepts += bound
        assert row["baseline_definitive"] is baseline
        assert row["commitment_bound_definitive"] is bound

    attacks = [row for row in rows if row["attack"]]
    controls = [row for row in rows if not row["attack"]]
    result = {
        "schema_version": "agnxiv.transparency-observer-registry-commitment-audit/1",
        "production_imports": 0,
        "rows": len(rows),
        "signature_checks": signature_checks,
        "root_checks": root_checks,
        "observer_registry_digests_recomputed": len(rows),
        "distinct_legitimate_registry_digests": len(legitimate_digests),
        "distinct_supplied_registry_digests": len(supplied_digests),
        "independent_baseline_accepts": baseline_accepts,
        "independent_commitment_bound_accepts": bound_accepts,
        "attack_false_passes": sum(
            row["commitment_bound_definitive"] for row in attacks
        ),
        "controls_passed": sum(
            row["commitment_bound_definitive"] for row in controls
        ),
        "passed": (
            len(rows) == 160
            and len(attacks) == 128
            and len(controls) == 32
            and signature_checks == 640
            and root_checks == 160
            and baseline_accepts == 160
            and bound_accepts == 32
        ),
    }
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit("independent observer-registry commitment audit failed")


if __name__ == "__main__":
    main()
