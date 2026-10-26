#!/usr/bin/env python3
"""Independent replay without agnXiv imports."""

import base64
import json
import sys
from datetime import datetime
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SRC = Path("research/results/authority-registry.json")
OUT = Path("research/results/authority-registry-audit.json")


def payload(s):
    return json.dumps(s, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sig(key, row):
    try:
        key.verify(base64.b64decode(row["signature_b64"], validate=True), payload(row["scope"]))
        return True
    except (InvalidSignature, ValueError):
        return False


def match(row):
    return all(
        row["scope"][k] == row["current_object"][k]
        for k in (
            "manuscript_sha256",
            "repository_tree_sha256",
            "claim_id",
            "metric",
            "authority_evidence_sha256",
        )
    )


def main():
    before = {x for x in sys.modules if x.startswith("agnxiv")}
    src = json.loads(SRC.read_text())
    key = serialization.load_pem_public_key(src["trusted_public_key_pem"].encode())
    assert isinstance(key, Ed25519PublicKey)
    now = datetime.fromisoformat(src["validation_time"])
    controls = [
        sig(key, r)
        and datetime.fromisoformat(r["scope"]["issued_at"])
        <= now
        < datetime.fromisoformat(r["scope"]["expires_at"])
        and r["definitive"]
        for r in src["controls"]
    ]
    checks = []
    families = {}
    for r in src["attacks"]:
        s = r["scope"]
        blocked = (
            not sig(key, r)
            or not match(r)
            or datetime.fromisoformat(s["issued_at"]) > now
            or datetime.fromisoformat(s["expires_at"]) <= now
        )
        ok = blocked and not r["definitive"]
        checks.append(ok)
        families[r["family"]] = families.get(r["family"], 0) + ok
    report = {
        "schema": "agnxiv.authority-registry-audit/1",
        "production_imports": len({x for x in sys.modules if x.startswith("agnxiv")} - before),
        "old_self_asserted_definitive": sum(r["old_definitive"] for r in src["self_asserted"]),
        "strict_self_asserted_definitive": sum(
            r["strict_definitive"] for r in src["self_asserted"]
        ),
        "controls_replayed": sum(controls),
        "control_total": len(controls),
        "attacks_replayed": sum(checks),
        "attack_total": len(checks),
        "attack_families": families,
    }
    report["passed"] = (
        report["production_imports"] == 0
        and report["old_self_asserted_definitive"] == 128
        and report["strict_self_asserted_definitive"] == 0
        and report["controls_replayed"] == 32
        and report["attacks_replayed"] == 192
        and all(v == 32 for v in families.values())
    )
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
