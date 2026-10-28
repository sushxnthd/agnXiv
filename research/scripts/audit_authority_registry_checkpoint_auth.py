#!/usr/bin/env python3
"""Independent stdlib-only audit of checkpoint-authentication evidence."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SRC = Path("research/results/authority-registry-checkpoint-auth.json")
OUT = Path("research/results/authority-registry-checkpoint-auth-audit.json")


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def audit_row(row, *, control):
    legitimate = row["legitimate_checkpoint_scope"]
    supplied = row["supplied_checkpoint_scope"]
    payload_changed = digest(legitimate) != digest(supplied)
    expected_changed = not control
    signature_attack = row["signature_reused"] and payload_changed
    blocked_for_signature = any(
        "checkpoint signature is invalid" in reason
        for reason in row["corrected_reasons"]
    )
    matched = (
        row["parent_definitive"]
        and payload_changed == expected_changed
        and row["legitimate_payload_sha256"] == digest(legitimate)
        and row["supplied_payload_sha256"] == digest(supplied)
        and row["corrected_definitive"] == control
        and (control or (signature_attack and blocked_for_signature))
    )
    return {
        "case": row["case"],
        "family": row["family"],
        "control": control,
        "payload_changed": payload_changed,
        "signature_reused": row["signature_reused"],
        "corrected_definitive": row["corrected_definitive"],
        "matched": matched,
    }


def main() -> None:
    before = {name for name in sys.modules if name.startswith("agnxiv")}
    source = json.loads(SRC.read_text(encoding="utf-8"))
    attacks = [audit_row(row, control=False) for row in source["attacks"]]
    controls = [audit_row(row, control=True) for row in source["controls"]]
    result = {
        "schema": "agnxiv.authority-registry-checkpoint-auth-audit/1",
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
    print(
        json.dumps(
            {key: value for key, value in result.items() if key not in ("attacks", "controls")},
            indent=2,
            sort_keys=True,
        )
    )
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
