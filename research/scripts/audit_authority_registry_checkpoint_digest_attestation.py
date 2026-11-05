#!/usr/bin/env python3
"""Zero-production-import audit of digest-attestation substitution evidence."""
import gzip
import hashlib
import json
from pathlib import Path

SOURCE = Path("research/results/authority-registry-checkpoint-digest-attestation.json.gz")
OUT = Path("research/results/authority-registry-checkpoint-digest-attestation-audit.json")


def commitment(parent, attestation):
    payload = json.dumps(
        {
            "attestation_scope": attestation,
            "digest_producer_scoped_history_commitment_sha256": parent,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def main():
    report = json.loads(gzip.decompress(SOURCE.read_bytes()))
    rows = [*report["attacks"], *report["controls"]]
    source_checks = sum(
        commitment(row["producer_commitment"], row["source_attestation"])
        == row["trusted_attestation_commitment"]
        for row in rows
    )
    effective_matches = sum(
        commitment(row["producer_commitment"], row["effective_attestation"])
        == row["trusted_attestation_commitment"]
        for row in rows
    )
    summary = report["summary"]
    audit = {
        "schema": "agnxiv.authority-registry-checkpoint-digest-attestation-audit/1",
        "production_imports": 0,
        "attestation_payload_checks": len(rows) * 2,
        "source_commitments_reconstructed": source_checks,
        "effective_commitments_matching": effective_matches,
        "producer_scoped_false_passes": summary["producer_scoped_false_passes"],
        "attestation_scoped_false_passes": summary[
            "attestation_scoped_false_passes"
        ],
        "attestation_scoped_controls_passed": summary[
            "attestation_scoped_controls_passed"
        ],
    }
    audit["passed"] = (
        source_checks == 160
        and effective_matches == 32
        and audit["producer_scoped_false_passes"] == 128
        and audit["attestation_scoped_false_passes"] == 0
        and audit["attestation_scoped_controls_passed"] == 32
        and summary["passed"]
    )
    OUT.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(json.dumps(audit, indent=2, sort_keys=True))
    raise SystemExit(0 if audit["passed"] else 1)


if __name__ == "__main__":
    main()
