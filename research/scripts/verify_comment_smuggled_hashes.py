#!/usr/bin/env python3
"""Adversarial verification of comment-smuggled requirement hashes."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from pathlib import Path

from agnxiv.build import classify_dependency_precision, plan_python_environment

OUT = Path("research/results/comment-smuggled-hashes.json")
HASH_RE = re.compile(r"--hash=sha256:[0-9a-fA-F]{64}(?:\s|$)")


def old_classifier(payload: str) -> str:
    lines = [line.strip() for line in payload.splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    packages = [line for line in lines if not line.startswith("-")]
    exact = all(re.match(r"^[A-Za-z0-9_.-]+==[^\s;\\]+", line)
                for line in packages)
    return "hash-pinned" if exact and all(HASH_RE.search(line) for line in packages) \
        else "version-pinned"


def classify(payload: str):
    with tempfile.TemporaryDirectory(prefix="agnxiv-comment-hash-") as temp:
        root = Path(temp)
        (root / "requirements.txt").write_text(payload, encoding="utf-8")
        return classify_dependency_precision(root / "requirements.txt"), \
            plan_python_environment(root).dockerfile


def main():
    attacks = []
    separators = (" # ", "\t# ", "  #", " \t# ")
    suffixes = ("", " ignored", " \\", " trailing-audit-text")
    for index in range(128):
        digest = hashlib.sha256(f"attack-{index}".encode()).hexdigest()
        separator = separators[index % len(separators)]
        suffix = suffixes[(index // len(separators)) % len(suffixes)]
        token = "--hash=sha256:" + (digest.upper() if index % 2 else digest)
        payload = f"package-{index}==1.0{separator}{token}{suffix}\n"
        if index % 3 == 0:
            payload += f"control-{index}==2.0{separator}{token}\n"
        before = old_classifier(payload)
        after, dockerfile = classify(payload)
        attacks.append({
            "case": index,
            "old_precision": before,
            "new_precision": after,
            "runtime_hash_mode": "--require-hashes" in dockerfile,
            "passed": before == "hash-pinned"
            and after != "hash-pinned"
            and "--require-hashes" not in dockerfile,
        })

    controls = []
    for index in range(32):
        digest = hashlib.sha256(f"control-{index}".encode()).hexdigest()
        if index % 2:
            payload = (
                f"package-{index}==1.0 \\\n"
                f"  --hash=sha256:{digest} # recorded artifact\n"
            )
        else:
            payload = f"package-{index}==1.0 --hash=sha256:{digest}\n"
        precision, dockerfile = classify(payload)
        controls.append({
            "case": index,
            "precision": precision,
            "runtime_hash_mode": "--require-hashes" in dockerfile,
            "passed": precision == "hash-pinned" and "--require-hashes" in dockerfile,
        })

    transcript = attacks + controls
    canonical = json.dumps(transcript, sort_keys=True, separators=(",", ":"))
    summary = {
        "old_false_accepts": sum(row["old_precision"] == "hash-pinned"
                                 for row in attacks),
        "attack_total": len(attacks),
        "attacks_rejected": sum(row["passed"] for row in attacks),
        "controls_preserved": sum(row["passed"] for row in controls),
        "control_total": len(controls),
        "false_definitive_evidence": sum(not row["passed"] for row in attacks),
        "digest": hashlib.sha256(canonical.encode()).hexdigest(),
        "passed": all(row["passed"] for row in transcript),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"schema": "agnxiv.comment-smuggled-hash/1",
                               "summary": summary, "cases": transcript},
                              indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
