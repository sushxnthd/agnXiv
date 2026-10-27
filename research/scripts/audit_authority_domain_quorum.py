#!/usr/bin/env python3
"""Independent authority-domain replay with no agnXiv imports."""

import base64
import json
import sys
from datetime import datetime
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SRC = Path("research/results/authority-domain-quorum.json")
OUT = Path("research/results/authority-domain-quorum-audit.json")


def payload(scope):
    return json.dumps(scope, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def valid_identities(row, registry_keys, now):
    keys = {(k["issuer"], k["key_id"]): k for k in registry_keys}
    accepted = set()
    domains = set()
    for attestation in row["attestations"]:
        scope = attestation["scope"]
        identity = (scope["issuer"], scope["key_id"])
        key_data = keys.get(identity)
        if key_data is None or key_data["status"] != "active":
            continue
        if not (datetime.fromisoformat(scope["issued_at"]) <= now < datetime.fromisoformat(scope["expires_at"])):
            continue
        try:
            key = serialization.load_pem_public_key(key_data["public_key_pem"].encode())
            assert isinstance(key, Ed25519PublicKey)
            key.verify(base64.b64decode(attestation["signature_b64"], validate=True), payload(scope))
        except (AssertionError, InvalidSignature, ValueError):
            continue
        accepted.add(identity)
        if key_data["trust_domain"] is not None:
            domains.add(key_data["trust_domain"])
    return accepted, domains


def main():
    before = {x for x in sys.modules if x.startswith("agnxiv")}
    src = json.loads(SRC.read_text())
    now = datetime.fromisoformat(src["validation_time"])
    attack_checks = []
    families = {}
    for row in src["attacks"]:
        identities, domains = valid_identities(row, src["registries"][row["family"]], now)
        parent = len(identities) >= 2
        corrected = parent and len(domains) >= 2
        ok = parent == row["parent_definitive"] and corrected == row["corrected_definitive"]
        attack_checks.append(ok and parent and not corrected)
        families[row["family"]] = families.get(row["family"], 0) + (ok and parent and not corrected)
    control_checks = []
    for row in src["controls"]:
        identities, domains = valid_identities(row, src["registries"]["control"], now)
        replayed = len(identities) >= 2 and len(domains) >= 2
        control_checks.append(replayed and replayed == row["corrected_definitive"])
    report = {
        "schema": "agnxiv.authority-domain-quorum-audit/1",
        "production_imports": len({x for x in sys.modules if x.startswith("agnxiv")} - before),
        "attacks_replayed": sum(attack_checks),
        "attack_total": len(attack_checks),
        "controls_replayed": sum(control_checks),
        "control_total": len(control_checks),
        "attack_families": families,
    }
    report["passed"] = (
        report["production_imports"] == 0
        and report["attacks_replayed"] == 128
        and report["controls_replayed"] == 32
        and all(v == 32 for v in families.values())
    )
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
