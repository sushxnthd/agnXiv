#!/usr/bin/env python3
"""Zero-production-import audit of digest-attestation authentication evidence."""
import base64
import binascii
import gzip
import hashlib
import json
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SOURCE = Path(
    "research/results/authority-registry-checkpoint-digest-attestation-auth.json.gz"
)
OUT = Path(
    "research/results/authority-registry-checkpoint-digest-attestation-auth-audit.json"
)


def canonical(scope):
    return json.dumps(
        scope,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


def fingerprint(public_pem):
    key = serialization.load_pem_public_key(public_pem.encode())
    if not isinstance(key, Ed25519PublicKey):
        return None
    der = key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(der).hexdigest()


def authenticated(row):
    signed = row["signed_attestation"]
    if signed is None or signed["scope"] != row["trusted_scope"]:
        return False
    try:
        key = serialization.load_pem_public_key(row["trusted_public_key_pem"].encode())
        if not isinstance(key, Ed25519PublicKey):
            return False
        if fingerprint(row["trusted_public_key_pem"]) != row["trusted_scope"][
            "attestation_signer_key_sha256"
        ]:
            return False
        signature = base64.b64decode(signed["signature_b64"], validate=True)
        key.verify(signature, canonical(signed["scope"]))
        return True
    except (binascii.Error, ValueError, TypeError, InvalidSignature):
        return False


def main():
    report = json.loads(gzip.decompress(SOURCE.read_bytes()))
    rows = [*report["attacks"], *report["controls"]]
    independent = [authenticated(row) for row in rows]
    summary = report["summary"]
    audit = {
        "schema": "agnxiv.authority-registry-checkpoint-digest-attestation-auth-audit/1",
        "production_imports": 0,
        "canonical_payload_checks": len(rows),
        "key_fingerprint_checks": len(rows),
        "independently_authenticated_envelopes": sum(independent),
        "authenticated_attacks": sum(independent[:128]),
        "authenticated_controls": sum(independent[128:]),
        "attestation_scoped_false_passes": summary[
            "attestation_scoped_false_passes"
        ],
        "authenticated_false_passes": summary["authenticated_false_passes"],
        "authenticated_controls_passed": summary["authenticated_controls_passed"],
    }
    audit["passed"] = (
        audit["authenticated_attacks"] == 0
        and audit["authenticated_controls"] == 32
        and audit["independently_authenticated_envelopes"] == 32
        and audit["attestation_scoped_false_passes"] == 128
        and audit["authenticated_false_passes"] == 0
        and audit["authenticated_controls_passed"] == 32
        and summary["passed"]
    )
    OUT.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(json.dumps(audit, indent=2, sort_keys=True))
    raise SystemExit(0 if audit["passed"] else 1)


if __name__ == "__main__":
    main()
