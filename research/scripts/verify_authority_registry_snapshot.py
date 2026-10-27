#!/usr/bin/env python3
"""Execute the frozen authority-registry snapshot substitution matrix."""

from __future__ import annotations

import base64
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
    canonical_authority_payload,
    sign_authority_scope,
)
from agnxiv.build import BuildPlan, BuildResult
from agnxiv.environment import EnvironmentSpec
from agnxiv.models import Claim, Observation, Verdict, VerificationPolicy
from agnxiv.pipeline import ExecutionSummary, VerificationBundle
from agnxiv.provenance import DocumentFingerprint, ProvenanceManifest
from agnxiv.verdict_gate import gate_hosted_verdict
from agnxiv.verify import verify_numeric_claim

OUT = Path("research/results/authority-registry-snapshot.json")
NOW = datetime(2026, 10, 27, tzinfo=UTC)
FAMILIES = (
    "trust_domain_remap",
    "revocation_rollback",
    "quorum_downgrade",
    "key_policy_swap",
)


def credential(seed: int, issuer: str, key_id: str, domain: str, status: str = "active"):
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
    return private_pem, public_pem, TrustedAuthorityKey(
        issuer=issuer,
        key_id=key_id,
        public_key_pem=public_pem,
        trust_domain=domain,
        status=status,
    )


PRIVATE_A, PUBLIC_A, _ = credential(17, "board-a", "key-a", "shared")
PRIVATE_B, PUBLIC_B, _ = credential(29, "board-b", "key-b", "shared")


def key(issuer: str, key_id: str, public: str, domain: str, status: str = "active"):
    return TrustedAuthorityKey(
        issuer=issuer,
        key_id=key_id,
        public_key_pem=public,
        trust_domain=domain,
        status=status,
    )


def registries(family: str):
    shared = [
        key("board-a", "key-a", PUBLIC_A, "shared"),
        key("board-b", "key-b", PUBLIC_B, "shared"),
    ]
    separate = [
        key("board-a", "key-a", PUBLIC_A, "operator-a"),
        key("board-b", "key-b", PUBLIC_B, "operator-b"),
    ]
    if family == "trust_domain_remap":
        return (
            TrustedAuthorityRegistry(minimum_signatures=2, minimum_trust_domains=2, keys=shared),
            TrustedAuthorityRegistry(minimum_signatures=2, minimum_trust_domains=2, keys=separate),
        )
    if family == "revocation_rollback":
        revoked = [shared[0], shared[1].model_copy(update={"status": "revoked"})]
        return (
            TrustedAuthorityRegistry(minimum_signatures=2, minimum_trust_domains=2, keys=revoked),
            TrustedAuthorityRegistry(minimum_signatures=2, minimum_trust_domains=2, keys=separate),
        )
    if family == "quorum_downgrade":
        return (
            TrustedAuthorityRegistry(minimum_signatures=2, minimum_trust_domains=2, keys=shared),
            TrustedAuthorityRegistry(minimum_signatures=1, minimum_trust_domains=1, keys=shared),
        )
    if family == "key_policy_swap":
        signed = [shared[0], shared[1].model_copy(update={"status": "revoked"})]
        interpreted = [separate[0], separate[1].model_copy(update={"status": "active"})]
        return (
            TrustedAuthorityRegistry(minimum_signatures=2, minimum_trust_domains=2, keys=signed),
            TrustedAuthorityRegistry(minimum_signatures=2, minimum_trust_domains=2, keys=interpreted),
        )
    if family == "control":
        exact = TrustedAuthorityRegistry(
            minimum_signatures=2,
            minimum_trust_domains=2,
            keys=separate,
        )
        return exact, exact.model_copy(deep=True)
    raise ValueError(family)


def bundle(case: int) -> VerificationBundle:
    value = 0.55 + (case % 30) / 100
    claim = Claim(id=f"SNAP-{case:04d}", text=f"Accuracy is {value}", metric="accuracy", reported_value=value)
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
        environment=EnvironmentSpec(historical_fidelity="constrained", scope_resolution="resolved"),
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
        image_ref="snapshot-test",
        image_id="sha256:" + "c" * 64,
        base_image_id="sha256:" + "e" * 64,
        stdout_sha256="3" * 64,
        stderr_sha256="4" * 64,
    )


def legacy_registry_accepts(item: VerificationBundle, registry: TrustedAuthorityRegistry) -> bool:
    """Reproduce the parent gate, which had no registry-digest comparison."""
    key_map = {(entry.issuer, entry.key_id): entry for entry in registry.keys}
    identities: set[tuple[str, str]] = set()
    domains: set[str] = set()
    for attestation in item.authority_attestations:
        scope = attestation.scope
        entry = key_map.get((scope.issuer, scope.key_id))
        if entry is None or entry.status != "active":
            continue
        public = serialization.load_pem_public_key(entry.public_key_pem.encode())
        try:
            public.verify(
                base64.b64decode(attestation.signature_b64, validate=True),
                canonical_authority_payload(scope),
            )
        except Exception:  # noqa: BLE001, S112 - exact parent accept/reject oracle
            continue
        identities.add((scope.issuer, scope.key_id))
        if entry.trust_domain is not None:
            domains.add(entry.trust_domain)
        elif registry.minimum_trust_domains == 1:
            domains.add(entry.issuer)
    return len(identities) >= registry.minimum_signatures and len(domains) >= registry.minimum_trust_domains


def run_case(case: int, family: str) -> dict:
    item = bundle(case)
    signing_registry, verification_registry = registries(family)
    credentials = (
        ("board-a", "key-a", PRIVATE_A),
        ("board-b", "key-b", PRIVATE_B),
    )
    item.authority_attestations = [
        sign_authority_scope(
            authority_scope_for_bundle(
                item,
                registry=signing_registry,
                issuer=issuer,
                key_id=key_id,
                issued_at=NOW - timedelta(days=1),
                expires_at=NOW + timedelta(days=30),
            ),
            private,
        )
        for issuer, key_id, private in credentials
    ]
    parent_definitive = legacy_registry_accepts(item, verification_registry)
    corrected = gate_hosted_verdict(
        item,
        build(),
        trusted_authority_registry=verification_registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
    )
    return {
        "case": case,
        "family": family,
        "signing_registry": signing_registry.model_dump(mode="json"),
        "verification_registry": verification_registry.model_dump(mode="json"),
        "signing_registry_sha256": authority_registry_sha256(signing_registry),
        "verification_registry_sha256": authority_registry_sha256(verification_registry),
        "parent_definitive": parent_definitive,
        "corrected_definitive": corrected.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "corrected_reasons": corrected.verdict_gate_reasons,
        "attestations": [value.model_dump(mode="json") for value in item.authority_attestations],
    }


def main() -> None:
    attacks = [
        run_case(6000 + 100 * i + j, family)
        for i, family in enumerate(FAMILIES)
        for j in range(32)
    ]
    controls = [run_case(9000 + j, "control") for j in range(32)]
    summary = {
        "parent_attacks_definitive": sum(row["parent_definitive"] for row in attacks),
        "corrected_attacks_definitive": sum(row["corrected_definitive"] for row in attacks),
        "attack_total": len(attacks),
        "corrected_controls_definitive": sum(row["corrected_definitive"] for row in controls),
        "control_total": len(controls),
        "families_blocked": {
            family: sum(row["family"] == family and not row["corrected_definitive"] for row in attacks)
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
        "schema": "agnxiv.authority-registry-snapshot/1",
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
