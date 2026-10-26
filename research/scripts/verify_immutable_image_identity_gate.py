#!/usr/bin/env python3
"""Frozen adversarial verifier for canonical container image identities."""

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

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research" / "results" / "immutable-image-identity-gate.json"
CANONICAL = "sha256:" + "a" * 64


def bundle(execution_image_id):
    claim = Claim(
        id="C1",
        text="Accuracy is 0.9",
        metric="accuracy",
        reported_value=0.9,
    )
    policy = VerificationPolicy(kind="absolute", tolerance=0.01)
    return VerificationBundle(
        verification_authority="auto_planned",
        authority_evidence_sha256="f" * 64,
        claim=claim,
        provenance=ProvenanceManifest(
            files=[], file_count=0, total_bytes=0, tree_digest="b" * 64
        ),
        environment=EnvironmentSpec(
            historical_fidelity="constrained",
            scope_resolution="resolved",
        ),
        execution=ExecutionSummary(
            command=["docker", "run"],
            image_id=execution_image_id,
            returncode=0,
            stdout_sha256="1" * 64,
            stderr_sha256="2" * 64,
            stdout_excerpt="",
            stderr_excerpt="",
            pre_execution_tree_sha256="b" * 64,
            post_execution_tree_sha256="b" * 64,
            source_unchanged=True,
            artifacts_unchanged=True,
        ),
        record=verify_numeric_claim(
            claim,
            [Observation(value=0.8)],
            policy,
        ),
    )


def build(*, base_image_id, image_id):
    return BuildResult(
        plan=BuildPlan(
            base_image="python:3.11-slim",
            dependency_file="requirements.txt",
            dependency_sha256="c" * 64,
            dependency_precision="hash-pinned",
            dockerfile="FROM python:3.11-slim\n",
            network_required=True,
            safe_manifest_only=True,
        ),
        image_ref="agnxiv-env:frozen",
        image_id=image_id,
        base_image_id=base_image_id,
        stdout_sha256="d" * 64,
        stderr_sha256="e" * 64,
    )


def malformed_ids():
    values = ["sha256:" + "a" * length for length in range(64)]
    values.extend("sha256:" + "a" * length for length in range(65, 97))
    values.extend([
        "",
        "sha256",
        "sha256:",
        "sha256:built",
        "sha256:" + "A" * 64,
        "sha256:" + "g" * 64,
        "sha512:" + "a" * 64,
        " sha256:" + "a" * 64,
        "sha256:" + "a" * 64 + " ",
        "sha256:" + "a" * 64 + "suffix",
    ])
    return tuple(dict.fromkeys(values))


def main():
    attacks = []
    for malformed in malformed_ids():
        for target in ("base", "built"):
            kwargs = {
                "base_image_id": malformed if target == "base" else CANONICAL,
                "image_id": malformed if target == "built" else CANONICAL,
            }
            gated = gate_hosted_verdict(
                bundle(kwargs["image_id"]), build(**kwargs)
            )
            passed = (
                gated.record.verdict == Verdict.UNABLE_TO_VERIFY
                and gated.provisional_verdict == Verdict.CONTRADICTED
                and gated.record.expected == 0.9
                and gated.record.observed_mean == 0.8
                and any("canonical immutable SHA-256" in reason
                        for reason in gated.verdict_gate_reasons)
            )
            attacks.append({
                "target": target,
                "candidate": malformed,
                "public_verdict": gated.record.verdict.value,
                "provisional_verdict": gated.provisional_verdict.value,
                "passed": passed,
            })

    control = gate_hosted_verdict(
        bundle("sha256:" + "f" * 64),
        build(base_image_id=CANONICAL, image_id="sha256:" + "f" * 64),
    )
    control_passed = (
        control.record.verdict == Verdict.CONTRADICTED
        and control.provisional_verdict is None
        and not control.verdict_gate_reasons
    )
    canonical = json.dumps(attacks, sort_keys=True, separators=(",", ":"))
    report = {
        "schema": "immutable-image-identity-gate-v1",
        "attack_cases": len(attacks),
        "rejected": sum(item["passed"] for item in attacks),
        "false_decisive_verdicts": sum(
            item["public_verdict"] != "UNABLE_TO_VERIFY" for item in attacks
        ),
        "measurements_preserved": all(
            item["provisional_verdict"] == "CONTRADICTED" for item in attacks
        ),
        "canonical_control_passed": control_passed,
        "digest": hashlib.sha256(canonical.encode()).hexdigest(),
        "attacks": attacks,
        "passed": all(item["passed"] for item in attacks) and control_passed,
    }
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: value for key, value in report.items()
                      if key != "attacks"}, indent=2, sort_keys=True))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
