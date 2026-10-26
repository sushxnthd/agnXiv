#!/usr/bin/env python3
"""Adversarial verification of fail-closed authority provenance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agnxiv.build import BuildPlan, BuildResult
from agnxiv.environment import EnvironmentSpec
from agnxiv.models import Claim, Observation, Verdict, VerificationPolicy
from agnxiv.pipeline import ExecutionSummary, VerificationBundle
from agnxiv.provenance import ProvenanceManifest
from agnxiv.verdict_gate import gate_hosted_verdict
from agnxiv.verify import verify_numeric_claim

OUTPUT = Path("research/results/authority-downgrade.json")
IMAGE = "sha256:" + "c" * 64
DECISIVE = {Verdict.VERIFIED, Verdict.PARTIALLY_VERIFIED, Verdict.CONTRADICTED}


def bundle(case: int, authority: str | None) -> VerificationBundle:
    reported = case + 0.25
    observed = reported if case % 3 else reported + 1
    claim = Claim(id=f"AUTH-{case:03d}", text="Reported result.", reported_value=reported)
    record = verify_numeric_claim(
        claim,
        [Observation(value=observed)],
        VerificationPolicy(kind="absolute", tolerance=0.0),
    )
    if case % 3 == 2:
        record.verdict = Verdict.PARTIALLY_VERIFIED
    return VerificationBundle(
        verification_authority=authority,
        claim=claim,
        provenance=ProvenanceManifest(
            files=[], file_count=0, total_bytes=0, tree_digest="a" * 64
        ),
        environment=EnvironmentSpec(
            historical_fidelity="constrained", scope_resolution="resolved"
        ),
        execution=ExecutionSummary(
            command=["python", "verification.py"],
            image_id=IMAGE,
            returncode=0,
            stdout_sha256=hashlib.sha256(str(observed).encode()).hexdigest(),
            stderr_sha256=hashlib.sha256(b"").hexdigest(),
            stdout_excerpt=str(observed),
            stderr_excerpt="",
            pre_execution_tree_sha256="a" * 64,
            post_execution_tree_sha256="a" * 64,
            source_unchanged=True,
            artifacts_unchanged=True,
        ),
        record=record,
    )


def build() -> BuildResult:
    return BuildResult(
        plan=BuildPlan(
            base_image="python@sha256:" + "b" * 64,
            dependency_file="requirements.txt",
            dependency_sha256="d" * 64,
            dependency_precision="hash-pinned",
            dockerfile="FROM python@sha256:" + "b" * 64 + "\n",
            network_required=True,
            safe_manifest_only=True,
        ),
        image_ref="agnxiv-env:authority-downgrade",
        image_id=IMAGE,
        base_image_id="sha256:" + "b" * 64,
        stdout_sha256="e" * 64,
        stderr_sha256="f" * 64,
    )


def main() -> None:
    environment = build()
    cases = []
    for case in range(128):
        labelled = bundle(case, "repository_supplied")
        serialized = labelled.model_dump(mode="json")
        serialized.pop("verification_authority")
        downgraded = VerificationBundle.model_validate(serialized)
        old_verdict = downgraded.record.verdict
        corrected = gate_hosted_verdict(downgraded, environment)
        cases.append({
            "case": case,
            "raw_verdict": old_verdict.value,
            "old_gate_definitive": old_verdict in DECISIVE,
            "corrected_verdict": corrected.record.verdict.value,
            "provisional_verdict": corrected.provisional_verdict.value,
            "evidence_preserved": (
                corrected.record.observed_mean == downgraded.record.observed_mean
            ),
            "missing_authority_blocked": any(
                "authority is missing" in reason
                for reason in corrected.verdict_gate_reasons
            ),
        })

    controls = []
    for case in range(32):
        raw = bundle(1000 + case, "auto_planned")
        corrected = gate_hosted_verdict(raw, environment)
        controls.append({
            "case": case,
            "raw_verdict": raw.record.verdict.value,
            "corrected_verdict": corrected.record.verdict.value,
            "passed": corrected.record.verdict == raw.record.verdict,
        })

    digest = hashlib.sha256(
        json.dumps(cases, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    report = {
        "schema": "agnxiv.authority-downgrade/1",
        "attack_total": len(cases),
        "old_false_definitive_verdicts": sum(
            case["old_gate_definitive"] for case in cases
        ),
        "corrected_false_definitive_verdicts": sum(
            case["corrected_verdict"] in {"VERIFIED", "PARTIALLY_VERIFIED", "CONTRADICTED"}
            for case in cases
        ),
        "provisional_evidence_preserved": sum(
            case["evidence_preserved"] and case["missing_authority_blocked"]
            for case in cases
        ),
        "explicit_auto_planned_controls_passed": sum(
            control["passed"] for control in controls
        ),
        "explicit_auto_planned_control_total": len(controls),
        "case_digest": digest,
        "cases": cases,
        "controls": controls,
    }
    report["passed"] = (
        report["old_false_definitive_verdicts"] == 128
        and report["corrected_false_definitive_verdicts"] == 0
        and report["provisional_evidence_preserved"] == 128
        and report["explicit_auto_planned_controls_passed"] == 32
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: value for key, value in report.items()
                      if key not in {"cases", "controls"}}, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
