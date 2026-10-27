#!/usr/bin/env python3
"""Independent stdlib-only audit of registry snapshot binding evidence."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SRC = Path("research/results/authority-registry-snapshot.json")
OUT = Path("research/results/authority-registry-snapshot-audit.json")


def digest(registry: dict) -> str:
    payload = json.dumps(
        registry,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    raw = json.loads(SRC.read_text())
    attack_replays = 0
    control_replays = 0
    failures: list[str] = []
    for row in raw["attacks"]:
        signed = digest(row["signing_registry"])
        verified = digest(row["verification_registry"])
        scopes = [entry["scope"] for entry in row["attestations"]]
        ok = (
            signed == row["signing_registry_sha256"]
            and verified == row["verification_registry_sha256"]
            and signed != verified
            and all(scope["authority_registry_sha256"] == signed for scope in scopes)
            and row["parent_definitive"]
            and not row["corrected_definitive"]
            and any("different registry snapshot" in reason for reason in row["corrected_reasons"])
        )
        if ok:
            attack_replays += 1
        else:
            failures.append(f"attack:{row['case']}:{row['family']}")
    for row in raw["controls"]:
        signed = digest(row["signing_registry"])
        verified = digest(row["verification_registry"])
        scopes = [entry["scope"] for entry in row["attestations"]]
        ok = (
            signed == verified == row["signing_registry_sha256"] == row["verification_registry_sha256"]
            and all(scope["authority_registry_sha256"] == signed for scope in scopes)
            and row["parent_definitive"]
            and row["corrected_definitive"]
        )
        if ok:
            control_replays += 1
        else:
            failures.append(f"control:{row['case']}")
    imported = sorted(name for name in sys.modules if name == "agnxiv" or name.startswith("agnxiv."))
    report = {
        "schema": "agnxiv.authority-registry-snapshot-audit/1",
        "source_sha256": hashlib.sha256(SRC.read_bytes()).hexdigest(),
        "attack_replays": attack_replays,
        "attack_total": len(raw["attacks"]),
        "control_replays": control_replays,
        "control_total": len(raw["controls"]),
        "agnxiv_imports": imported,
        "failures": failures,
        "passed": attack_replays == 128 and control_replays == 32 and not imported and not failures,
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
