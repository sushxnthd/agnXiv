#!/usr/bin/env python3
"""Execute the frozen cross-registry checkpoint-scope matrix."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agnxiv.authority import (
    TrustedAuthorityKey,
    TrustedAuthorityRegistry,
    TrustedRegistryCheckpoint,
    authority_registry_sha256,
    authority_scope_for_bundle,
    sign_authority_scope,
)
from agnxiv.build import BuildPlan, BuildResult
from agnxiv.environment import EnvironmentSpec
from agnxiv.models import Claim, Observation, Verdict, VerificationPolicy
from agnxiv.pipeline import ExecutionSummary, VerificationBundle
from agnxiv.provenance import DocumentFingerprint, ProvenanceManifest
from agnxiv.verdict_gate import gate_hosted_verdict
from agnxiv.verify import verify_numeric_claim

OUT = Path("research/results/authority-registry-checkpoint-scope.json")
NOW = datetime(2026, 10, 28, tzinfo=UTC)
EPOCH = 73
FAMILIES = {
    "staging_to_production": ("staging-release", "production-release"),
    "tenant_to_tenant": ("tenant-blue", "tenant-green"),
    "paper_track_to_release_gate": ("paper-track", "release-gate"),
    "benchmark_to_external_audit": ("benchmark", "external-audit"),
}


def credential():
    private = Ed25519PrivateKey.from_private_bytes(b"\x35" * 32)
    return private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ), private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


PRIVATE, PUBLIC = credential()


def bundle(case: int) -> VerificationBundle:
    value = 0.55 + (case % 30) / 100
    claim = Claim(
        id=f"CHECKPOINT-SCOPE-{case:04d}",
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
        image_ref="checkpoint-scope-test",
        image_id="sha256:" + "c" * 64,
        base_image_id="sha256:" + "e" * 64,
        stdout_sha256="3" * 64,
        stderr_sha256="4" * 64,
    )


def run_case(case: int, family: str, *, control: bool = False) -> dict:
    foreign_namespace, registry_namespace = FAMILIES[family]
    checkpoint_namespace = registry_namespace if control else foreign_namespace
    item = bundle(case)
    registry = TrustedAuthorityRegistry(
        registry_namespace=registry_namespace,
        registry_epoch=EPOCH,
        keys=[
            TrustedAuthorityKey(
                issuer="review-board",
                key_id="primary",
                public_key_pem=PUBLIC,
                trust_domain="independent-board",
            )
        ],
    )
    item.authority_attestations = [
        sign_authority_scope(
            authority_scope_for_bundle(
                item,
                registry=registry,
                issuer="review-board",
                key_id="primary",
                issued_at=NOW - timedelta(minutes=1),
                expires_at=NOW + timedelta(days=1),
            ),
            PRIVATE,
        )
    ]
    parent = gate_hosted_verdict(
        item,
        build(),
        trusted_authority_registry=registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
        trusted_minimum_registry_epoch=EPOCH,
        require_registry_freshness=True,
    )
    checkpoint = TrustedRegistryCheckpoint(
        registry_namespace=checkpoint_namespace,
        minimum_registry_epoch=EPOCH,
    )
    corrected = gate_hosted_verdict(
        item,
        build(),
        trusted_authority_registry=registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
        trusted_registry_checkpoint=checkpoint,
        require_registry_checkpoint_scope=True,
    )
    return {
        "case": case,
        "family": family,
        "control": control,
        "registry": registry.model_dump(mode="json"),
        "registry_sha256": authority_registry_sha256(registry),
        "checkpoint": checkpoint.model_dump(mode="json"),
        "signed_scope": item.authority_attestations[0].scope.model_dump(mode="json"),
        "parent_definitive": parent.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "corrected_definitive": corrected.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "corrected_reasons": corrected.verdict_gate_reasons,
    }


def main() -> None:
    attacks = [
        run_case(30000 + 100 * index + offset, family)
        for index, family in enumerate(FAMILIES)
        for offset in range(32)
    ]
    controls = [
        run_case(40000 + offset, family, control=True)
        for offset, family in enumerate(tuple(FAMILIES) * 8)
    ]
    summary = {
        "attack_total": len(attacks),
        "parent_attacks_definitive": sum(row["parent_definitive"] for row in attacks),
        "corrected_attacks_definitive": sum(
            row["corrected_definitive"] for row in attacks
        ),
        "control_total": len(controls),
        "corrected_controls_definitive": sum(
            row["corrected_definitive"] for row in controls
        ),
        "families_blocked": {
            family: sum(
                row["family"] == family and not row["corrected_definitive"]
                for row in attacks
            )
            for family in FAMILIES
        },
    }
    summary["passed"] = (
        summary["parent_attacks_definitive"] == 128
        and summary["corrected_attacks_definitive"] == 0
        and summary["corrected_controls_definitive"] == 32
        and all(value == 32 for value in summary["families_blocked"].values())
    )
    report = {
        "schema": "agnxiv.authority-registry-checkpoint-scope/1",
        "validation_time": NOW.isoformat(),
        "attacks": attacks,
        "controls": controls,
        "summary": summary,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    raise SystemExit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()
