#!/usr/bin/env python3
"""Independent zero-agnXiv-import audit of checkpoint-history consistency."""

from __future__ import annotations

import base64
import binascii
import gzip
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization

SRC = Path("research/results/authority-registry-checkpoint-history.json.gz")
OUT = Path("research/results/authority-registry-checkpoint-history-audit.json")


def canonical(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(r):
    return hashlib.sha256(canonical(r)).hexdigest()


def qualifying(rows, key_map, policy):
    groups = defaultdict(lambda: {"identities": set(), "domains": set()})
    signatures = 0
    for signed in rows:
        scope = signed["scope"]
        identity = (scope["issuer"], scope["key_id"])
        key = key_map.get(identity)
        if key is None or key["status"] != "active":
            continue
        try:
            public = serialization.load_pem_public_key(key["public_key_pem"].encode())
            public.verify(
                base64.b64decode(signed["signature_b64"], validate=True), canonical(scope)
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
    return [
        s
        for s, x in groups.items()
        if len(x["identities"]) >= policy["minimum_signatures"]
        and len(x["domains"]) >= policy["minimum_trust_domains"]
    ], signatures


def audit_row(row, key_map, policy):
    current, cs = qualifying(row["current_checkpoints"], key_map, policy)
    observed, os = qualifying(row["observed_checkpoints"], key_map, policy)
    supplied = digest(row["supplied_registry"])
    matches = any(d == supplied for _, _, d in current)
    by_epoch = defaultdict(set)
    for namespace, epoch, d in current + observed:
        by_epoch[(namespace, epoch)].add(d)
    equivocation = any(len(ds) > 1 for ds in by_epoch.values())
    parent = bool(current) and matches
    corrected = parent and bool(observed) and not equivocation
    return {
        "signatures": cs + os,
        "digest_matched": supplied == row["supplied_registry_sha256"],
        "parent_matched": parent == row["parent_definitive"],
        "corrected_matched": corrected == row["history_bound_definitive"],
        "reversed_matched": corrected == row["reversed_order_definitive"],
        "corrected_definitive": corrected,
    }


def main():
    before = {n for n in sys.modules if n.startswith("agnxiv")}
    with gzip.open(SRC, "rt", encoding="utf-8") as source:
        report = json.load(source)
    key_map = {(k["issuer"], k["key_id"]): k for k in report["checkpoint_keys"]}
    policy = report["quorum_policy"]
    attacks = [audit_row(r, key_map, policy) for r in report["attacks"]]
    matching = [audit_row(r, key_map, policy) for r in report["matching_controls"]]
    prior = [audit_row(r, key_map, policy) for r in report["prior_epoch_controls"]]
    rows = attacks + matching + prior
    good = lambda r, w: (
        r["parent_matched"]
        and r["corrected_matched"]
        and r["reversed_matched"]
        and r["corrected_definitive"] == w
    )
    result = {
        "schema": "agnxiv.authority-registry-checkpoint-history-audit/1",
        "production_imports": len({n for n in sys.modules if n.startswith("agnxiv")} - before),
        "attack_total": len(attacks),
        "attacks_reproduced": sum(good(r, False) for r in attacks),
        "matching_control_total": len(matching),
        "matching_controls_reproduced": sum(good(r, True) for r in matching),
        "prior_epoch_control_total": len(prior),
        "prior_epoch_controls_reproduced": sum(good(r, True) for r in prior),
        "valid_signatures_checked": sum(r["signatures"] for r in rows),
        "registry_digests_reproduced": sum(r["digest_matched"] for r in rows),
    }
    result["passed"] = (
        result["production_imports"] == 0
        and result["attacks_reproduced"] == result["attack_total"] == 128
        and result["matching_controls_reproduced"] == result["matching_control_total"] == 32
        and result["prior_epoch_controls_reproduced"] == result["prior_epoch_control_total"] == 32
        and result["valid_signatures_checked"] == 768
        and result["registry_digests_reproduced"] == 192
    )
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
