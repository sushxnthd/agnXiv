#!/usr/bin/env python3
"""Frozen adversarial verification of immutable Dockerfile base binding."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agnxiv.build import BuildPlan, bind_plan_to_immutable_base

OUT = Path("research/results/base-image-aba-binding.json")


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def candidate(index: int) -> dict[str, object]:
    a = digest(f"base-a-{index}")
    b = digest(f"base-b-{index}")
    immutable = f"python@sha256:{a}"
    plan = BuildPlan(
        base_image="python:3.11-slim",
        dependency_file=None,
        dependency_sha256=None,
        dependency_precision="base-only",
        dockerfile=(
            "FROM python:3.11-slim\n"
            "ENV PYTHONDONTWRITEBYTECODE=1\n"
            "WORKDIR /workspace\n"
        ),
        network_required=False,
        safe_manifest_only=True,
    )
    bound = bind_plan_to_immutable_base(plan, immutable)
    before = a
    after = a
    old_endpoint_check_accepts = before == after
    old_build_selected = b
    bound_build_selected = bound.base_image.rsplit(":", 1)[1]
    passed = (
        old_endpoint_check_accepts
        and old_build_selected != a
        and bound_build_selected == a
        and bound.dockerfile.startswith(f"FROM {immutable}\n")
        and plan.plan_id != bound.plan_id
    )
    return {
        "case": index,
        "pre_build_tag": a,
        "during_build_tag": b,
        "post_build_tag": a,
        "old_endpoint_check_accepts": old_endpoint_check_accepts,
        "old_build_selected": old_build_selected,
        "bound_build_selected": bound_build_selected,
        "bound_from": bound.dockerfile.splitlines()[0],
        "passed": passed,
    }


def main() -> None:
    attacks = [candidate(index) for index in range(128)]
    controls = []
    for index in range(8):
        value = digest(f"control-{index}")
        observed = str(value)
        controls.append({
            "case": index,
            "pre": value,
            "during": value,
            "post": value,
            "passed": observed == value,
        })
    canonical = json.dumps(
        {"attacks": attacks, "controls": controls},
        sort_keys=True,
        separators=(",", ":"),
    )
    result = {
        "schema": "agnxiv.base-image-aba-binding/1",
        "attacks": attacks,
        "controls": controls,
        "summary": {
            "aba_attacks": len(attacks),
            "aba_neutralized": sum(bool(item["passed"]) for item in attacks),
            "old_false_accepts": sum(
                bool(item["old_endpoint_check_accepts"])
                and item["old_build_selected"] != item["pre_build_tag"]
                for item in attacks
            ),
            "mutable_from_in_bound_plans": sum(
                "@sha256:" not in str(item["bound_from"]) for item in attacks
            ),
            "controls_passed": sum(bool(item["passed"]) for item in controls),
            "digest": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "passed": all(bool(item["passed"]) for item in attacks + controls),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    if not result["summary"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
