#!/usr/bin/env python3
"""Independent stdlib-only audit of callback object-binding evidence."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

SOURCE = Path("research/results/callback-scientific-object-binding.json")
OUT = Path("research/results/callback-scientific-object-binding-audit.json")


def main() -> None:
    before = {name for name in sys.modules if name.startswith("agnxiv")}
    report = json.loads(SOURCE.read_text(encoding="utf-8"))
    attacks = report["attacks"]
    controls = report["controls"]
    family_counts = Counter(row["attack"] for row in attacks)
    canonical = json.dumps(attacks, sort_keys=True, separators=(",", ":"))
    result = {
        "schema": "agnxiv.callback-scientific-object-binding-audit/1",
        "attack_total": len(attacks),
        "attack_families": dict(sorted(family_counts.items())),
        "legacy_false_accepts_replayed": sum(
            row["legacy_accepted"] for row in attacks
        ),
        "corrected_rejections_replayed": sum(
            not row["corrected_accepted"] for row in attacks
        ),
        "controls_replayed": sum(
            row["accepted"] and row["verdict_preserved"] for row in controls
        ),
        "case_digest_reproduced": hashlib.sha256(canonical.encode()).hexdigest()
        == report["case_digest"],
        "production_imports": len(
            {name for name in sys.modules if name.startswith("agnxiv")} - before
        ),
    }
    result["passed"] = (
        set(family_counts.values()) == {128}
        and result["legacy_false_accepts_replayed"] == 640
        and result["corrected_rejections_replayed"] == 640
        and result["controls_replayed"] == 32
        and result["case_digest_reproduced"]
        and result["production_imports"] == 0
    )
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
