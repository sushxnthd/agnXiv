#!/usr/bin/env python3
"""Independent zero-agnXiv-import audit of disclosed checkpoint equivocation."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization

SRC = Path("research/results/authority-registry-checkpoint-equivocation.json")
OUT = Path("research/results/authority-registry-checkpoint-equivocation-audit.json")


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def digest(registry):
    return hashlib.sha256(canonical(registry)).hexdigest()


def audit_row(row, key_map, policy):
    groups = defaultdict(lambda: {"identities": set(), "domains": set()})
    signatures = 0
    for signed in row["supplied_checkpoints"]:
        scope = signed["scope"]
        identity = (scope["issuer"], scope["key_id"])
        key = key_map.get(identity)
        if key is None or key["status"] != "active":
            continue
        try:
            public = serialization.load_pem_public_key(key["public_key_pem"].encode())
            public.verify(
                base64.b64decode(signed["signature_b64"], validate=True),
                canonical(scope),
            )
        except (ValueError, TypeError, binascii.Error, InvalidSignature):
            continue
        signatures += 1
        statement = (
            scope["registry_namespace"],
            scope["minimum_registry_epoch"],
            scope["authority_registry_sha256"],
        )
        groups[statement]["identities"].add(identity)
        if key["trust_domain"] is not None:
            groups[statement]["domains"].add(key["trust_domain"])
    qualifying = [
        statement
        for statement, support in groups.items()
        if len(support["identities"]) >= policy["minimum_signatures"]
        and len(support["domains"]) >= policy["minimum_trust_domains"]
    ]
    by_epoch = defaultdict(set)
    for namespace, epoch, registry_digest in qualifying:
        by_epoch[(namespace, epoch)].add(registry_digest)
    equivocation = any(len(digests) > 1 for digests in by_epoch.values())
    supplied_digest = digest(row["supplied_registry"])
    conflicting = row["conflicting_registry"]
    digests_match = supplied_digest == row["supplied_registry_sha256"]
    if conflicting is not None:
        digests_match = digests_match and (
            digest(conflicting) == row["conflicting_registry_sha256"]
        )
    parent = bool(qualifying) and qualifying[0][2] == supplied_digest
    corrected = bool(qualifying) and not equivocation and any(
        registry_digest == supplied_digest
        for _, _, registry_digest in qualifying
    )
    return {
        "signatures": signatures,
        "digests_match": digests_match,
        "parent_matched": parent == row["parent_snapshot_definitive"],
        "corrected_matched": corrected == row["equivocation_bound_definitive"],
        "reversed_matched": corrected == row["reversed_order_definitive"],
        "corrected_definitive": corrected,
    }


def main():
    before = {name for name in sys.modules if name.startswith("agnxiv")}
    report = json.loads(SRC.read_text(encoding="utf-8"))
    key_map = {
        (key["issuer"], key["key_id"]): key for key in report["checkpoint_keys"]
    }
    attacks = [
        audit_row(row, key_map, report["quorum_policy"])
        for row in report["attacks"]
    ]
    controls = [
        audit_row(row, key_map, report["quorum_policy"])
        for row in report["controls"]
    ]
    rows = attacks + controls
    imports = len({name for name in sys.modules if name.startswith("agnxiv")} - before)
    result = {
        "schema": "agnxiv.authority-registry-checkpoint-equivocation-audit/1",
        "production_imports": imports,
        "attack_total": len(attacks),
        "attacks_reproduced": sum(
            row["parent_matched"]
            and row["corrected_matched"]
            and row["reversed_matched"]
            and not row["corrected_definitive"]
            for row in attacks
        ),
        "control_total": len(controls),
        "controls_reproduced": sum(
            row["parent_matched"]
            and row["corrected_matched"]
            and row["reversed_matched"]
            and row["corrected_definitive"]
            for row in controls
        ),
        "valid_signatures_checked": sum(row["signatures"] for row in rows),
        "registry_digest_sets_reproduced": sum(row["digests_match"] for row in rows),
    }
    result["passed"] = (
        imports == 0
        and result["attacks_reproduced"] == result["attack_total"] == 128
        and result["controls_reproduced"] == result["control_total"] == 32
        and result["valid_signatures_checked"] == 576
        and result["registry_digest_sets_reproduced"] == 160
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
