#!/usr/bin/env python3
"""Replay the frozen authority-domain quorum falsification matrix."""

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

OUT = Path("research/results/authority-domain-quorum.json")
NOW = datetime(2026, 10, 27, tzinfo=UTC)
FAMILIES = (
    "same_issuer_two_keys",
    "aliased_issuers_one_domain",
    "missing_domain_metadata",
    "revoked_second_domain",
)


def credential(seed: int, issuer: str, key_id: str, domain: str | None, status: str = "active"):
    private = Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32)
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    key = TrustedAuthorityKey(
        issuer=issuer,
        key_id=key_id,
        public_key_pem=private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode(),
        trust_domain=domain,
        status=status,
    )
    return key, private_pem


def bundle(case: int) -> VerificationBundle:
    value = 0.5 + (case % 40) / 100
    claim = Claim(id=f"CLAIM-{case:04d}", text=f"Accuracy is {value}", metric="accuracy", reported_value=value)
    return VerificationBundle(
        verification_authority="auto_planned",
        authority_evidence_sha256=hashlib.sha256(f"locator:{case}".encode()).hexdigest(),
        claim=claim,
        manuscript=DocumentFingerprint(
            name="paper.pdf",
            sha256=hashlib.sha256(f"paper:{case}".encode()).hexdigest(),
            size_bytes=2048,
        ),
        provenance=ProvenanceManifest(
            files=[], file_count=0, total_bytes=0,
            tree_digest=hashlib.sha256(f"tree:{case}".encode()).hexdigest(),
        ),
        environment=EnvironmentSpec(historical_fidelity="constrained", scope_resolution="resolved"),
        execution=ExecutionSummary(
            command=["python"], image_id="sha256:" + "c" * 64, returncode=0,
            stdout_sha256="1" * 64, stderr_sha256="2" * 64,
            stdout_excerpt="", stderr_excerpt="",
            pre_execution_tree_sha256="a" * 64,
            post_execution_tree_sha256="a" * 64,
            source_unchanged=True, artifacts_unchanged=True,
        ),
        record=verify_numeric_claim(
            claim, [Observation(value=value)], VerificationPolicy(kind="absolute", tolerance=0)
        ),
    )


def build() -> BuildResult:
    return BuildResult(
        plan=BuildPlan(
            base_image="python:3.11-slim", dependency_file="requirements.txt",
            dependency_sha256="b" * 64, dependency_precision="hash-pinned",
            dockerfile="FROM python:3.11-slim\n", network_required=True,
            safe_manifest_only=True,
        ),
        image_ref="test", image_id="sha256:" + "c" * 64,
        base_image_id="sha256:" + "e" * 64,
        stdout_sha256="3" * 64, stderr_sha256="4" * 64,
    )


def credentials(family: str):
    if family == "same_issuer_two_keys":
        return [
            credential(7, "board-a", "key-1", "operator-a"),
            credential(8, "board-a", "key-2", "operator-a"),
        ]
    if family == "aliased_issuers_one_domain":
        return [
            credential(7, "board-a", "key-1", "operator-a"),
            credential(8, "board-a-alias", "key-2", "operator-a"),
        ]
    if family == "missing_domain_metadata":
        return [
            credential(7, "board-a", "key-1", "operator-a"),
            credential(8, "board-b", "key-2", None),
        ]
    if family == "revoked_second_domain":
        return [
            credential(7, "board-a", "key-1", "operator-a"),
            credential(8, "board-a-alias", "key-2", "operator-a"),
            credential(9, "board-b", "key-3", "operator-b", "revoked"),
        ]
    if family == "control":
        return [
            credential(7, "board-a", "key-1", "operator-a"),
            credential(8, "board-b", "key-2", "operator-b"),
        ]
    raise ValueError(family)


def run_case(case: int, family: str) -> dict:
    item = bundle(case)
    creds = credentials(family)
    item.authority_attestations = [
        sign_authority_scope(
            authority_scope_for_bundle(
                item,
                issuer=key.issuer,
                key_id=key.key_id,
                issued_at=NOW - timedelta(days=1),
                expires_at=NOW + timedelta(days=30),
            ),
            private,
        )
        for key, private in creds
        if key.status == "active"
    ]
    parent_registry = TrustedAuthorityRegistry(minimum_signatures=2, keys=[key for key, _ in creds])
    corrected_registry = TrustedAuthorityRegistry(
        minimum_signatures=2,
        minimum_trust_domains=2,
        keys=[key for key, _ in creds],
    )
    parent = gate_hosted_verdict(
        item, build(), trusted_authority_registry=parent_registry,
        require_registry_authority=True, authority_validation_time=NOW,
    )
    corrected = gate_hosted_verdict(
        item, build(), trusted_authority_registry=corrected_registry,
        require_registry_authority=True, authority_validation_time=NOW,
    )
    return {
        "case": case,
        "family": family,
        "parent_definitive": parent.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "corrected_definitive": corrected.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "attestations": [a.model_dump(mode="json") for a in item.authority_attestations],
    }


def main() -> None:
    attacks = [
        run_case(1000 + 100 * i + j, family)
        for i, family in enumerate(FAMILIES)
        for j in range(32)
    ]
    controls = [run_case(5000 + j, "control") for j in range(32)]
    summary = {
        "parent_attacks_definitive": sum(x["parent_definitive"] for x in attacks),
        "corrected_attacks_definitive": sum(x["corrected_definitive"] for x in attacks),
        "attack_total": len(attacks),
        "corrected_controls_definitive": sum(x["corrected_definitive"] for x in controls),
        "control_total": len(controls),
        "attack_families_blocked": {
            family: sum(x["family"] == family and not x["corrected_definitive"] for x in attacks)
            for family in FAMILIES
        },
    }
    summary["passed"] = (
        summary["parent_attacks_definitive"] == 128
        and summary["corrected_attacks_definitive"] == 0
        and summary["corrected_controls_definitive"] == 32
        and all(v == 32 for v in summary["attack_families_blocked"].values())
    )
    report = {
        "schema": "agnxiv.authority-domain-quorum/1",
        "validation_time": NOW.isoformat(),
        "registries": {
            family: [key.model_dump(mode="json") for key, _ in credentials(family)]
            for family in (*FAMILIES, "control")
        },
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
