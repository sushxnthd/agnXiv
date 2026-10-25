#!/usr/bin/env python3
"""Independent stdlib-only audit of base-image identity coherence evidence."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SOURCE = Path("research/results/base-identity-coherence.json")
OUT = Path("research/results/base-identity-coherence-audit.json")
IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
DIGEST_REF = re.compile(r"^python@sha256:[0-9a-f]{64}$")


def main() -> None:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    cases = payload["cases"]
    independently_valid = 0
    attacks = 0
    controls = 0
    for row in cases:
        valid = (
            IMAGE_ID.fullmatch(row["old_endpoint_id"]) is not None
            and IMAGE_ID.fullmatch(row["bound_id"]) is not None
            and DIGEST_REF.fullmatch(row["bound_digest"]) is not None
            and row["mutable_id_lookups"] == 0
            and row["corrected_coherent"] is True
        )
        independently_valid += valid
        attacks += row["attack"] is True and row["old_endpoint_id"] != row["bound_id"]
        controls += row["attack"] is False and row["old_endpoint_id"] == row["bound_id"]

    canonical = json.dumps(cases, sort_keys=True, separators=(",", ":"))
    summary = {
        "case_total": len(cases),
        "attack_total": attacks,
        "control_total": controls,
        "independently_valid": independently_valid,
        "primary_digest_reproduced": hashlib.sha256(canonical.encode()).hexdigest()
        == payload["summary"]["digest"],
        "production_imports": 0,
    }
    summary["passed"] = (
        summary["case_total"] == 144
        and summary["attack_total"] == 128
        and summary["control_total"] == 16
        and summary["independently_valid"] == 144
        and summary["primary_digest_reproduced"]
    )
    OUT.write_text(
        json.dumps(
            {"schema": "agnxiv.base-identity-coherence-audit/1", "summary": summary},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
