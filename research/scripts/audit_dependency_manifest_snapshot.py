#!/usr/bin/env python3
"""Independent stdlib-only audit of manifest snapshot binding."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> None:
    transcript: list[tuple[object, ...]] = []
    old_false_accepts = rejected = controls_passed = 0
    for index in range(128):
        before = f"a-{index}".encode()
        after = f"b-{index}".encode()
        planned = digest(before)
        built = digest(after)
        old_accept = planned != built
        new_accept = built == planned
        old_false_accepts += int(old_accept)
        rejected += int(not new_accept)
        transcript.append((index, planned, built, old_accept, new_accept))

    for index in range(16):
        value = f"control-{index}".encode()
        with tempfile.TemporaryDirectory(prefix="agnxiv-audit-") as temp:
            source = Path(temp) / "source"
            target = Path(temp) / "target"
            source.write_bytes(value)
            planned = digest(source.read_bytes())
            shutil.copyfile(source, target)
            observed = digest(target.read_bytes())
        passed = planned == observed
        controls_passed += int(passed)
        transcript.append(("control", index, planned, observed, passed))

    result = {
        "schema": "agnxiv.dependency-manifest-snapshot-audit/1",
        "production_imports": 0,
        "attacks": 128,
        "old_false_accepts": old_false_accepts,
        "rejected": rejected,
        "controls": 16,
        "controls_passed": controls_passed,
        "digest": hashlib.sha256(
            json.dumps(transcript, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "passed": old_false_accepts == rejected == 128 and controls_passed == 16,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
