#!/usr/bin/env python3
"""Independent zero-production-import audit of domain-quorum evidence."""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

RAW = Path("research/results/authority-registry-transparency-domain-quorum.json.gz")
OUT = Path("research/results/authority-registry-transparency-domain-quorum-audit.json")


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


def public_key(value: str) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(value.encode())
    assert isinstance(key, Ed25519PublicKey)
    return key


def key_id(value: str) -> str:
    key = public_key(value)
    der = key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(der).hexdigest()


def main() -> None:
    rows = json.loads(gzip.decompress(RAW.read_bytes()))
    signature_checks = 0
    root_checks = 0
    independent_baseline = 0
    independent_domain_quorum = 0
    for row in rows:
        root = tree_hash([bytes.fromhex(value) for value in row["statements"]]).hex()
        root_checks += 1
        trusted = {
            (value["observer_id"], value["key_id"]): value
            for value in row["trusted_observers"]
        }
        identities = set()
        domains = set()
        for signed in row["observations"]:
            observation = signed["observation"]
            checkpoint = signed["checkpoint"]
            observer = trusted[(observation["observer_id"], signed["key_id"])]
            assert signed["key_id"] == key_id(observer["public_key_pem"])
            assert checkpoint["checkpoint"]["root_sha256"] == root
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
            identities.add(observation["observer_id"])
            domain = observer.get("administrative_domain")
            if domain is not None:
                normalized = domain.strip().casefold()
                assert normalized
                domains.add(normalized)
        baseline = len(identities) >= 2
        domain_quorum = baseline and len(domains) >= 2
        independent_baseline += baseline
        independent_domain_quorum += domain_quorum
        assert row["baseline_definitive"] is baseline
        assert row["domain_quorum_definitive"] is domain_quorum

    attacks = [row for row in rows if row["attack"]]
    controls = [row for row in rows if not row["attack"]]
    result = {
        "schema_version": "agnxiv.transparency-domain-quorum-audit/1",
        "production_imports": 0,
        "rows": len(rows),
        "signature_checks": signature_checks,
        "root_checks": root_checks,
        "independent_baseline_accepts": independent_baseline,
        "independent_domain_quorum_accepts": independent_domain_quorum,
        "attack_false_passes": sum(
            row["domain_quorum_definitive"] for row in attacks
        ),
        "controls_passed": sum(
            row["domain_quorum_definitive"] for row in controls
        ),
        "passed": (
            len(rows) == 160
            and len(attacks) == 128
            and len(controls) == 32
            and independent_baseline == 160
            and independent_domain_quorum == 32
        ),
    }
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit("independent administrative-domain quorum audit failed")


if __name__ == "__main__":
    main()
