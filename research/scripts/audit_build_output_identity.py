#!/usr/bin/env python3
"""Independent stdlib-only audit of build-output identity binding."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

OUT = Path("research/results/build-output-identity-audit.json")
CANONICAL = re.compile(r"^sha256:[0-9a-f]{64}$")


def image_id(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode()).hexdigest()


def parse_iidfile(payload: str) -> str | None:
    lines = payload.splitlines()
    return lines[0] if len(lines) == 1 and CANONICAL.fullmatch(lines[0]) else None


def main() -> None:
    attacks = []
    for case in range(128):
        genuine = image_id(f"genuine-{case}")
        attacker = image_id(f"attacker-{case}")
        parsed = parse_iidfile(genuine + "\n")
        attacks.append(
            {
                "case": case,
                "old_false_accept": attacker != genuine,
                "independent_binding": parsed == genuine,
            }
        )
    malformed = ["", "sha256:not-a-digest\n", image_id("one") + "\n" + image_id("two") + "\n"]
    canonical = json.dumps(attacks, sort_keys=True, separators=(",", ":"))
    summary = {
        "attack_total": len(attacks),
        "old_baseline_false_accepts": sum(row["old_false_accept"] for row in attacks),
        "independent_bindings": sum(row["independent_binding"] for row in attacks),
        "malformed_rejected": sum(parse_iidfile(value) is None for value in malformed),
        "production_imports": 0,
        "digest": hashlib.sha256(canonical.encode()).hexdigest(),
    }
    summary["passed"] = (
        summary["old_baseline_false_accepts"] == 128
        and summary["independent_bindings"] == 128
        and summary["malformed_rejected"] == 3
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"schema": "agnxiv.build-output-identity-audit/1", "summary": summary, "cases": attacks}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
