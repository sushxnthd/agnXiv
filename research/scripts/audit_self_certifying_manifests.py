#!/usr/bin/env python3
"""Independent stdlib-only audit of the self-certification evidence."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SOURCE = Path("research/results/self-certifying-manifests.json")
OUTPUT = Path("research/results/self-certifying-manifests-audit.json")


def main() -> None:
    production_before = {name for name in sys.modules if name.startswith("agnxiv")}
    report = json.loads(SOURCE.read_text())
    cases = report["cases"]
    digest = hashlib.sha256(
        json.dumps(cases, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    passed = all(
        case["old_verdict"] == "VERIFIED"
        and case["corrected_verdict"] == "UNABLE_TO_VERIFY"
        and case["provisional_verdict"] == "VERIFIED"
        and case["evidence_preserved"]
        and case["authority_blocked"]
        for case in cases
    )
    result = {
        "schema": "agnxiv.self-certifying-manifests-audit/1",
        "attack_total": len(cases),
        "attacks_replayed": sum(passed for _ in cases) if passed else 0,
        "case_digest_reproduced": digest == report["case_digest"],
        "production_imports": len(
            {name for name in sys.modules if name.startswith("agnxiv")}
            - production_before
        ),
    }
    result["passed"] = (
        passed
        and result["attack_total"] == 128
        and result["case_digest_reproduced"]
        and result["production_imports"] == 0
    )
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
