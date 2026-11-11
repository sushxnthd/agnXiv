#!/usr/bin/env python3
"""Independent zero-production-import transparency consistency audit."""
from __future__ import annotations

import base64
import binascii
import gzip
import hashlib
import json
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SOURCE = Path("research/results/authority-registry-transparency-consistency.json.gz")
OUT = Path("research/results/authority-registry-transparency-consistency-audit.json")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def node(left, right):
    return hashlib.sha256(b"\x01" + left + right).digest()


def root(statements):
    row = [hashlib.sha256(b"\x00" + bytes.fromhex(value)).digest() for value in statements]
    while len(row) > 1:
        row = [node(row[i], row[i + 1]) for i in range(0, len(row), 2)]
    return row[0].hex()


def checkpoint_signature_valid(signed, public_key_pem):
    key = serialization.load_pem_public_key(public_key_pem.encode())
    if not isinstance(key, Ed25519PublicKey):
        return False
    try:
        key.verify(
            base64.b64decode(signed["signature_b64"], validate=True),
            canonical(signed["checkpoint"]),
        )
        return True
    except (ValueError, TypeError, binascii.Error, InvalidSignature):
        return False


def consistency_valid(witness):
    if witness["old_tree_size"] != 8 or witness["new_tree_size"] != 16:
        return False
    if len(witness["audit_path_sha256"]) != 1:
        return False
    return node(
        bytes.fromhex(witness["old_root_sha256"]),
        bytes.fromhex(witness["audit_path_sha256"][0]),
    ).hex() == witness["new_root_sha256"]


def main():
    with gzip.open(SOURCE, "rt", encoding="utf-8") as handle:
        matrix = json.load(handle)
    attacks_valid = 0
    controls_valid = 0
    signatures_checked = 0
    roots_checked = 0
    for group, expected in ((matrix["attacks"], False), (matrix["controls"], True)):
        for row in group:
            current = row["current_checkpoint"]
            prior = row["prior_checkpoint"]
            public_key = row["trusted_transparency_public_key_pem"]
            signatures = checkpoint_signature_valid(current, public_key)
            signatures_checked += 1
            if prior is not None:
                signatures &= checkpoint_signature_valid(prior, public_key)
                signatures_checked += 1
            witness = row["consistency_witness"]
            new_root_valid = root(row["new_statements"]) == witness["new_root_sha256"]
            old_root_valid = root(row["old_statements"]) == witness["old_root_sha256"]
            roots_checked += 2
            valid = (
                signatures
                and prior is not None
                and old_root_valid
                and new_root_valid
                and consistency_valid(witness)
                and prior["checkpoint"]["tree_size"] < current["checkpoint"]["tree_size"]
            )
            if expected:
                controls_valid += valid
            else:
                attacks_valid += valid
    report = {
        "schema": "agnxiv.transparency-consistency-audit/1",
        "production_imports": 0,
        "signatures_checked": signatures_checked,
        "roots_checked": roots_checked,
        "independently_verified_attacks": attacks_valid,
        "independently_verified_controls": controls_valid,
        "passed": attacks_valid == 0 and controls_valid == 32,
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
