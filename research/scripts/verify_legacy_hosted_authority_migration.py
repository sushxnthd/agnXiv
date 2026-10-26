#!/usr/bin/env python3
"""Replay the preserved real-paper artifact through the current authority gate."""

from __future__ import annotations

import copy
import hashlib
import json
import zipfile
from pathlib import Path

from agnxiv.attestation import canonical_json_sha256
from agnxiv.service.app import _validate_worker_result
from agnxiv.service.db import Job

ARCHIVE = Path("research/evidence/hosted-real-paper/run-40116884857.zip")
OUT = Path("research/results/legacy-hosted-authority-migration.json")
EXPECTED_SHA256 = "fce92fdc1ced72366437cad6830c043520870abbc299a54cb00fdb0e6c3f94cb"


def job(commit: str) -> Job:
    return Job(
        id="00000000-0000-0000-0000-000000000401",
        api_key_hash="frozen-evidence",
        status="running",
        mode="auto_verify",
        repository="ChildMindInstitute/reliability-paper",
        repository_ref=commit,
        arxiv_id="2604.15702v2",
        spec_path=None,
    )


def attempt(bundle: dict, discovery: dict, manuscript_identity: dict) -> dict:
    result = {
        "kind": "verification",
        "zero_manifest": True,
        "manuscript_identity": manuscript_identity,
        "discovery": discovery,
        "bundle": bundle,
    }
    commit = bundle["provenance"]["git"]["commit"]
    try:
        _validate_worker_result(job(commit), "needs_review", result)
    except (TypeError, ValueError) as exc:
        return {"accepted": False, "error": str(exc)}
    return {"accepted": True, "error": None}


def main() -> None:
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == EXPECTED_SHA256
    with zipfile.ZipFile(ARCHIVE) as zipped:
        payload = json.loads(zipped.read("zero-manifest-real.json"))
    root = payload["result"]
    manuscript_identity = root["manuscript_identity"]
    items = [root, *root["additional_verifications"]]
    rows = []
    for index, item in enumerate(items):
        bundle = item["bundle"]
        discovery = item["discovery"]
        other = items[1 - index]["discovery"]

        legacy = copy.deepcopy(bundle)
        missing = attempt(legacy, discovery, manuscript_identity)

        label_only = copy.deepcopy(bundle)
        label_only["verification_authority"] = "auto_planned"
        label_only["authority_evidence_sha256"] = None
        relabelled = attempt(label_only, discovery, manuscript_identity)

        crossed = copy.deepcopy(label_only)
        crossed["authority_evidence_sha256"] = canonical_json_sha256(other)
        cross_locator = attempt(crossed, discovery, manuscript_identity)

        exact = copy.deepcopy(label_only)
        exact["authority_evidence_sha256"] = canonical_json_sha256(discovery)
        control = attempt(exact, discovery, manuscript_identity)

        rows.append(
            {
                "metric": bundle["claim"]["metric"],
                "reported": bundle["record"]["expected"],
                "observed": bundle["record"]["observed_mean"],
                "public_verdict": bundle["record"]["verdict"],
                "provisional_verdict": bundle["provisional_verdict"],
                "locator_sha256": canonical_json_sha256(discovery),
                "missing_authority": missing,
                "label_only_upgrade": relabelled,
                "cross_locator_upgrade": cross_locator,
                "exact_binding_control": control,
            }
        )

    report = {
        "schema": "agnxiv.legacy-hosted-authority-migration/1",
        "archive_sha256": EXPECTED_SHA256,
        "workflow_run": 40116884857,
        "bundle_total": len(rows),
        "legacy_missing_authority_rejected": sum(
            not row["missing_authority"]["accepted"] for row in rows
        ),
        "label_only_upgrades_rejected": sum(
            not row["label_only_upgrade"]["accepted"] for row in rows
        ),
        "cross_locator_upgrades_rejected": sum(
            not row["cross_locator_upgrade"]["accepted"] for row in rows
        ),
        "exact_binding_controls_accepted": sum(
            row["exact_binding_control"]["accepted"] for row in rows
        ),
        "measurements_preserved": sum(
            row["observed"] is not None for row in rows
        ),
        "public_abstentions_preserved": sum(
            row["public_verdict"] == "UNABLE_TO_VERIFY" for row in rows
        ),
        "provisional_comparisons_preserved": sum(
            row["provisional_verdict"] == "CONTRADICTED" for row in rows
        ),
        "rows": rows,
    }
    report["passed"] = all(
        report[key] == len(rows)
        for key in (
            "legacy_missing_authority_rejected",
            "label_only_upgrades_rejected",
            "cross_locator_upgrades_rejected",
            "exact_binding_controls_accepted",
            "measurements_preserved",
            "public_abstentions_preserved",
            "provisional_comparisons_preserved",
        )
    )
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
