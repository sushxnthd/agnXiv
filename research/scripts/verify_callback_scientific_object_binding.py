#!/usr/bin/env python3
"""Replay cross-manuscript and cross-claim callback substitutions."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from agnxiv.attestation import canonical_json_sha256
from agnxiv.service.app import _validate_worker_result
from agnxiv.service.db import Job

OUT = Path("research/results/callback-scientific-object-binding.json")
ATTACKS = (
    "cross_arxiv_identity",
    "cross_manuscript_digest",
    "cross_additional_manuscript",
    "cross_claim_locator",
    "cross_metric_locator",
)


def digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def locator(case: int, claim_id: str, metric: str = "accuracy") -> dict:
    return {
        "claim_id": claim_id,
        "metric": metric,
        "regex": rf"^accuracy-{case}=(?P<value>[0-9.]+)$",
        "scale": 1.0,
        "label": f"accuracy {case}",
        "discovery_stdout_sha256": digest(f"stdout:{case}"),
    }


def bundle(case: int, commit: str, frozen: dict, manuscript_sha256: str) -> dict:
    value = 0.5 + (case % 40) / 100
    claim = {
        "id": f"CLAIM-{case:03d}",
        "text": f"Accuracy is {value}",
        "metric": "accuracy",
        "reported_value": value,
    }
    return {
        "verification_authority": "auto_planned",
        "authority_evidence_sha256": canonical_json_sha256(frozen),
        "claim": claim,
        "manuscript": {
            "name": "paper.pdf",
            "sha256": manuscript_sha256,
            "size_bytes": 4096 + case,
        },
        "provenance": {
            "tree_digest": digest(f"tree:{case}"),
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
        id="00000000-0000-0000-0000-000000000777",
        api_key_hash="frozen-object-binding",
        status="running",
        mode="auto_verify",
        repository="owner/repository",
        repository_ref=commit,
        arxiv_id="2601.00001v1",
        spec_path=None,
    )


def valid_result(case: int, commit: str) -> dict:
    claim_id = f"CLAIM-{case:03d}"
    frozen = locator(case, claim_id)
    manuscript_sha256 = digest(f"paper:{case}")
    return {
        "kind": "verification",
        "zero_manifest": True,
        "manuscript_identity": {
            "arxiv_id": "2601.00001v1",
            "sha256": manuscript_sha256,
            "expected_sha256": None,
            "identity_verified": False,
        },
        "discovery": frozen,
        "bundle": bundle(case, commit, frozen, manuscript_sha256),
    }


def mutate(result: dict, attack: str, case: int, commit: str) -> None:
    if attack == "cross_arxiv_identity":
        result["manuscript_identity"]["arxiv_id"] = "2601.99999v2"
    elif attack == "cross_manuscript_digest":
        result["bundle"]["manuscript"]["sha256"] = digest(f"other-paper:{case}")
    elif attack == "cross_additional_manuscript":
        claim_id = f"CLAIM-{case:03d}"
        second = locator(case, claim_id)
        second["regex"] = rf"^secondary-{case}=(?P<value>[0-9.]+)$"
        result["additional_verifications"] = [{
            "discovery": second,
            "bundle": bundle(case, commit, second, digest(f"other-paper:{case}")),
        }]
    elif attack == "cross_claim_locator":
        result["discovery"]["claim_id"] = f"OTHER-{case:03d}"
        result["bundle"]["authority_evidence_sha256"] = canonical_json_sha256(
            result["discovery"]
        )
    elif attack == "cross_metric_locator":
        result["discovery"]["metric"] = "f1"
        result["bundle"]["authority_evidence_sha256"] = canonical_json_sha256(
            result["discovery"]
        )
    else:
        raise AssertionError(attack)


def legacy_accepts(result: dict, commit: str) -> bool:
    """Reproduce the relevant pre-fix callback checks."""
    pairs = [(result["discovery"], result["bundle"])] + [
        (item["discovery"], item["bundle"])
        for item in result.get("additional_verifications", [])
    ]
    if result.get("kind") != "verification" or result.get("zero_manifest") is not True:
        return False
    for frozen, candidate in pairs:
        if candidate.get("verification_authority") != "auto_planned":
            return False
        if candidate.get("authority_evidence_sha256") != canonical_json_sha256(frozen):
            return False
        git = candidate.get("provenance", {}).get("git", {})
        if git.get("commit") != commit or git.get("dirty") is not False:
            return False
    return True


def corrected_accepts(result: dict, commit: str) -> bool:
    try:
        _validate_worker_result(job(commit), "succeeded", result)
    except (TypeError, ValueError):
        return False
    return True


def main() -> None:
    commit = "e" * 40
    rows = []
    for case in range(128):
        for attack in ATTACKS:
            candidate = copy.deepcopy(valid_result(case, commit))
            mutate(candidate, attack, case, commit)
            rows.append({
                "case": case,
                "attack": attack,
                "legacy_accepted": legacy_accepts(candidate, commit),
                "corrected_accepted": corrected_accepts(candidate, commit),
            })

    controls = []
    for case in range(32):
        candidate = valid_result(1000 + case, commit)
        controls.append({
            "case": case,
            "accepted": corrected_accepts(candidate, commit),
            "verdict_preserved": candidate["bundle"]["record"]["verdict"] == "VERIFIED",
        })

    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    report = {
        "schema": "agnxiv.callback-scientific-object-binding/1",
        "attack_families": list(ATTACKS),
        "attack_total": len(rows),
        "legacy_false_accepts": sum(row["legacy_accepted"] for row in rows),
        "corrected_false_accepts": sum(row["corrected_accepted"] for row in rows),
        "control_total": len(controls),
        "controls_accepted": sum(row["accepted"] for row in controls),
        "control_verdicts_preserved": sum(
            row["verdict_preserved"] for row in controls
        ),
        "case_digest": hashlib.sha256(canonical.encode()).hexdigest(),
        "attacks": rows,
        "controls": controls,
    }
    report["passed"] = (
        report["legacy_false_accepts"] == 640
        and report["corrected_false_accepts"] == 0
        and report["controls_accepted"] == 32
        and report["control_verdicts_preserved"] == 32
    )
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"attacks", "controls"}}, indent=2, sort_keys=True))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
