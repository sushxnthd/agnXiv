#!/usr/bin/env python3
"""Independent audit of transitive checkpoint-history evidence."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SOURCE = Path("research/results/authority-registry-checkpoint-transitive-chain.json.gz")
OUT = Path("research/results/authority-registry-checkpoint-transitive-chain-audit.json")


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def statement_digest(registry):
    return digest(
        {
            "authority_registry_sha256": digest(registry),
            "minimum_registry_epoch": registry["registry_epoch"],
            "registry_namespace": registry["registry_namespace"],
        }
    )


def main():
    with gzip.open(SOURCE, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    keys = {
        (row["issuer"], row["key_id"]): row["public_key_pem"]
        for row in payload["checkpoint_keys"]
    }
    signatures = 0
    registry_digests = 0
    statement_links = 0
    for row in [*payload["attacks"], *payload["controls"]]:
        for label in ("root", "prior", "current"):
            registry = row[f"{label}_registry"]
            if digest(registry) != row[f"{label}_registry_sha256"]:
                raise SystemExit("registry digest mismatch")
            registry_digests += 1
        if statement_digest(row["root_registry"]) != row["expected_prior_link_sha256"]:
            raise SystemExit("root-to-prior statement digest mismatch")
        if statement_digest(row["prior_registry"]) != row["expected_current_link_sha256"]:
            raise SystemExit("prior-to-current statement digest mismatch")
        statement_links += 2
        for checkpoint in [*row["observed_checkpoints"], *row["current_checkpoints"]]:
            scope = checkpoint["scope"]
            public = serialization.load_pem_public_key(
                keys[(scope["issuer"], scope["key_id"])].encode()
            )
            if not isinstance(public, Ed25519PublicKey):
                raise SystemExit("checkpoint key is not Ed25519")
            public.verify(base64.b64decode(checkpoint["signature_b64"]), canonical(scope))
            signatures += 1
    attacks = payload["attacks"]
    controls = payload["controls"]
    report = {
        "production_module_imports": 0,
        "verified_signatures": signatures,
        "reconstructed_registry_digests": registry_digests,
        "reconstructed_statement_links": statement_links,
        "attack_total": len(attacks),
        "parent_false_passes": sum(row["parent_definitive"] for row in attacks),
        "transitive_false_passes": sum(
            row["transitive_definitive"] for row in attacks
        ),
        "linked_controls_passed": sum(
            row["transitive_definitive"] for row in controls
        ),
        "control_total": len(controls),
    }
    report["passed"] = (
        signatures == 960
        and registry_digests == 480
        and statement_links == 320
        and report["parent_false_passes"] == report["attack_total"] == 128
        and report["transitive_false_passes"] == 0
        and report["linked_controls_passed"] == report["control_total"] == 32
    )
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
