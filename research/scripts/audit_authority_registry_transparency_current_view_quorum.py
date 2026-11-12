#!/usr/bin/env python3
"""Independent zero-production-import audit of current-view quorum evidence."""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

RAW = Path("research/results/authority-registry-transparency-current-view-quorum.json.gz")
OUT = Path("research/results/authority-registry-transparency-current-view-quorum-audit.json")


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def leaf_hash(value: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + value).digest()


def tree_hash(values: list[bytes]) -> bytes:
    if len(values) == 1:
        return leaf_hash(values[0])
    split = 1 << (len(values) - 1).bit_length() - 1
    if split == len(values):
        split //= 2
    return hashlib.sha256(
        b"\x01" + tree_hash(values[:split]) + tree_hash(values[split:])
    ).digest()


def consistency_valid(witness: dict) -> bool:
    old_size, new_size = witness["old_tree_size"], witness["new_tree_size"]
    proof = [bytes.fromhex(value) for value in witness["audit_path_sha256"]]
    old_root = bytes.fromhex(witness["old_root_sha256"])
    new_root = bytes.fromhex(witness["new_root_sha256"])
    fn, sn = old_size - 1, new_size - 1
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
    signature_checks = root_checks = baseline_accepts = quorum_accepts = 0
    for row in rows:
        old_root = tree_hash([bytes.fromhex(value) for value in row["old_statements"]]).hex()
        current_root = tree_hash(
            [bytes.fromhex(value) for value in row["current_statements"]]
        ).hex()
        root_checks += 2
        current = row["current_checkpoint"]
        assert current["checkpoint"]["root_sha256"] == current_root
        current_digest = hashlib.sha256(canonical(current)).hexdigest()
        trusted = {
            (value["observer_id"], value["key_id"]): value
            for value in row["trusted_observers"]
        }
        checkpoints = []
        current_observers, current_domains = set(), set()
        for signed in row["observations"]:
            observation = signed["observation"]
            checkpoint = signed["checkpoint"]
            observer = trusted[(observation["observer_id"], signed["key_id"])]
            assert observation["checkpoint_sha256"] == hashlib.sha256(
                canonical(checkpoint)
            ).hexdigest()
            public_key(observer["public_key_pem"]).verify(
                base64.b64decode(signed["signature_b64"]), canonical(observation)
            )
            public_key(row["log_public_key_pem"]).verify(
                base64.b64decode(checkpoint["signature_b64"]),
                canonical(checkpoint["checkpoint"]),
            )
            signature_checks += 2
            checkpoints.append(checkpoint["checkpoint"])
            assert checkpoint["checkpoint"]["root_sha256"] in {old_root, current_root}
            if observation["checkpoint_sha256"] == current_digest:
                current_observers.add(observation["observer_id"])
                current_domains.add(observer["administrative_domain"].strip().casefold())

        pairwise = True
        for index, left in enumerate(checkpoints):
            for right in checkpoints[index + 1 :]:
                if left["tree_size"] == right["tree_size"]:
                    pairwise &= left["root_sha256"] == right["root_sha256"]
                else:
                    old, new = (left, right) if left["tree_size"] < right["tree_size"] else (right, left)
                    matches = [
                        witness
                        for witness in row["consistency_witnesses"]
                        if witness["old_root_sha256"] == old["root_sha256"]
                        and witness["new_root_sha256"] == new["root_sha256"]
                    ]
                    pairwise &= len(matches) == 1 and consistency_valid(matches[0])
        baseline = pairwise and len(checkpoints) >= 2
        quorum = baseline and len(current_observers) >= 2 and len(current_domains) >= 2
        baseline_accepts += baseline
        quorum_accepts += quorum
        assert row["baseline_definitive"] is baseline
        assert row["current_view_quorum_definitive"] is quorum

    attacks = [row for row in rows if row["attack"]]
    controls = [row for row in rows if not row["attack"]]
    result = {
        "schema_version": "agnxiv.transparency-current-view-quorum-audit/1",
        "production_imports": 0,
        "rows": len(rows),
        "signature_checks": signature_checks,
        "root_checks": root_checks,
        "independent_baseline_accepts": baseline_accepts,
        "independent_current_view_quorum_accepts": quorum_accepts,
        "attack_false_passes": sum(
            row["current_view_quorum_definitive"] for row in attacks
        ),
        "controls_passed": sum(
            row["current_view_quorum_definitive"] for row in controls
        ),
        "passed": (
            len(rows) == 160
            and len(attacks) == 128
            and len(controls) == 32
            and baseline_accepts == 160
            and quorum_accepts == 32
        ),
    }
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit("independent current-view quorum audit failed")


if __name__ == "__main__":
    main()
