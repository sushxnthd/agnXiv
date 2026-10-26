#!/usr/bin/env python3
"""Freeze and replay cross-locator authority substitution attacks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agnxiv.attestation import canonical_json_sha256
from agnxiv.service.app import _validate_worker_result
from agnxiv.service.db import Job

OUTPUT = Path("research/results/authority-evidence-binding.json")


def locator(case: int, variant: str) -> dict:
    return {
        "claim_id": f"CLAIM-{case:03d}-{variant}",
        "metric": "accuracy" if case % 2 == 0 else "f1",
        "regex": rf"^{variant}:{case}:(?P<value>[0-9.]+)$",
        "scale": 1.0,
        "label": f"{variant} metric {case}",
        "discovery_stdout_sha256": hashlib.sha256(
            f"discovery:{case}:{variant}".encode()
        ).hexdigest(),
    }


def bundle(case: int, commit: str, frozen_locator: dict) -> dict:
    value = 0.5 + (case % 40) / 100
    claim = {
        "id": f"CLAIM-{case:03d}-A",
        "text": f"Accuracy is {value}",
        "reported_value": value,
    }
    return {
        "verification_authority": "auto_planned",
        "authority_evidence_sha256": canonical_json_sha256(frozen_locator),
        "claim": claim,
        "provenance": {
            "tree_digest": "a" * 64,
            "git": {"commit": commit, "dirty": False},
            "files": [],
            "file_count": 0,
            "total_bytes": 0,
        },
        "environment": {},
        "record": {
            "claim": claim,
            "policy": {"kind": "absolute", "tolerance": 0.01},
            "observations": [{"value": value}],
            "verdict": "VERIFIED",
            "expected": value,
            "observed_mean": value,
            "absolute_error": 0.0,
            "relative_error": 0.0,
            "rationale": "matched",
        },
    }


def job(commit: str) -> Job:
    return Job(
        id="00000000-0000-0000-0000-000000000099",
        api_key_hash="hash",
        status="running",
        mode="auto_verify",
        repository="owner/repo",
        repository_ref=commit,
        arxiv_id="2601.00001",
        spec_path=None,
    )


def old_boundary_accepts(result: dict, commit: str) -> bool:
    """Exact relevant pre-fix checks, retained only as the frozen baseline."""
    candidate = result["bundle"]
    return (
        result.get("kind") == "verification"
        and result.get("zero_manifest") is True
        and isinstance(result.get("discovery"), dict)
        and candidate.get("verification_authority") == "auto_planned"
        and candidate.get("provenance", {}).get("git", {}).get("commit") == commit
        and candidate.get("provenance", {}).get("git", {}).get("dirty") is False
    )


def corrected_accepts(result: dict, commit: str) -> bool:
    try:
        _validate_worker_result(job(commit), "succeeded", result)
    except ValueError:
        return False
    return True


def main() -> None:
    commit = "c" * 40
    attacks = []
    for case in range(128):
        source = locator(case, "A")
        substituted = locator(case, "B")
        result = {
            "kind": "verification",
            "zero_manifest": True,
            "discovery": substituted,
            "bundle": bundle(case, commit, source),
        }
        attacks.append(
            {
                "case": case,
                "source_digest": canonical_json_sha256(source),
                "substituted_digest": canonical_json_sha256(substituted),
                "old_boundary_accepted": old_boundary_accepts(result, commit),
                "corrected_boundary_accepted": corrected_accepts(result, commit),
            }
        )

    controls = []
    for case in range(32):
        frozen = locator(1000 + case, "CONTROL")
        result = {
            "kind": "verification",
            "zero_manifest": True,
            "discovery": frozen,
            "bundle": bundle(1000 + case, commit, frozen),
        }
        controls.append(
            {
                "case": case,
                "accepted": corrected_accepts(result, commit),
            }
        )

    cases_digest = hashlib.sha256(
        json.dumps(attacks, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    report = {
        "schema": "agnxiv.authority-evidence-binding/1",
        "attack_total": len(attacks),
        "old_false_accepts": sum(x["old_boundary_accepted"] for x in attacks),
        "corrected_false_accepts": sum(x["corrected_boundary_accepted"] for x in attacks),
        "matching_controls_passed": sum(x["accepted"] for x in controls),
        "matching_control_total": len(controls),
        "case_digest": cases_digest,
        "attacks": attacks,
        "controls": controls,
    }
    report["passed"] = (
        report["old_false_accepts"] == 128
        and report["corrected_false_accepts"] == 0
        and report["matching_controls_passed"] == 32
    )
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps({k: v for k, v in report.items() if k not in {"attacks", "controls"}}, indent=2)
    )
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
