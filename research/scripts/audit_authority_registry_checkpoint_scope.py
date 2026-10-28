#!/usr/bin/env python3
"""Independent stdlib-only audit of checkpoint-scope evidence."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SRC = Path("research/results/authority-registry-checkpoint-scope.json")
OUT = Path("research/results/authority-registry-checkpoint-scope-audit.json")


def digest(value):
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def audit_row(row, *, control):
    registry = row["registry"]
    checkpoint = row["checkpoint"]
    scope = row["signed_scope"]
    namespace_match = (
        registry["registry_namespace"] == checkpoint["registry_namespace"]
    )
    digest_match = row["registry_sha256"] == digest(registry)
    signature_scope_match = scope["authority_registry_sha256"] == row["registry_sha256"]
    epoch_fresh = registry["registry_epoch"] >= checkpoint["minimum_registry_epoch"]
    blocked_for_scope = any(
        "checkpoint namespace does not match" in reason
        for reason in row["corrected_reasons"]
    )
    expected_corrected = namespace_match and epoch_fresh
    matched = (
        digest_match
        and signature_scope_match
        and row["parent_definitive"]
        and row["corrected_definitive"] == expected_corrected
        and (control == namespace_match)
        and (control or blocked_for_scope)
    )
    return {
        "case": row["case"],
        "family": row["family"],
        "namespace_match": namespace_match,
        "registry_digest_reproduced": digest_match,
        "signed_scope_digest_matches": signature_scope_match,
        "epoch_fresh": epoch_fresh,
        "parent_definitive": row["parent_definitive"],
        "corrected_definitive": row["corrected_definitive"],
        "matched": matched,
    }


def main() -> None:
    before = {name for name in sys.modules if name.startswith("agnxiv")}
    source = json.loads(SRC.read_text(encoding="utf-8"))
    attacks = [audit_row(row, control=False) for row in source["attacks"]]
    controls = [audit_row(row, control=True) for row in source["controls"]]
    result = {
        "schema": "agnxiv.authority-registry-checkpoint-scope-audit/1",
        "agnxiv_imports": len(
            {name for name in sys.modules if name.startswith("agnxiv")} - before
        ),
        "attack_total": len(attacks),
        "attacks_reproduced": sum(row["matched"] for row in attacks),
        "control_total": len(controls),
        "controls_reproduced": sum(row["matched"] for row in controls),
        "attacks": attacks,
        "controls": controls,
    }
    result["passed"] = (
        result["agnxiv_imports"] == 0
        and result["attacks_reproduced"] == result["attack_total"] == 128
        and result["controls_reproduced"] == result["control_total"] == 32
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key not in ("attacks", "controls")}, indent=2, sort_keys=True))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
