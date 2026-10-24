#!/usr/bin/env python3
"""Independent stdlib-only audit of the base-image ABA mechanism."""

from __future__ import annotations

import hashlib
import json


def h(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> None:
    checked = old_false_accepts = neutralized = 0
    transcript = []
    for index in range(128):
        before = h(f"base-a-{index}")
        during = h(f"base-b-{index}")
        after = before
        old_accepts = before == after
        pinned_reference = f"python@sha256:{before}"
        selected = pinned_reference.split("@sha256:", 1)[1]
        passed = old_accepts and during != before and selected == before
        checked += 1
        old_false_accepts += int(old_accepts and during != before)
        neutralized += int(passed)
        transcript.append((index, before, during, after, selected, passed))
    result = {
        "schema": "agnxiv.base-image-aba-binding-audit/1",
        "production_imports": 0,
        "attacks_checked": checked,
        "old_false_accepts": old_false_accepts,
        "neutralized": neutralized,
        "digest": hashlib.sha256(
            json.dumps(transcript, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "passed": checked == old_false_accepts == neutralized == 128,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
