#!/usr/bin/env python3
"""Independent zero-import audit of checkpoint-quorum evidence."""

from __future__ import annotations

import base64
import binascii
import json
import sys
from collections import defaultdict
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization

SRC = Path("research/results/authority-registry-checkpoint-quorum.json")
OUT = Path("research/results/authority-registry-checkpoint-quorum-audit.json")


def canonical(scope):
    return json.dumps(
        scope,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


def audit_row(row, key_map, policy):
    groups = defaultdict(lambda: {"identities": set(), "domains": set()})
    signatures_valid = True
    for signed in row["supplied_checkpoints"]:
        scope = signed["scope"]
        identity = (scope["issuer"], scope["key_id"])
        key = key_map.get(identity)
        if key is None or key["status"] != "active":
            signatures_valid = False
            continue
        try:
            public = serialization.load_pem_public_key(key["public_key_pem"].encode())
            public.verify(base64.b64decode(signed["signature_b64"], validate=True), canonical(scope))
        except (ValueError, TypeError, binascii.Error, InvalidSignature):
            signatures_valid = False
            continue
        statement = (scope["registry_namespace"], scope["minimum_registry_epoch"])
        groups[statement]["identities"].add(identity)
        if key["trust_domain"] is not None:
            groups[statement]["domains"].add(key["trust_domain"])
    qualifying = [
        statement
        for statement, support in groups.items()
        if len(support["identities"]) >= policy["minimum_signatures"]
        and len(support["domains"]) >= policy["minimum_trust_domains"]
    ]
    effective = max((floor for namespace, floor in qualifying if namespace == "production-release"), default=None)
    decisive = effective is not None and row["registry_epoch"] >= effective
    return {
        "case": row["case"],
        "signatures_valid": signatures_valid,
        "independent_quorum_definitive": decisive,
        "production_quorum_definitive": row["quorum_definitive"],
        "matched": decisive == row["quorum_definitive"],
    }


def main():
    before = {name for name in sys.modules if name.startswith("agnxiv")}
    report = json.loads(SRC.read_text(encoding="utf-8"))
    policy = report["quorum_policy"]
    key_map = {
        (key["issuer"], key["key_id"]): key for key in report["checkpoint_keys"]
    }
    attacks = [audit_row(row, key_map, policy) for row in report["attacks"]]
    controls = [audit_row(row, key_map, policy) for row in report["controls"]]
    imports = len({name for name in sys.modules if name.startswith("agnxiv")} - before)
    result = {
        "schema": "agnxiv.authority-registry-checkpoint-quorum-audit/1",
        "production_imports": imports,
        "attack_total": len(attacks),
        "attacks_reproduced": sum(row["matched"] and not row["independent_quorum_definitive"] for row in attacks),
        "control_total": len(controls),
        "controls_reproduced": sum(row["matched"] and row["independent_quorum_definitive"] for row in controls),
        "valid_signatures_checked": sum(row["signatures_valid"] for row in attacks + controls),
        "adversarial_controls_blocked": sum(not row["definitive"] for row in report["adversarial_controls"]),
    }
    result["passed"] = (
        imports == 0
        and result["attacks_reproduced"] == result["attack_total"] == 128
        and result["controls_reproduced"] == result["control_total"] == 32
        and result["valid_signatures_checked"] == 160
        and result["adversarial_controls_blocked"] == 4
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
