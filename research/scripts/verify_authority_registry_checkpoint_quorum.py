#!/usr/bin/env python3
"""Execute the frozen single-checkpoint-domain compromise matrix."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agnxiv.authority import (
    RegistryCheckpointQuorumPolicy,
    RegistryCheckpointScope,
    TrustedAuthorityKey,
    TrustedAuthorityRegistry,
    TrustedRegistryCheckpointKey,
    authority_registry_sha256,
    authority_scope_for_bundle,
    sign_authority_scope,
    sign_registry_checkpoint,
)
from agnxiv.build import BuildPlan, BuildResult
from agnxiv.environment import EnvironmentSpec
from agnxiv.models import Claim, Observation, Verdict, VerificationPolicy
from agnxiv.pipeline import ExecutionSummary, VerificationBundle
from agnxiv.provenance import DocumentFingerprint, ProvenanceManifest
from agnxiv.verdict_gate import gate_hosted_verdict
from agnxiv.verify import verify_numeric_claim

OUT = Path("research/results/authority-registry-checkpoint-quorum.json")
NOW = datetime(2026, 10, 28, tzinfo=UTC)
CURRENT_EPOCH = 89
OBSOLETE_EPOCH = 55
FAMILIES = ("revocation", "trust_domain", "quorum", "key_set")
POLICY = RegistryCheckpointQuorumPolicy(minimum_signatures=2, minimum_trust_domains=2)


def credential(seed: int):
    private = Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32)
    return private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ), private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


AUTHORITY_PRIVATE, AUTHORITY_PUBLIC = credential(61)
CHECKPOINT_MATERIAL = tuple(credential(seed) for seed in (67, 68, 69))
CHECKPOINT_KEYS = [
    TrustedRegistryCheckpointKey(
        issuer=f"checkpoint-board-{index}",
        key_id="monotonic-floor",
        public_key_pem=public,
        trust_domain=f"operator-{chr(96 + index)}",
    )
    for index, (_, public) in enumerate(CHECKPOINT_MATERIAL, start=1)
]


def bundle(case: int) -> VerificationBundle:
    value = 0.55 + (case % 30) / 100
    claim = Claim(
        id=f"CHECKPOINT-QUORUM-{case:04d}",
        text=f"Accuracy is {value}",
        metric="accuracy",
        reported_value=value,
    )
    return VerificationBundle(
        verification_authority="auto_planned",
        authority_evidence_sha256=hashlib.sha256(f"locator:{case}".encode()).hexdigest(),
        claim=claim,
        manuscript=DocumentFingerprint(
            name="paper.pdf",
            sha256=hashlib.sha256(f"paper:{case}".encode()).hexdigest(),
            size_bytes=4096,
        ),
        provenance=ProvenanceManifest(
            files=[],
            file_count=0,
            total_bytes=0,
            tree_digest=hashlib.sha256(f"tree:{case}".encode()).hexdigest(),
        ),
        environment=EnvironmentSpec(
            historical_fidelity="constrained",
            scope_resolution="resolved",
        ),
        execution=ExecutionSummary(
            command=["python"],
            image_id="sha256:" + "c" * 64,
            returncode=0,
            stdout_sha256="1" * 64,
            stderr_sha256="2" * 64,
            stdout_excerpt="",
            stderr_excerpt="",
            pre_execution_tree_sha256="a" * 64,
            post_execution_tree_sha256="a" * 64,
            source_unchanged=True,
            artifacts_unchanged=True,
        ),
        record=verify_numeric_claim(
            claim,
            [Observation(value=value)],
            VerificationPolicy(kind="absolute", tolerance=0),
        ),
    )


def build() -> BuildResult:
    return BuildResult(
        plan=BuildPlan(
            base_image="python:3.11-slim",
            dependency_file="requirements.txt",
            dependency_sha256="b" * 64,
            dependency_precision="hash-pinned",
            dockerfile="FROM python:3.11-slim\n",
            network_required=True,
            safe_manifest_only=True,
        ),
        image_ref="checkpoint-quorum-test",
        image_id="sha256:" + "c" * 64,
        base_image_id="sha256:" + "e" * 64,
        stdout_sha256="3" * 64,
        stderr_sha256="4" * 64,
    )


def checkpoint(index: int, floor: int):
    private, _ = CHECKPOINT_MATERIAL[index]
    scope = RegistryCheckpointScope(
        issuer=f"checkpoint-board-{index + 1}",
        key_id="monotonic-floor",
        registry_namespace="production-release",
        minimum_registry_epoch=floor,
    )
    return sign_registry_checkpoint(scope, private)


def case_material(case: int, family: str, epoch: int):
    item = bundle(case)
    registry = TrustedAuthorityRegistry(
        registry_namespace="production-release",
        registry_epoch=epoch,
        minimum_signatures=1,
        minimum_trust_domains=1,
        keys=[
            TrustedAuthorityKey(
                issuer=f"review-board-{family}",
                key_id="primary",
                public_key_pem=AUTHORITY_PUBLIC,
                trust_domain=f"legacy-{family}",
            )
        ],
    )
    item.authority_attestations = [
        sign_authority_scope(
            authority_scope_for_bundle(
                item,
                registry=registry,
                issuer=f"review-board-{family}",
                key_id="primary",
                issued_at=NOW - timedelta(minutes=1),
                expires_at=NOW + timedelta(days=1),
            ),
            AUTHORITY_PRIVATE,
        )
    ]
    return item, registry


def gate(item, registry, checkpoints, keys, *, quorum):
    kwargs = {
        "trusted_authority_registry": registry,
        "require_registry_authority": True,
        "authority_validation_time": NOW,
        "trusted_registry_checkpoint_keys": keys,
    }
    if quorum:
        kwargs.update(
            signed_registry_checkpoints=checkpoints,
            registry_checkpoint_quorum=POLICY,
            require_registry_checkpoint_quorum=True,
        )
    else:
        kwargs.update(
            signed_registry_checkpoint=checkpoints[0],
            require_authenticated_registry_checkpoint=True,
        )
    return gate_hosted_verdict(item, build(), **kwargs)


def run_case(case: int, family: str, *, control: bool = False) -> dict:
    epoch = CURRENT_EPOCH if control else OBSOLETE_EPOCH
    item, registry = case_material(case, family, epoch)
    supplied = (
        [checkpoint(1, CURRENT_EPOCH), checkpoint(2, CURRENT_EPOCH)]
        if control
        else [checkpoint(0, OBSOLETE_EPOCH)]
    )
    parent = gate(item.model_copy(deep=True), registry, supplied, CHECKPOINT_KEYS, quorum=False)
    corrected = gate(item.model_copy(deep=True), registry, supplied, CHECKPOINT_KEYS, quorum=True)
    return {
        "case": case,
        "family": family,
        "control": control,
        "registry_epoch": epoch,
        "registry_sha256": authority_registry_sha256(registry),
        "supplied_checkpoints": [row.model_dump(mode="json") for row in supplied],
        "parent_definitive": parent.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "quorum_definitive": corrected.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "quorum_reasons": corrected.verdict_gate_reasons,
    }


def adversarial_controls():
    item, registry = case_material(70000, "control", CURRENT_EPOCH)
    compromised = checkpoint(0, OBSOLETE_EPOCH)
    current_a = checkpoint(1, CURRENT_EPOCH)
    current_b = checkpoint(2, CURRENT_EPOCH)
    same_domain_keys = [
        CHECKPOINT_KEYS[0],
        CHECKPOINT_KEYS[1].model_copy(update={"trust_domain": "operator-a"}),
    ]
    revoked_keys = [
        CHECKPOINT_KEYS[1],
        CHECKPOINT_KEYS[2].model_copy(update={"status": "revoked"}),
    ]
    scenarios = (
        ("duplicate_identity", [compromised, compromised], CHECKPOINT_KEYS),
        ("same_domain", [checkpoint(0, CURRENT_EPOCH), current_a], same_domain_keys),
        ("disagreeing_floors", [compromised, current_a], CHECKPOINT_KEYS),
        ("revoked_key", [current_a, current_b], revoked_keys),
    )
    return [
        {
            "name": name,
            "definitive": (
                gated := gate(
                    item.model_copy(deep=True), registry, checkpoints, keys, quorum=True
                )
            ).record.verdict
            != Verdict.UNABLE_TO_VERIFY,
            "reasons": gated.verdict_gate_reasons,
        }
        for name, checkpoints, keys in scenarios
    ]


def main() -> None:
    attacks = [
        run_case(50000 + 100 * index + offset, family)
        for index, family in enumerate(FAMILIES)
        for offset in range(32)
    ]
    controls = [
        run_case(60000 + offset, family, control=True)
        for offset, family in enumerate(FAMILIES * 8)
    ]
    stress = adversarial_controls()
    summary = {
        "attack_total": len(attacks),
        "parent_false_passes": sum(row["parent_definitive"] for row in attacks),
        "quorum_false_passes": sum(row["quorum_definitive"] for row in attacks),
        "control_total": len(controls),
        "quorum_controls_passed": sum(row["quorum_definitive"] for row in controls),
        "adversarial_controls_blocked": sum(not row["definitive"] for row in stress),
        "families_blocked": {
            family: sum(
                row["family"] == family and not row["quorum_definitive"]
                for row in attacks
            )
            for family in FAMILIES
        },
    }
    summary["passed"] = (
        summary["parent_false_passes"] == 128
        and summary["quorum_false_passes"] == 0
        and summary["quorum_controls_passed"] == 32
        and summary["adversarial_controls_blocked"] == 4
        and all(value == 32 for value in summary["families_blocked"].values())
    )
    report = {
        "schema": "agnxiv.authority-registry-checkpoint-quorum/1",
        "validation_time": NOW.isoformat(),
        "quorum_policy": POLICY.model_dump(mode="json"),
        "checkpoint_keys": [key.model_dump(mode="json") for key in CHECKPOINT_KEYS],
        "attacks": attacks,
        "controls": controls,
        "adversarial_controls": stress,
        "summary": summary,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    raise SystemExit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()
