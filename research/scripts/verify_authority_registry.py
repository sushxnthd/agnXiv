#!/usr/bin/env python3
"""Adversarial replay of the trusted authority-registry boundary."""

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

OUT = Path("research/results/authority-registry.json")
NOW = datetime(2026, 10, 27, tzinfo=UTC)
FAMILIES = (
    "rogue_key",
    "altered_locator",
    "cross_claim",
    "cross_manuscript",
    "cross_repository",
    "expired",
)


def keys(seed):
    k = Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32)
    return (
        k.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
        k.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode(),
    )


def bundle(case):
    value = 0.5 + (case % 40) / 100
    claim = Claim(
        id=f"CLAIM-{case:04d}",
        text=f"Accuracy is {value}",
        metric="accuracy" if case % 2 == 0 else "f1",
        reported_value=value,
    )
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
            claim, [Observation(value=value)], VerificationPolicy(kind="absolute", tolerance=0)
        ),
    )


def build():
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
        image_ref="test",
        image_id="sha256:" + "c" * 64,
        base_image_id="sha256:" + "e" * 64,
        stdout_sha256="3" * 64,
        stderr_sha256="4" * 64,
    )


TRUSTED_PRIVATE, TRUSTED_PUBLIC = keys(7)
ROGUE_PRIVATE, _ = keys(9)
REGISTRY = TrustedAuthorityRegistry(
    keys=[
        TrustedAuthorityKey(
            issuer="independent-review-board", key_id="2026-01", public_key_pem=TRUSTED_PUBLIC
        )
    ]
)


def signed(item, private=TRUSTED_PRIVATE, expired=False):
    scope = authority_scope_for_bundle(
        item,
        issuer="independent-review-board",
        key_id="2026-01",
        issued_at=NOW - timedelta(days=2 if expired else 1),
        expires_at=NOW - timedelta(days=1) if expired else NOW + timedelta(days=30),
    )
    item.authority_attestations = [sign_authority_scope(scope, private)]
    return item


def strict(item):
    gated = gate_hosted_verdict(
        item,
        build(),
        trusted_authority_registry=REGISTRY,
        require_registry_authority=True,
        authority_validation_time=NOW,
    )
    return gated.record.verdict != Verdict.UNABLE_TO_VERIFY, gated.verdict_gate_reasons


def attacked(case, family):
    item = bundle(case)
    if family == "rogue_key":
        return signed(item, ROGUE_PRIVATE)
    signed(item, expired=family == "expired")
    if family == "altered_locator":
        item.authority_evidence_sha256 = hashlib.sha256(f"other:{case}".encode()).hexdigest()
    elif family == "cross_claim":
        item.claim.id = f"CROSSED-{case}"
    elif family == "cross_manuscript":
        item.manuscript.sha256 = hashlib.sha256(f"other-paper:{case}".encode()).hexdigest()
    elif family == "cross_repository":
        item.provenance.tree_digest = hashlib.sha256(f"other-tree:{case}".encode()).hexdigest()
    return item


def row(item, family=None):
    decisive, reasons = strict(item)
    att = item.authority_attestations[0]
    current = {
        "manuscript_sha256": item.manuscript.sha256,
        "repository_tree_sha256": item.provenance.tree_digest,
        "claim_id": item.claim.id,
        "metric": item.claim.metric,
        "authority_evidence_sha256": item.authority_evidence_sha256,
    }
    return {
        "family": family,
        "definitive": decisive,
        "reasons": reasons,
        "scope": att.scope.model_dump(mode="json"),
        "signature_b64": att.signature_b64,
        "current_object": current,
    }


def main():
    self_asserted = []
    for case in range(128):
        item = bundle(case)
        old = gate_hosted_verdict(item, build())
        decisive, reasons = strict(item)
        self_asserted.append(
            {
                "old_definitive": old.record.verdict != Verdict.UNABLE_TO_VERIFY,
                "strict_definitive": decisive,
                "reasons": reasons,
            }
        )
    controls = [row(signed(bundle(case))) for case in range(1000, 1032)]
    attacks = [
        row(attacked(2000 + 100 * i + j, f), f) for i, f in enumerate(FAMILIES) for j in range(32)
    ]
    summary = {
        "old_self_asserted_definitive": sum(x["old_definitive"] for x in self_asserted),
        "strict_self_asserted_definitive": sum(x["strict_definitive"] for x in self_asserted),
        "trusted_controls_definitive": sum(x["definitive"] for x in controls),
        "trusted_control_total": len(controls),
        "attacks_definitive": sum(x["definitive"] for x in attacks),
        "attack_total": len(attacks),
        "attack_families": {
            f: sum(x["family"] == f and not x["definitive"] for x in attacks) for f in FAMILIES
        },
    }
    summary["passed"] = (
        summary["old_self_asserted_definitive"] == 128
        and summary["strict_self_asserted_definitive"] == 0
        and summary["trusted_controls_definitive"] == 32
        and summary["attacks_definitive"] == 0
        and all(v == 32 for v in summary["attack_families"].values())
    )
    report = {
        "schema": "agnxiv.authority-registry/1",
        "validation_time": NOW.isoformat(),
        "trusted_public_key_pem": TRUSTED_PUBLIC,
        "self_asserted": self_asserted,
        "controls": controls,
        "attacks": attacks,
        "summary": summary,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    raise SystemExit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()
