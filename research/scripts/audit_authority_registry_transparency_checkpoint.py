#!/usr/bin/env python3
"""Zero-production-import audit of transparency-checkpoint evidence."""
import base64
import gzip
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SOURCE = Path("research/results/authority-registry-transparency-checkpoint.json.gz")
OUT = Path("research/results/authority-registry-transparency-checkpoint-audit.json")


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def key_id(public_key):
    der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(der).hexdigest()


def independently_verified(row):
    signed = row["signed_transparency_checkpoint"]
    if signed is None:
        return False
    checkpoint = signed["checkpoint"]
    witness = row["witness"]
    if (
        checkpoint["log_id"] != witness["log_id"]
        or checkpoint["tree_size"] != witness["tree_size"]
        or checkpoint["root_sha256"] != witness["root_sha256"]
    ):
        return False
    try:
        public_key = serialization.load_pem_public_key(
            row["trusted_transparency_public_key_pem"].encode()
        )
        if not isinstance(public_key, Ed25519PublicKey):
            return False
        if signed["key_id"] != key_id(public_key):
            return False
        public_key.verify(
            base64.b64decode(signed["signature_b64"]), canonical(checkpoint)
        )
    except (ValueError, TypeError):
        return False
    now = datetime.fromisoformat(row["validation_time"])
    issued = datetime.fromisoformat(checkpoint["issued_at"])
    if now - issued > timedelta(seconds=row["max_age_seconds"]):
        return False
    return issued - now <= timedelta(seconds=row["future_skew_seconds"])


def main():
    report = json.loads(gzip.decompress(SOURCE.read_bytes()))
    rows = [*report["attacks"], *report["controls"]]
    verified = [independently_verified(row) for row in rows]
    summary = report["summary"]
    audit = {
        "schema": "agnxiv.authority-registry-transparency-checkpoint-audit/1",
        "production_imports": 0,
        "checkpoint_binding_checks": len(rows),
        "key_fingerprint_checks": len(rows),
        "signature_checks": len(rows),
        "freshness_checks": len(rows),
        "independently_verified_attacks": sum(verified[:128]),
        "independently_verified_controls": sum(verified[128:]),
        "inclusion_verified_false_passes": summary[
            "inclusion_verified_false_passes"
        ],
        "checkpoint_verified_false_passes": summary[
            "checkpoint_verified_false_passes"
        ],
    }
    audit["passed"] = (
        audit["independently_verified_attacks"] == 0
        and audit["independently_verified_controls"] == 32
        and audit["inclusion_verified_false_passes"] == 128
        and audit["checkpoint_verified_false_passes"] == 0
        and summary["passed"]
    )
    OUT.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(json.dumps(audit, indent=2, sort_keys=True))
    raise SystemExit(0 if audit["passed"] else 1)


if __name__ == "__main__":
    main()
