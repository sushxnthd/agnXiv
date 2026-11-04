#!/usr/bin/env python3
"""Independent zero-production-import audit of execution-scoped commitments."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SOURCE = Path("research/results/authority-registry-checkpoint-execution-scope.json.gz")
OUT = Path("research/results/authority-registry-checkpoint-execution-scope-audit.json")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def linked_digest(registry, previous):
    return digest({"authority_registry_sha256": digest(registry), "minimum_registry_epoch": registry["registry_epoch"], "previous_statement_sha256": previous, "registry_namespace": registry["registry_namespace"]})


def consumer_digest(commitment, scope):
    return digest({"consumer_scope": scope, "history_commitment_sha256": commitment})


def execution_digest(commitment, scope):
    return digest({"execution_scope": scope, "scoped_history_commitment_sha256": commitment})


def verify_row(row, public_keys):
    previous = ""
    signatures = links = 0
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
        raise SystemExit("history commitment mismatch")
    consumer = consumer_digest(previous, row["consumer_scope"])
    if consumer != row["trusted_consumer_commitment"]:
        raise SystemExit("consumer commitment mismatch")
    execution = execution_digest(consumer, row["source_execution_scope"])
    if execution != row["trusted_execution_commitment"]:
        raise SystemExit("execution commitment mismatch")
    effective = execution_digest(consumer, row["effective_execution_scope"])
    return signatures, links, execution == effective


def main():
    with gzip.open(SOURCE, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    public_keys = {(row["issuer"], row["key_id"]): row["public_key_pem"] for row in payload["checkpoint_keys"]}
    rows = [*payload["attacks"], *payload["controls"]]
    signatures = links = matched = 0
    for row in rows:
        row_signatures, row_links, row_matched = verify_row(row, public_keys)
        signatures += row_signatures
        links += row_links
        matched += row_matched
    attacks, controls = payload["attacks"], payload["controls"]
    report = {
        "production_module_imports": 0,
        "verified_signatures": signatures,
        "reconstructed_registry_digests": len(rows) * 3,
        "recursive_statement_links": links,
        "history_commitment_checks": len(rows),
        "consumer_scope_payload_checks": len(rows),
        "execution_scope_payload_checks": len(rows) * 2,
        "matched_execution_envelopes": matched,
        "attack_total": len(attacks),
        "consumer_scoped_false_passes": sum(row["consumer_scoped_commitment_definitive"] for row in attacks),
        "execution_scoped_false_passes": sum(row["execution_scoped_commitment_definitive"] for row in attacks),
        "control_total": len(controls),
        "execution_scoped_controls_passed": sum(row["execution_scoped_commitment_definitive"] for row in controls),
    }
    report["passed"] = signatures == 960 and links == 320 and report["reconstructed_registry_digests"] == 480 and report["history_commitment_checks"] == 160 and report["consumer_scope_payload_checks"] == 160 and report["execution_scope_payload_checks"] == 320 and matched == 32 and report["consumer_scoped_false_passes"] == 128 and report["execution_scoped_false_passes"] == 0 and report["execution_scoped_controls_passed"] == 32 and payload["summary"]["passed"]
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
