#!/usr/bin/env python3
"""Independent stdlib-only audit of authority-evidence binding results."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SOURCE = Path("research/results/authority-evidence-binding.json")
OUTPUT = Path("research/results/authority-evidence-binding-audit.json")


def main() -> None:
    production_before = {name for name in sys.modules if name.startswith("agnxiv")}
    report = json.loads(SOURCE.read_text())
    attacks = report["attacks"]
    controls = report["controls"]
    digest = hashlib.sha256(
        json.dumps(attacks, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    result = {
        "schema": "agnxiv.authority-evidence-binding-audit/1",
        "attack_total": len(attacks),
        "attacks_replayed": sum(
            item["old_boundary_accepted"]
            and not item["corrected_boundary_accepted"]
            and item["source_digest"] != item["substituted_digest"]
            for item in attacks
        ),
        "control_total": len(controls),
        "controls_replayed": sum(item["accepted"] for item in controls),
        "case_digest_reproduced": digest == report["case_digest"],
        "production_imports": len(
            {name for name in sys.modules if name.startswith("agnxiv")} - production_before
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
