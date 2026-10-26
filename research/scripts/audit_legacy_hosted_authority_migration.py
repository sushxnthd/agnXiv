#!/usr/bin/env python3
"""Independent stdlib audit of the legacy authority-migration evidence."""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

ARCHIVE = Path("research/evidence/hosted-real-paper/run-40116884857.zip")
PRIMARY = Path("research/results/legacy-hosted-authority-migration.json")
OUT = Path("research/results/legacy-hosted-authority-migration-audit.json")
EXPECTED_SHA256 = "fce92fdc1ced72366437cad6830c043520870abbc299a54cb00fdb0e6c3f94cb"


def canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    before = {name for name in sys.modules if name.startswith("agnxiv")}
    archive_sha256 = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    assert archive_sha256 == EXPECTED_SHA256
    with zipfile.ZipFile(ARCHIVE) as zipped:
        payload = json.loads(zipped.read("zero-manifest-real.json"))
    primary = json.loads(PRIMARY.read_text(encoding="utf-8"))
    root = payload["result"]
    items = [root, *root["additional_verifications"]]
    rows = primary["rows"]

    checks = []
    for item, row in zip(items, rows):
        bundle = item["bundle"]
        checks.append(
            bundle.get("verification_authority") is None
            and bundle.get("authority_evidence_sha256") is None
            and row["locator_sha256"] == canonical_sha256(item["discovery"])
            and row["metric"] == bundle["claim"]["metric"]
            and row["observed"] == bundle["record"]["observed_mean"]
            and row["public_verdict"] == "UNABLE_TO_VERIFY"
            and row["provisional_verdict"] == "CONTRADICTED"
            and row["missing_authority"]["accepted"] is False
            and row["label_only_upgrade"]["accepted"] is False
            and row["cross_locator_upgrade"]["accepted"] is False
            and row["exact_binding_control"]["accepted"] is True
        )

    audit = {
        "schema": "agnxiv.legacy-hosted-authority-migration-audit/1",
        "archive_sha256_reproduced": archive_sha256 == primary["archive_sha256"],
        "bundles_replayed": sum(checks),
        "bundle_total": len(items),
        "production_imports": len(
            {name for name in sys.modules if name.startswith("agnxiv")} - before
        ),
    }
    audit["passed"] = (
        audit["archive_sha256_reproduced"]
        and audit["bundles_replayed"] == audit["bundle_total"]
        and audit["production_imports"] == 0
    )
    OUT.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2, sort_keys=True))
    if not audit["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
