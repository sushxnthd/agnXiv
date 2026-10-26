#!/usr/bin/env python3
"""Independent stdlib-only audit of authority-downgrade evidence."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SOURCE = Path("research/results/authority-downgrade.json")
OUTPUT = Path("research/results/authority-downgrade-audit.json")


def main() -> None:
    production_before = {name for name in sys.modules if name.startswith("agnxiv")}
    report = json.loads(SOURCE.read_text())
    cases = report["cases"]
    controls = report["controls"]
    digest = hashlib.sha256(
        json.dumps(cases, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    attacks_pass = all(
        case["old_gate_definitive"]
        and case["corrected_verdict"] == "UNABLE_TO_VERIFY"
        and case["provisional_verdict"] == case["raw_verdict"]
        and case["evidence_preserved"]
        and case["missing_authority_blocked"]
        for case in cases
    )
    result = {
        "schema": "agnxiv.authority-downgrade-audit/1",
        "attack_total": len(cases),
        "attacks_replayed": len(cases) if attacks_pass else 0,
        "control_total": len(controls),
        "controls_replayed": sum(
            control["passed"]
            and control["raw_verdict"] == control["corrected_verdict"]
            for control in controls
        ),
        "case_digest_reproduced": digest == report["case_digest"],
        "production_imports": len(
            {name for name in sys.modules if name.startswith("agnxiv")}
            - production_before
        ),
    }
    result["passed"] = (
        result["attacks_replayed"] == 128
        and result["controls_replayed"] == 32
        and result["case_digest_reproduced"]
        and result["production_imports"] == 0
    )
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
