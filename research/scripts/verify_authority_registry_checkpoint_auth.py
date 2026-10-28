#!/usr/bin/env python3
"""Execute the frozen forged-checkpoint authentication matrix."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agnxiv.authority import (
    RegistryCheckpointScope,
    TrustedAuthorityKey,
    TrustedAuthorityRegistry,
    TrustedRegistryCheckpoint,
    TrustedRegistryCheckpointKey,
    authority_registry_sha256,
    authority_scope_for_bundle,
    canonical_registry_checkpoint_payload,
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

OUT = Path("research/results/authority-registry-checkpoint-auth.json")
NOW = datetime(2026, 10, 28, tzinfo=UTC)
CURRENT_EPOCH = 73
OBSOLETE_EPOCH = 41
FAMILIES = ("revocation", "trust_domain", "quorum", "key_set")


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
CHECKPOINT_PRIVATE, CHECKPOINT_PUBLIC = credential(67)
CHECKPOINT_KEYS = [
    TrustedRegistryCheckpointKey(
        issuer="checkpoint-board",
        key_id="monotonic-floor",
        public_key_pem=CHECKPOINT_PUBLIC,
    )
]


def bundle(case: int) -> VerificationBundle:
    value = 0.55 + (case % 30) / 100
    claim = Claim(
        id=f"CHECKPOINT-AUTH-{case:04d}",
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
        image_ref="checkpoint-auth-test",
        image_id="sha256:" + "c" * 64,
        base_image_id="sha256:" + "e" * 64,
        stdout_sha256="3" * 64,
        stderr_sha256="4" * 64,
    )


def run_case(case: int, family: str, *, control: bool = False) -> dict:
    epoch = CURRENT_EPOCH if control else OBSOLETE_EPOCH
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
    legitimate = sign_registry_checkpoint(
        RegistryCheckpointScope(
            issuer="checkpoint-board",
            key_id="monotonic-floor",
            registry_namespace="production-release",
            minimum_registry_epoch=CURRENT_EPOCH,
        ),
        CHECKPOINT_PRIVATE,
    )
    supplied = legitimate.model_copy(deep=True)
    if not control:
        supplied.scope.minimum_registry_epoch = OBSOLETE_EPOCH
    parent = gate_hosted_verdict(
        item.model_copy(deep=True),
        build(),
        trusted_authority_registry=registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
        trusted_registry_checkpoint=TrustedRegistryCheckpoint(
            registry_namespace=supplied.scope.registry_namespace,
            minimum_registry_epoch=supplied.scope.minimum_registry_epoch,
        ),
        require_registry_checkpoint_scope=True,
    )
    corrected = gate_hosted_verdict(
        item.model_copy(deep=True),
        build(),
        trusted_authority_registry=registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
        signed_registry_checkpoint=supplied,
        trusted_registry_checkpoint_keys=CHECKPOINT_KEYS,
        require_authenticated_registry_checkpoint=True,
    )
    return {
        "case": case,
        "family": family,
        "control": control,
        "registry_epoch": epoch,
        "registry_sha256": authority_registry_sha256(registry),
        "legitimate_checkpoint_scope": legitimate.scope.model_dump(mode="json"),
        "supplied_checkpoint_scope": supplied.scope.model_dump(mode="json"),
        "legitimate_payload_sha256": hashlib.sha256(
            canonical_registry_checkpoint_payload(legitimate.scope)
        ).hexdigest(),
        "supplied_payload_sha256": hashlib.sha256(
            canonical_registry_checkpoint_payload(supplied.scope)
        ).hexdigest(),
        "signature_reused": supplied.signature_b64 == legitimate.signature_b64,
        "parent_definitive": parent.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "corrected_definitive": corrected.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "corrected_reasons": corrected.verdict_gate_reasons,
    }


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
    summary = {
        "attack_total": len(attacks),
        "parent_false_passes": sum(row["parent_definitive"] for row in attacks),
        "authenticated_false_passes": sum(
            row["corrected_definitive"] for row in attacks
        ),
        "control_total": len(controls),
        "authenticated_controls_passed": sum(
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
        summary["parent_false_passes"] == 128
        and summary["authenticated_false_passes"] == 0
        and summary["authenticated_controls_passed"] == 32
        and all(value == 32 for value in summary["families_blocked"].values())
    )
    report = {
        "schema": "agnxiv.authority-registry-checkpoint-auth/1",
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
