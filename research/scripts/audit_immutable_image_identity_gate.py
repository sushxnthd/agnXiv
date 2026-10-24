"""Independent standard-library audit of image identity gate evidence."""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIMARY = ROOT / "research" / "results" / "immutable-image-identity-gate.json"
OUT = ROOT / "research" / "results" / "immutable-image-identity-gate-audit.json"
CANONICAL = re.compile(r"^sha256:[0-9a-f]{64}$")


def main():
    primary = json.loads(PRIMARY.read_text())
    attacks = primary["attacks"]
    independently_invalid = all(
        CANONICAL.fullmatch(item["candidate"]) is None for item in attacks
    )
    verdicts_fail_closed = all(
        item["public_verdict"] == "UNABLE_TO_VERIFY"
        and item["provisional_verdict"] == "CONTRADICTED"
        and item["passed"] is True
        for item in attacks
    )
    canonical = json.dumps(attacks, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    report = {
        "schema": "immutable-image-identity-gate-independent-audit-v1",
        "production_imports": False,
        "attack_cases": len(attacks),
        "independently_invalid": independently_invalid,
        "verdicts_fail_closed": verdicts_fail_closed,
        "digest_matches": digest == primary["digest"],
        "canonical_control_passed": primary["canonical_control_passed"] is True,
    }
    report["passed"] = all(
        value for key, value in report.items()
        if key not in {"schema", "attack_cases", "production_imports"}
    ) and report["production_imports"] is False
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
