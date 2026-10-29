#!/usr/bin/env python3
"""Independent zero-production-import audit of pinned checkpoint roots."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SOURCE = Path("research/results/authority-registry-checkpoint-pinned-root.json.gz")
OUT = Path("research/results/authority-registry-checkpoint-pinned-root-audit.json")


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
    pin_checks = 0
    for row in [*payload["attacks"], *payload["controls"]]:
        for label in ("root", "prior", "current"):
            registry = row[f"{label}_registry"]
            if digest(registry) != row[f"{label}_registry_sha256"]:
                raise SystemExit("registry digest mismatch")
            registry_digests += 1
        root_statement = statement_digest(row["root_registry"])
        prior_statement = statement_digest(row["prior_registry"])
        if root_statement != row["trusted_root_statement_sha256"]:
            raise SystemExit("trusted root statement mismatch")
        if prior_statement != row["prior_statement_sha256"]:
            raise SystemExit("prior statement mismatch")
        if any(
            checkpoint["scope"]["previous_statement_sha256"] != prior_statement
            for checkpoint in row["current_checkpoints"]
        ):
            raise SystemExit("current history link mismatch")
        statement_links += 1
        supplied = row["observed_checkpoints"]
        oldest_scope = min(
            (checkpoint["scope"] for checkpoint in supplied),
            key=lambda scope: scope["minimum_registry_epoch"],
        )
        oldest_statement = digest(
            {
                "authority_registry_sha256": oldest_scope["authority_registry_sha256"],
                "minimum_registry_epoch": oldest_scope["minimum_registry_epoch"],
                "registry_namespace": oldest_scope["registry_namespace"],
            }
        )
        if row["control"]:
            if oldest_statement != root_statement:
                raise SystemExit("complete control does not start at pinned root")
        elif oldest_statement == root_statement:
            raise SystemExit("truncation attack unexpectedly supplies pinned root")
        pin_checks += 1
        for checkpoint in [*supplied, *row["current_checkpoints"]]:
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
        "trusted_root_pin_checks": pin_checks,
        "attack_total": len(attacks),
        "parent_false_passes": sum(row["parent_definitive"] for row in attacks),
        "pinned_root_false_passes": sum(
            row["pinned_definitive"] for row in attacks
        ),
        "complete_history_controls_passed": sum(
            row["pinned_definitive"] for row in controls
        ),
        "control_total": len(controls),
    }
    report["passed"] = (
        signatures == 704
        and registry_digests == 480
        and statement_links == 160
        and pin_checks == 160
        and report["parent_false_passes"] == report["attack_total"] == 128
        and report["pinned_root_false_passes"] == 0
        and report["complete_history_controls_passed"]
        == report["control_total"]
        == 32
    )
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
