#!/usr/bin/env python3
"""Independent zero-production-import audit of transparency gossip evidence."""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

RAW = Path("research/results/authority-registry-transparency-gossip.json.gz")
OUT = Path("research/results/authority-registry-transparency-gossip-audit.json")


def canonical(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


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


def consistency_valid(witness: dict) -> bool:
    old_size = witness["old_tree_size"]
    new_size = witness["new_tree_size"]
    if old_size > new_size:
        return False
    if old_size == new_size:
        return (
            witness["old_root_sha256"] == witness["new_root_sha256"]
            and not witness["audit_path_sha256"]
        )
    try:
        proof = [bytes.fromhex(value) for value in witness["audit_path_sha256"]]
        old_root = bytes.fromhex(witness["old_root_sha256"])
        new_root = bytes.fromhex(witness["new_root_sha256"])
    except ValueError:
        return False
    fn = old_size - 1
    sn = new_size - 1
    while fn & 1:
        fn >>= 1
        sn >>= 1
    if fn == 0:
        old_hash = new_hash = old_root
        index = 0
    elif proof:
        old_hash = new_hash = proof[0]
        index = 1
    else:
        return False
    while index < len(proof):
        if sn == 0:
            return False
        node = proof[index]
        if fn & 1 or fn == sn:
            old_hash = hashlib.sha256(b"\x01" + node + old_hash).digest()
            new_hash = hashlib.sha256(b"\x01" + node + new_hash).digest()
            while fn and not (fn & 1):
                fn >>= 1
                sn >>= 1
        else:
            new_hash = hashlib.sha256(b"\x01" + new_hash + node).digest()
        fn >>= 1
        sn >>= 1
        index += 1
    return sn == 0 and old_hash == old_root and new_hash == new_root


def public_key(value: str) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(value.encode())
    assert isinstance(key, Ed25519PublicKey)
    return key


def main() -> None:
    rows = json.loads(gzip.decompress(RAW.read_bytes()))
    signature_checks = 0
    root_checks = 0
    independently_passed = 0
    direct_splits = 0
    for row in rows:
        roots = {
            "base": tree_hash([bytes.fromhex(value) for value in row["base_statements"]]).hex(),
            "branch_a": tree_hash(
                [bytes.fromhex(value) for value in row["branch_a_statements"]]
            ).hex(),
            "branch_b": tree_hash(
                [bytes.fromhex(value) for value in row["branch_b_statements"]]
            ).hex(),
        }
        root_checks += 3
        trusted = {
            (value["observer_id"], value["key_id"]): value
            for value in row["trusted_observers"]
        }
        checkpoints = []
        for signed in row["observations"]:
            observation = signed["observation"]
            checkpoint = signed["checkpoint"]
            expected_digest = hashlib.sha256(canonical(checkpoint)).hexdigest()
            assert observation["checkpoint_sha256"] == expected_digest
            observer = trusted[(observation["observer_id"], signed["key_id"])]
            public_key(observer["public_key_pem"]).verify(
                base64.b64decode(signed["signature_b64"]), canonical(observation)
            )
            public_key(row["log_public_key_pem"]).verify(
                base64.b64decode(checkpoint["signature_b64"]),
                canonical(checkpoint["checkpoint"]),
            )
            signature_checks += 2
            checkpoints.append(checkpoint["checkpoint"])
        for checkpoint in checkpoints:
            assert checkpoint["root_sha256"] in roots.values()
        if checkpoints[0]["tree_size"] == checkpoints[1]["tree_size"]:
            audit_pass = checkpoints[0]["root_sha256"] == checkpoints[1]["root_sha256"]
            if not audit_pass:
                direct_splits += 1
        else:
            matching = [
                value
                for value in row["consistency_witnesses"]
                if value["old_root_sha256"]
                in {checkpoints[0]["root_sha256"], checkpoints[1]["root_sha256"]}
                and value["new_root_sha256"]
                in {checkpoints[0]["root_sha256"], checkpoints[1]["root_sha256"]}
            ]
            audit_pass = len(matching) == 1 and consistency_valid(matching[0])
        independently_passed += audit_pass
        assert row["gossip_definitive"] is audit_pass

    attacks = [row for row in rows if row["attack"]]
    controls = [row for row in rows if not row["attack"]]
    result = {
        "schema_version": "agnxiv.transparency-gossip-audit/1",
        "production_imports": 0,
        "rows": len(rows),
        "signature_checks": signature_checks,
        "root_checks": root_checks,
        "independently_verified_attacks": sum(
            row["gossip_definitive"] for row in attacks
        ),
        "independently_verified_controls": sum(
            row["gossip_definitive"] for row in controls
        ),
        "direct_split_views_detected": direct_splits,
        "passed": (
            independently_passed == 32
            and direct_splits == 64
            and len(attacks) == 128
            and len(controls) == 32
        ),
    }
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit("independent gossip audit failed")


if __name__ == "__main__":
    main()
