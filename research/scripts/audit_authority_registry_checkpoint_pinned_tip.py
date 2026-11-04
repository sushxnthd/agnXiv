#!/usr/bin/env python3
"""Independent zero-production-import audit of pinned checkpoint tips."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SOURCE = Path("research/results/authority-registry-checkpoint-pinned-tip.json.gz")
OUT = Path("research/results/authority-registry-checkpoint-pinned-tip-audit.json")


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
    root_checks = 0
    tip_checks = 0
    rows = [*payload["attacks"], *payload["controls"]]
    for row in rows:
        statements = []
        expected_statement_keys = {
            "root": "trusted_root_statement_sha256",
            "prior": "prior_statement_sha256",
            "stale": "stale_statement_sha256",
            "newest": "trusted_tip_statement_sha256",
        }
        for label in ("root", "prior", "stale", "newest"):
            registry = row[f"{label}_registry"]
            if digest(registry) != row[f"{label}_registry_sha256"]:
                raise SystemExit("registry digest mismatch")
            statement = statement_digest(registry)
            if statement != row[expected_statement_keys[label]]:
                raise SystemExit("statement digest mismatch")
            statements.append(statement)
            registry_digests += 1
        if statements[0] != row["trusted_root_statement_sha256"]:
            raise SystemExit("trusted root mismatch")
        if statements[-1] != row["trusted_tip_statement_sha256"]:
            raise SystemExit("trusted tip mismatch")
        root_checks += 1
        tip_checks += 1
        all_checkpoints = [
            *row["observed_checkpoints"],
            *row["current_checkpoints"],
            *row["withheld_tip_checkpoints"],
        ]
        by_epoch = {}
        for checkpoint in all_checkpoints:
            scope = checkpoint["scope"]
            by_epoch.setdefault(scope["minimum_registry_epoch"], []).append(checkpoint)
            public = serialization.load_pem_public_key(
                keys[(scope["issuer"], scope["key_id"])].encode()
            )
            if not isinstance(public, Ed25519PublicKey):
                raise SystemExit("checkpoint key is not Ed25519")
            public.verify(base64.b64decode(checkpoint["signature_b64"]), canonical(scope))
            signatures += 1
        ordered = [by_epoch[epoch] for epoch in sorted(by_epoch)]
        if len(ordered) != 4 or any(len(quorum) != 2 for quorum in ordered):
            raise SystemExit("complete four-epoch evidence is missing")
        for index, quorum in enumerate(ordered):
            scopes = [checkpoint["scope"] for checkpoint in quorum]
            if any(
                scope["authority_registry_sha256"]
                != row[f"{('root', 'prior', 'stale', 'newest')[index]}_registry_sha256"]
                for scope in scopes
            ):
                raise SystemExit("checkpoint snapshot mismatch")
            if index:
                if any(
                    scope["previous_statement_sha256"] != statements[index - 1]
                    for scope in scopes
                ):
                    raise SystemExit("history link mismatch")
                statement_links += 1
        if row["control"]:
            if row["withheld_tip_checkpoints"]:
                raise SystemExit("control unexpectedly withholds tip")
        elif not row["withheld_tip_checkpoints"]:
            raise SystemExit("attack does not preserve withheld tip evidence")
    attacks = payload["attacks"]
    controls = payload["controls"]
    report = {
        "production_module_imports": 0,
        "verified_signatures": signatures,
        "reconstructed_registry_digests": registry_digests,
        "reconstructed_statement_links": statement_links,
        "trusted_root_pin_checks": root_checks,
        "trusted_tip_pin_checks": tip_checks,
        "attack_total": len(attacks),
        "parent_rooted_false_passes": sum(
            row["parent_rooted_definitive"] for row in attacks
        ),
        "pinned_tip_false_passes": sum(
            row["pinned_tip_definitive"] for row in attacks
        ),
        "complete_chain_controls_passed": sum(
            row["pinned_tip_definitive"] for row in controls
        ),
        "control_total": len(controls),
    }
    report["passed"] = (
        signatures == 1280
        and registry_digests == 640
        and statement_links == 480
        and root_checks == tip_checks == 160
        and report["parent_rooted_false_passes"] == report["attack_total"] == 128
        and report["pinned_tip_false_passes"] == 0
        and report["complete_chain_controls_passed"]
        == report["control_total"]
        == 32
    )
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
