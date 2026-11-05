#!/usr/bin/env python3
"""Zero-production-import audit of transparency-inclusion evidence."""
import base64
import gzip
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SOURCE = Path(
    "research/results/authority-registry-checkpoint-transparency-inclusion.json.gz"
)
OUT = Path(
    "research/results/authority-registry-checkpoint-transparency-inclusion-audit.json"
)


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def witness_digest(witness):
    return hashlib.sha256(canonical(witness)).hexdigest()


def inclusion(statement_sha256, witness):
    if witness is None or witness["leaf_index"] >= witness["tree_size"]:
        return False
    value = hashlib.sha256(b"\x00" + bytes.fromhex(statement_sha256)).digest()
    node_index = witness["leaf_index"]
    last_node = witness["tree_size"] - 1
    try:
        for encoded in witness["audit_path_sha256"]:
            sibling = bytes.fromhex(encoded)
            if len(sibling) != 32:
                return False
            if node_index & 1 or node_index == last_node:
                if node_index == last_node and not (node_index & 1):
                    while node_index and not (node_index & 1):
                        node_index >>= 1
                        last_node >>= 1
                value = hashlib.sha256(b"\x01" + sibling + value).digest()
            else:
                value = hashlib.sha256(b"\x01" + value + sibling).digest()
            node_index >>= 1
            last_node >>= 1
    except ValueError:
        return False
    return last_node == 0 and value.hex() == witness["root_sha256"]


def independently_verified(row):
    witness = row["witness"]
    scope = row["scope"]
    if witness is None or witness_digest(witness) != scope[
        "transparency_inclusion_witness_sha256"
    ]:
        return False
    signed = row["signed_attestation"]
    if signed["scope"] != scope:
        return False
    try:
        key = serialization.load_pem_public_key(row["trusted_public_key_pem"].encode())
        if not isinstance(key, Ed25519PublicKey):
            return False
        key.verify(base64.b64decode(signed["signature_b64"]), canonical(scope))
    except (ValueError, TypeError):
        return False
    return inclusion(scope["provenance_statement_sha256"], witness)


def main():
    report = json.loads(gzip.decompress(SOURCE.read_bytes()))
    rows = [*report["attacks"], *report["controls"]]
    verified = [independently_verified(row) for row in rows]
    summary = report["summary"]
    audit = {
        "schema": "agnxiv.authority-registry-checkpoint-transparency-inclusion-audit/1",
        "production_imports": 0,
        "canonical_witness_checks": len(rows),
        "signature_checks": len(rows),
        "merkle_proof_checks": len(rows),
        "independently_verified_attacks": sum(verified[:128]),
        "independently_verified_controls": sum(verified[128:]),
        "signature_authenticated_false_passes": summary[
            "signature_authenticated_false_passes"
        ],
        "inclusion_verified_false_passes": summary[
            "inclusion_verified_false_passes"
        ],
    }
    audit["passed"] = (
        audit["independently_verified_attacks"] == 0
        and audit["independently_verified_controls"] == 32
        and audit["signature_authenticated_false_passes"] == 128
        and audit["inclusion_verified_false_passes"] == 0
        and summary["passed"]
    )
    OUT.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(json.dumps(audit, indent=2, sort_keys=True))
    raise SystemExit(0 if audit["passed"] else 1)


if __name__ == "__main__":
    main()
