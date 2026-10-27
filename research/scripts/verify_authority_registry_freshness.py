#!/usr/bin/env python3
"""Execute the frozen exact-snapshot registry rollback matrix."""

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

OUT = Path("research/results/authority-registry-freshness.json")
NOW = datetime(2026, 10, 27, tzinfo=UTC)
FLOOR = 41
FAMILIES = (
    "revocation_rollback",
    "domain_rollback",
    "quorum_rollback",
    "keyset_rollback",
)


def credential(seed: int, issuer: str, key_id: str, domain: str):
    private = Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32)
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    key = TrustedAuthorityKey(
        issuer=issuer,
        key_id=key_id,
        public_key_pem=public_pem,
        trust_domain=domain,
    )
    return private_pem, key


PRIVATE_A, KEY_A = credential(17, "board-a", "key-a", "operator-a")
PRIVATE_B, KEY_B = credential(29, "board-b", "key-b", "operator-b")
_, KEY_C = credential(43, "board-c", "key-c", "operator-a")
_, KEY_D = credential(59, "board-d", "key-d", "operator-b")


def registries(family: str):
    old = TrustedAuthorityRegistry(
        registry_epoch=40,
        minimum_signatures=2,
        minimum_trust_domains=2,
        keys=[KEY_A, KEY_B],
    )
    credentials = (
        (KEY_A.issuer, KEY_A.key_id, PRIVATE_A),
        (KEY_B.issuer, KEY_B.key_id, PRIVATE_B),
    )
    if family == "revocation_rollback":
        current = old.model_copy(deep=True)
        current.registry_epoch = FLOOR
        current.keys[1].status = "revoked"
    elif family == "domain_rollback":
        current = old.model_copy(deep=True)
        current.registry_epoch = FLOOR
        current.keys[1].trust_domain = "operator-a"
    elif family == "quorum_rollback":
        old.minimum_signatures = 1
        old.minimum_trust_domains = 1
        credentials = credentials[:1]
        current = old.model_copy(deep=True)
        current.registry_epoch = FLOOR
        current.minimum_signatures = 2
        current.minimum_trust_domains = 2
    elif family == "keyset_rollback":
        current = old.model_copy(deep=True)
        current.registry_epoch = FLOOR
        current.keys = [KEY_C, KEY_D]
    elif family == "control":
        current = old.model_copy(deep=True)
        current.registry_epoch = FLOOR
        old = current.model_copy(deep=True)
    else:
        raise ValueError(family)
    return old, current, credentials


def bundle(case: int) -> VerificationBundle:
    value = 0.55 + (case % 30) / 100
    claim = Claim(
        id=f"FRESH-{case:04d}",
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
        image_ref="freshness-test",
        image_id="sha256:" + "c" * 64,
        base_image_id="sha256:" + "e" * 64,
        stdout_sha256="3" * 64,
        stderr_sha256="4" * 64,
    )


def run_case(case: int, family: str) -> dict:
    item = bundle(case)
    supplied, current, credentials = registries(family)
    item.authority_attestations = [
        sign_authority_scope(
            authority_scope_for_bundle(
                item,
                registry=supplied,
                issuer=issuer,
                key_id=key_id,
                issued_at=NOW - timedelta(days=1),
                expires_at=NOW + timedelta(days=30),
            ),
            private,
        )
        for issuer, key_id, private in credentials
    ]
    parent = gate_hosted_verdict(
        item,
        build(),
        trusted_authority_registry=supplied,
        require_registry_authority=True,
        authority_validation_time=NOW,
    )
    corrected = gate_hosted_verdict(
        item,
        build(),
        trusted_authority_registry=supplied,
        require_registry_authority=True,
        authority_validation_time=NOW,
        trusted_minimum_registry_epoch=FLOOR,
        require_registry_freshness=True,
    )
    return {
        "case": case,
        "family": family,
        "trusted_minimum_registry_epoch": FLOOR,
        "supplied_registry": supplied.model_dump(mode="json"),
        "current_registry": current.model_dump(mode="json"),
        "supplied_registry_sha256": authority_registry_sha256(supplied),
        "current_registry_sha256": authority_registry_sha256(current),
        "attestations": [value.model_dump(mode="json") for value in item.authority_attestations],
        "parent_definitive": parent.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "corrected_definitive": corrected.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "corrected_reasons": corrected.verdict_gate_reasons,
    }


def main() -> None:
    attacks = [
        run_case(10000 + 100 * index + offset, family)
        for index, family in enumerate(FAMILIES)
        for offset in range(32)
    ]
    controls = [run_case(20000 + offset, "control") for offset in range(32)]
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
        "schema": "agnxiv.authority-registry-freshness/1",
        "validation_time": NOW.isoformat(),
        "attacks": attacks,
        "controls": controls,
        "summary": summary,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    raise SystemExit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()
