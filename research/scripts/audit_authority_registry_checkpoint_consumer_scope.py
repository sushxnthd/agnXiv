#!/usr/bin/env python3
"""Independent zero-production-import audit of consumer-scoped commitments."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SOURCE = Path("research/results/authority-registry-checkpoint-consumer-scope.json.gz")
OUT = Path("research/results/authority-registry-checkpoint-consumer-scope-audit.json")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def linked_digest(registry, previous):
    return digest({"authority_registry_sha256": digest(registry), "minimum_registry_epoch": registry["registry_epoch"], "previous_statement_sha256": previous, "registry_namespace": registry["registry_namespace"]})


def scoped_digest(commitment, scope):
    return digest({"consumer_scope": scope, "history_commitment_sha256": commitment})


def verify_row(row, public_keys):
    previous = ""
    signatures = 0
    links = 0
    for index, registry in enumerate(row["registries"]):
        for checkpoint in row["checkpoints"][2 * index : 2 * index + 2]:
            scope = checkpoint["scope"]
            if scope["registry_namespace"] != registry["registry_namespace"] or scope["minimum_registry_epoch"] != registry["registry_epoch"] or scope["authority_registry_sha256"] != digest(registry) or scope["previous_statement_sha256"] != previous:
                raise SystemExit("checkpoint statement mismatch")
            public = serialization.load_pem_public_key(public_keys[(scope["issuer"], scope["key_id"])].encode())
            if not isinstance(public, Ed25519PublicKey):
                raise SystemExit("checkpoint key is not Ed25519")
            public.verify(base64.b64decode(checkpoint["signature_b64"]), canonical(scope))
            signatures += 1
        if index:
            links += 1
        previous = linked_digest(registry, previous)
    if previous != row["history_commitment"]:
        raise SystemExit("recursive history commitment mismatch")
    source_envelope = scoped_digest(previous, row["source_scope"])
    if source_envelope != row["trusted_scoped_commitment"]:
        raise SystemExit("trusted consumer envelope mismatch")
    return signatures, links, source_envelope == scoped_digest(previous, row["effective_scope"])


def main():
    with gzip.open(SOURCE, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    public_keys = {(row["issuer"], row["key_id"]): row["public_key_pem"] for row in payload["checkpoint_keys"]}
    signatures = links = matched_envelopes = 0
    rows = [*payload["attacks"], *payload["controls"]]
    for row in rows:
        row_signatures, row_links, matched = verify_row(row, public_keys)
        signatures += row_signatures
        links += row_links
        matched_envelopes += matched
    attacks, controls = payload["attacks"], payload["controls"]
    report = {
        "production_module_imports": 0,
        "verified_signatures": signatures,
        "reconstructed_registry_digests": len(rows) * 3,
        "recursive_statement_links": links,
        "history_commitment_checks": len(rows),
        "consumer_scope_payload_checks": len(rows) * 2,
        "matched_consumer_envelopes": matched_envelopes,
        "attack_total": len(attacks),
        "parent_recursive_commitment_false_passes": sum(row["parent_recursive_commitment_definitive"] for row in attacks),
        "consumer_scoped_false_passes": sum(row["consumer_scoped_commitment_definitive"] for row in attacks),
        "control_total": len(controls),
        "consumer_scoped_controls_passed": sum(row["consumer_scoped_commitment_definitive"] for row in controls),
    }
    report["passed"] = signatures == 960 and links == 320 and report["reconstructed_registry_digests"] == 480 and report["history_commitment_checks"] == 160 and report["consumer_scope_payload_checks"] == 320 and matched_envelopes == 32 and report["parent_recursive_commitment_false_passes"] == 128 and report["consumer_scoped_false_passes"] == 0 and report["consumer_scoped_controls_passed"] == 32 and payload["summary"]["passed"]
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
