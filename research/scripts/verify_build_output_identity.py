#!/usr/bin/env python3
"""Adversarial matrix for build-output identity versus mutable tag lookup."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from agnxiv.build import EnvironmentBuildError, read_build_output_image_id

OUT = Path("research/results/build-output-identity.json")


def image_id(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode()).hexdigest()


def main() -> None:
    attacks = []
    with tempfile.TemporaryDirectory(prefix="agnxiv-iid-evidence-") as temp:
        root = Path(temp)
        for case in range(128):
            genuine = image_id(f"genuine-{case}")
            substituted_tag = image_id(f"attacker-{case}")
            iidfile = root / str(case)
            iidfile.write_text(genuine + "\n", encoding="utf-8")
            bound = read_build_output_image_id(iidfile)
            attacks.append(
                {
                    "case": case,
                    "old_tag_lookup": substituted_tag,
                    "build_output_id": bound,
                    "old_false_accept": substituted_tag != genuine,
                    "correctly_bound": bound == genuine,
                }
            )

        controls = []
        for case in range(16):
            genuine = image_id(f"control-{case}")
            iidfile = root / f"control-{case}"
            iidfile.write_text(genuine + "\n", encoding="utf-8")
            controls.append(read_build_output_image_id(iidfile) == genuine)

        malformed = {
            "missing": None,
            "empty": "",
            "short": "sha256:not-a-digest\n",
            "multiple": image_id("one") + "\n" + image_id("two") + "\n",
        }
        rejected = {}
        for name, payload in malformed.items():
            iidfile = root / f"malformed-{name}"
            if payload is not None:
                iidfile.write_text(payload, encoding="utf-8")
            try:
                read_build_output_image_id(iidfile)
            except EnvironmentBuildError:
                rejected[name] = True
            else:
                rejected[name] = False

    canonical = json.dumps(attacks, sort_keys=True, separators=(",", ":"))
    summary = {
        "attack_total": len(attacks),
        "old_baseline_false_accepts": sum(row["old_false_accept"] for row in attacks),
        "iidfile_attacks_bound": sum(row["correctly_bound"] for row in attacks),
        "control_total": len(controls),
        "controls_preserved": sum(controls),
        "malformed_total": len(rejected),
        "malformed_rejected": sum(rejected.values()),
        "digest": hashlib.sha256(canonical.encode()).hexdigest(),
    }
    summary["passed"] = summary == {
        **summary,
        "old_baseline_false_accepts": 128,
        "iidfile_attacks_bound": 128,
        "controls_preserved": 16,
        "malformed_rejected": 4,
    }
    payload = {"schema": "agnxiv.build-output-identity/1", "summary": summary, "cases": attacks}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
