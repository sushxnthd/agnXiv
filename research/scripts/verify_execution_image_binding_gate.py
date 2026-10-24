"""Frozen adversarial verifier for build-to-execution image binding."""

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
OUT = ROOT / "research" / "results" / "execution-image-binding-gate.json"


def image_id(digest: str) -> str:
    return "sha256:" + digest


def bundle(execution_image_id: str | None) -> VerificationBundle:
    claim = Claim(
        id="C1", text="Accuracy is 0.9", metric="accuracy", reported_value=0.9
    )
    execution = None
    if execution_image_id is not None:
        execution = ExecutionSummary(
            command=["docker", "run"],
            image_id=execution_image_id,
            returncode=0,
            stdout_sha256="1" * 64,
            stderr_sha256="2" * 64,
            stdout_excerpt="",
            stderr_excerpt="",
            pre_execution_tree_sha256="3" * 64,
            post_execution_tree_sha256="3" * 64,
            source_unchanged=True,
            artifacts_unchanged=True,
        )
    return VerificationBundle(
        claim=claim,
        provenance=ProvenanceManifest(
            files=[], file_count=0, total_bytes=0, tree_digest="3" * 64
        ),
        environment=EnvironmentSpec(
            historical_fidelity="constrained", scope_resolution="resolved"
        ),
        execution=execution,
        record=verify_numeric_claim(
            claim,
            [Observation(value=0.8)],
            VerificationPolicy(kind="absolute", tolerance=0.01),
        ),
    )


def build(built_image_id: str) -> BuildResult:
    return BuildResult(
        plan=BuildPlan(
            base_image="python:3.11-slim",
            dependency_file="requirements.txt",
            dependency_sha256="4" * 64,
            dependency_precision="hash-pinned",
            dockerfile="FROM python:3.11-slim\n",
            network_required=True,
            safe_manifest_only=True,
        ),
        image_ref="agnxiv-env:frozen",
        image_id=built_image_id,
        base_image_id=image_id("5" * 64),
        stdout_sha256="6" * 64,
        stderr_sha256="7" * 64,
    )


def substitution_cases() -> list[dict[str, str]]:
    cases = []
    for position in range(64):
        for built_nibble, executed_nibble in (("a", "b"), ("b", "a")):
            built_digest = list("a" * 64)
            executed_digest = list("a" * 64)
            built_digest[position] = built_nibble
            executed_digest[position] = executed_nibble
            cases.append({
                "position": str(position),
                "built_image_id": image_id("".join(built_digest)),
                "execution_image_id": image_id("".join(executed_digest)),
            })
    return cases


def main() -> None:
    attacks = []
    for case in substitution_cases():
        gated = gate_hosted_verdict(
            bundle(case["execution_image_id"]), build(case["built_image_id"])
        )
        attacks.append({
            **case,
            "public_verdict": gated.record.verdict.value,
            "provisional_verdict": (
                gated.provisional_verdict.value if gated.provisional_verdict else None
            ),
            "measurement_preserved": (
                gated.record.expected == 0.9 and gated.record.observed_mean == 0.8
            ),
            "binding_blocker": any(
                "does not match" in reason for reason in gated.verdict_gate_reasons
            ),
        })

    controls = []
    for nibble in ("0", "7", "a", "f"):
        candidate = image_id(nibble * 64)
        gated = gate_hosted_verdict(bundle(candidate), build(candidate))
        controls.append({
            "image_id": candidate,
            "public_verdict": gated.record.verdict.value,
            "passed": gated.record.verdict == Verdict.CONTRADICTED,
        })

    missing = gate_hosted_verdict(bundle(None), build(image_id("a" * 64)))
    malformed = gate_hosted_verdict(
        bundle("sha256:execution"), build(image_id("a" * 64))
    )
    hosted_source = (ROOT / "src" / "agnxiv" / "hosted_runner.py").read_text(
        encoding="utf-8"
    )
    hosted_paths_immutable = all(
        marker in hosted_source
        for marker in (
            "run_zero_manifest(paper, repo, image=build.image_id)",
            "image_override=build.image_id",
        )
    )
    rejected = sum(
        item["public_verdict"] == "UNABLE_TO_VERIFY"
        and item["provisional_verdict"] == "CONTRADICTED"
        and item["measurement_preserved"]
        and item["binding_blocker"]
        for item in attacks
    )
    canonical = json.dumps(attacks, sort_keys=True, separators=(",", ":"))
    report = {
        "schema": "execution-image-binding-gate-v1",
        "attack_cases": len(attacks),
        "rejected": rejected,
        "false_decisive_verdicts": len(attacks) - rejected,
        "measurements_preserved": all(
            item["measurement_preserved"] for item in attacks
        ),
        "missing_execution_rejected": missing.record.verdict == Verdict.UNABLE_TO_VERIFY,
        "malformed_execution_rejected": malformed.record.verdict == Verdict.UNABLE_TO_VERIFY,
        "exact_match_controls": len(controls),
        "exact_match_controls_passed": sum(item["passed"] for item in controls),
        "hosted_execution_paths_bound_to_immutable_id": hosted_paths_immutable,
        "digest": hashlib.sha256(canonical.encode()).hexdigest(),
        "attacks": attacks,
        "controls": controls,
    }
    report["passed"] = (
        rejected == len(attacks)
        and report["measurements_preserved"]
        and report["missing_execution_rejected"]
        and report["malformed_execution_rejected"]
        and report["exact_match_controls_passed"] == len(controls)
        and report["hosted_execution_paths_bound_to_immutable_id"]
    )
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(
        {k: v for k, v in report.items() if k not in {"attacks", "controls"}},
        indent=2,
        sort_keys=True,
    ))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
