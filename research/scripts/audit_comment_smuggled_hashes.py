#!/usr/bin/env python3
"""Independent stdlib-only audit of effective requirement hash tokens."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

OUT = Path("research/results/comment-smuggled-hashes-audit.json")
HASH_RE = re.compile(r"--hash=sha256:[0-9a-fA-F]{64}(?:\s|$)")


def effective(line: str) -> str:
    return re.split(r"\s+#", line.strip(), maxsplit=1)[0].rstrip()


def main():
    transcript = []
    attacks = controls = 0
    for index in range(128):
        digest = hashlib.sha256(f"audit-attack-{index}".encode()).hexdigest()
        raw = f"package-{index}==1.0 # --hash=sha256:{digest} trailing"
        passed = HASH_RE.search(raw) is not None and HASH_RE.search(effective(raw)) is None
        attacks += int(passed)
        transcript.append(("attack", index, passed))
    for index in range(32):
        digest = hashlib.sha256(f"audit-control-{index}".encode()).hexdigest()
        raw = f"package-{index}==1.0 --hash=sha256:{digest} # provenance"
        passed = HASH_RE.search(effective(raw)) is not None
        controls += int(passed)
        transcript.append(("control", index, passed))
    result = {
        "schema": "agnxiv.comment-smuggled-hash-audit/1",
        "production_imports": 0,
        "attacks_rejected": attacks,
        "attack_total": 128,
        "controls_preserved": controls,
        "control_total": 32,
        "digest": hashlib.sha256(json.dumps(transcript).encode()).hexdigest(),
        "passed": attacks == 128 and controls == 32,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
