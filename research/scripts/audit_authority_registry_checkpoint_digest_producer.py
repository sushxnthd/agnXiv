#!/usr/bin/env python3
"""Zero-production-import audit of digest-producer substitution evidence."""
import gzip
import hashlib
import json
from pathlib import Path

SOURCE = Path("research/results/authority-registry-checkpoint-digest-producer.json.gz")
OUT = Path("research/results/authority-registry-checkpoint-digest-producer-audit.json")


def commitment(parent, producer):
    payload = json.dumps(
        {
            "digest_profile_scoped_history_commitment_sha256": parent,
            "producer_scope": producer,
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
        commitment(row["profile_commitment"], row["source_producer"])
        == row["trusted_producer_commitment"]
        for row in rows
    )
    effective_matches = sum(
        commitment(row["profile_commitment"], row["effective_producer"])
        == row["trusted_producer_commitment"]
        for row in rows
    )
    summary = report["summary"]
    audit = {
        "schema": "agnxiv.authority-registry-checkpoint-digest-producer-audit/1",
        "production_imports": 0,
        "producer_payload_checks": len(rows) * 2,
        "source_commitments_reconstructed": source_checks,
        "effective_commitments_matching": effective_matches,
        "profile_scoped_false_passes": summary["profile_scoped_false_passes"],
        "producer_scoped_false_passes": summary["producer_scoped_false_passes"],
        "producer_scoped_controls_passed": summary[
            "producer_scoped_controls_passed"
        ],
    }
    audit["passed"] = (
        source_checks == 160
        and effective_matches == 32
        and audit["profile_scoped_false_passes"] == 128
        and audit["producer_scoped_false_passes"] == 0
        and audit["producer_scoped_controls_passed"] == 32
        and summary["passed"]
    )
    OUT.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(json.dumps(audit, indent=2, sort_keys=True))
    raise SystemExit(0 if audit["passed"] else 1)


if __name__ == "__main__":
    main()
