#!/usr/bin/env python3
"""Adversarial gate for repository-authored self-certifying manifests."""

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

OUTPUT = Path("research/results/self-certifying-manifests.json")
IMAGE = "sha256:" + "c" * 64


def bundle(case: int, *, repository_supplied: bool) -> VerificationBundle:
    reported = case + 0.125
    claim = Claim(id=f"SELF-{case:03d}", text="Reported result.", reported_value=reported)
    policy = VerificationPolicy(kind="absolute", tolerance=0.0)
    result = VerificationBundle(
        claim=claim,
        provenance=ProvenanceManifest(
            files=[], file_count=0, total_bytes=0, tree_digest="a" * 64
        ),
        environment=EnvironmentSpec(
            historical_fidelity="constrained", scope_resolution="resolved"
        ),
        execution=ExecutionSummary(
            command=["python", "self_echo.py"],
            image_id=IMAGE,
            returncode=0,
            stdout_sha256=hashlib.sha256(str(reported).encode()).hexdigest(),
            stderr_sha256=hashlib.sha256(b"").hexdigest(),
            stdout_excerpt=str(reported),
            stderr_excerpt="",
            pre_execution_tree_sha256="a" * 64,
            post_execution_tree_sha256="a" * 64,
            source_unchanged=True,
            artifacts_unchanged=True,
        ),
        record=verify_numeric_claim(
            claim, [Observation(value=reported)], policy
        ),
    )
    if repository_supplied:
        result.verification_authority = "repository_supplied"
    return result


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
        image_ref="agnxiv-env:self-certification",
        image_id=IMAGE,
        base_image_id="sha256:" + "b" * 64,
        stdout_sha256="e" * 64,
        stderr_sha256="f" * 64,
    )


def main() -> None:
    environment = build()
    cases = []
    for case in range(128):
        raw = bundle(case, repository_supplied=True)
        old_verdict = raw.record.verdict.value
        corrected = gate_hosted_verdict(raw, environment)
        cases.append(
            {
                "case": case,
                "old_verdict": old_verdict,
                "corrected_verdict": corrected.record.verdict.value,
                "provisional_verdict": corrected.provisional_verdict.value,
                "evidence_preserved": corrected.record.observed_mean == case + 0.125,
                "authority_blocked": any(
                    "no independent verification authority" in reason
                    for reason in corrected.verdict_gate_reasons
                ),
            }
        )

    controls = []
    for case in range(32):
        corrected = gate_hosted_verdict(
            bundle(1000 + case, repository_supplied=False), environment
        )
        controls.append(corrected.record.verdict.value)

    digest = hashlib.sha256(
        json.dumps(cases, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    report = {
        "schema": "agnxiv.self-certifying-manifests/1",
        "attack_total": len(cases),
        "old_false_definitive_verdicts": sum(
            case["old_verdict"] in {"VERIFIED", "CONTRADICTED"} for case in cases
        ),
        "corrected_false_definitive_verdicts": sum(
            case["corrected_verdict"] in {"VERIFIED", "CONTRADICTED"}
            for case in cases
        ),
        "provisional_evidence_preserved": sum(
            case["evidence_preserved"] and case["authority_blocked"]
            for case in cases
        ),
        "independent_authority_controls_decisive": sum(
            verdict == Verdict.VERIFIED.value for verdict in controls
        ),
        "independent_authority_control_total": len(controls),
        "case_digest": digest,
        "cases": cases,
    }
    report["passed"] = (
        report["old_false_definitive_verdicts"] == 128
        and report["corrected_false_definitive_verdicts"] == 0
        and report["provisional_evidence_preserved"] == 128
        and report["independent_authority_controls_decisive"] == 32
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "cases"}, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
