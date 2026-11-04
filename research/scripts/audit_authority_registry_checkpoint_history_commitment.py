#!/usr/bin/env python3
"""Independent zero-production-import audit of recursive history commitments."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SOURCE = Path(
    "research/results/authority-registry-checkpoint-history-commitment.json.gz"
)
OUT = Path(
    "research/results/authority-registry-checkpoint-history-commitment-audit.json"
)


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


def linked_digest(registry, previous):
    return digest(
        {
            "authority_registry_sha256": digest(registry),
            "minimum_registry_epoch": registry["registry_epoch"],
            "previous_statement_sha256": previous,
            "registry_namespace": registry["registry_namespace"],
        }
    )


def verify_chain(checkpoints, registries, keys, *, recursive):
    signatures = 0
    links = 0
    if len(checkpoints) != 6:
        raise SystemExit("checkpoint chain does not contain three quorums")
    previous = ""
    for index, registry in enumerate(registries):
        quorum = checkpoints[2 * index : 2 * index + 2]
        if len(quorum) != 2:
            raise SystemExit("checkpoint quorum is incomplete")
        expected_previous = previous
        for checkpoint in quorum:
            scope = checkpoint["scope"]
            if scope["registry_namespace"] != registry["registry_namespace"]:
                raise SystemExit("checkpoint namespace mismatch")
            if scope["minimum_registry_epoch"] != registry["registry_epoch"]:
                raise SystemExit("checkpoint epoch mismatch")
            if scope["authority_registry_sha256"] != digest(registry):
                raise SystemExit("checkpoint registry digest mismatch")
            if scope["previous_statement_sha256"] != expected_previous:
                raise SystemExit("checkpoint predecessor mismatch")
            public = serialization.load_pem_public_key(
                keys[(scope["issuer"], scope["key_id"])].encode()
            )
            if not isinstance(public, Ed25519PublicKey):
                raise SystemExit("checkpoint key is not Ed25519")
            public.verify(base64.b64decode(checkpoint["signature_b64"]), canonical(scope))
            signatures += 1
        if index:
            links += 1
        previous = (
            linked_digest(registry, previous)
            if recursive
            else statement_digest(registry)
        )
    return signatures, links, previous


def main():
    with gzip.open(SOURCE, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    keys = {
        (row["issuer"], row["key_id"]): row["public_key_pem"]
        for row in payload["checkpoint_keys"]
    }
    signatures = 0
    registry_digests = 0
    legacy_links = 0
    recursive_links = 0
    root_checks = 0
    tip_checks = 0
    commitment_checks = 0
    rows = [*payload["attacks"], *payload["controls"]]
    for row in rows:
        root = row["root_registry"]
        honest = row["honest_middle_registry"]
        fork = row["fork_middle_registry"]
        final = row["final_registry"]
        for registry in (root, honest, fork, final):
            if len(digest(registry)) != 64:
                raise SystemExit("registry digest is invalid")
            registry_digests += 1
        if statement_digest(root) != row["root_pin"]:
            raise SystemExit("trusted root pin mismatch")
        if statement_digest(final) != row["tip_pin"]:
            raise SystemExit("trusted tip pin mismatch")
        root_checks += 1
        tip_checks += 1
        count, links, _ = verify_chain(
            row["legacy_fork_checkpoints"], (root, fork, final), keys, recursive=False
        )
        signatures += count
        legacy_links += links
        count, links, honest_commitment = verify_chain(
            row["recursive_honest_checkpoints"],
            (root, honest, final),
            keys,
            recursive=True,
        )
        signatures += count
        recursive_links += links
        count, links, fork_commitment = verify_chain(
            row["recursive_fork_checkpoints"],
            (root, fork, final),
            keys,
            recursive=True,
        )
        signatures += count
        recursive_links += links
        if honest_commitment != row["trusted_history_commitment"]:
            raise SystemExit("trusted recursive commitment mismatch")
        if fork_commitment != row["fork_history_commitment"]:
            raise SystemExit("fork recursive commitment mismatch")
        if honest_commitment == fork_commitment:
            raise SystemExit("path substitution did not change final commitment")
        commitment_checks += 2
    attacks = payload["attacks"]
    controls = payload["controls"]
    summary = payload["summary"]
    report = {
        "production_module_imports": 0,
        "verified_signatures": signatures,
        "reconstructed_registry_digests": registry_digests,
        "legacy_statement_links": legacy_links,
        "recursive_statement_links": recursive_links,
        "trusted_root_pin_checks": root_checks,
        "trusted_tip_pin_checks": tip_checks,
        "recursive_commitment_checks": commitment_checks,
        "attack_total": len(attacks),
        "parent_endpoint_pinning_false_passes": sum(
            row["parent_endpoint_pinning_definitive"] for row in attacks
        ),
        "recursive_commitment_false_passes": sum(
            row["recursive_commitment_definitive"] for row in attacks
        ),
        "recursive_commitment_controls_passed": sum(
            row["recursive_commitment_definitive"] for row in controls
        ),
        "control_total": len(controls),
    }
    report["passed"] = (
        signatures == 2880
        and registry_digests == 640
        and legacy_links == 320
        and recursive_links == 640
        and root_checks == tip_checks == 160
        and commitment_checks == 320
        and report["parent_endpoint_pinning_false_passes"]
        == report["attack_total"]
        == 128
        and report["recursive_commitment_false_passes"] == 0
        and report["recursive_commitment_controls_passed"]
        == report["control_total"]
        == 32
        and summary["passed"]
    )
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
