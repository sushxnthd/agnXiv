"""Independent stdlib-only audit of build-to-execution image binding."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIMARY = ROOT / "research" / "results" / "execution-image-binding-gate.json"
OUT = ROOT / "research" / "results" / "execution-image-binding-gate-audit.json"


def canonical_image(value: str) -> bool:
    if not value.startswith("sha256:") or len(value) != 71:
        return False
    return all(character in "0123456789abcdef" for character in value[7:])


def main() -> None:
    primary = json.loads(PRIMARY.read_text(encoding="utf-8"))
    audited = []
    for item in primary["attacks"]:
        built = item["built_image_id"]
        executed = item["execution_image_id"]
        should_abstain = (
            canonical_image(built)
            and canonical_image(executed)
            and built != executed
        )
        audited.append({
            "position": item["position"],
            "should_abstain": should_abstain,
            "production_abstained": item["public_verdict"] == "UNABLE_TO_VERIFY",
        })
    matched = sum(
        item["should_abstain"] and item["production_abstained"]
        for item in audited
    )
    canonical = json.dumps(audited, sort_keys=True, separators=(",", ":"))
    report = {
        "schema": "execution-image-binding-gate-independent-audit-v1",
        "cases": len(audited),
        "matched": matched,
        "production_imports": 0,
        "audit_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "passed": matched == len(audited) == 128,
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
