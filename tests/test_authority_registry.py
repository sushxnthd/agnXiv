from datetime import UTC, datetime, timedelta

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

NOW = datetime(2026, 10, 27, tzinfo=UTC)


def _keys():
    private = Ed25519PrivateKey.from_private_bytes(b"\x07" * 32)
    return private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ), private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def _bundle():
    claim = Claim(id="C1", text="Accuracy is 0.9", metric="accuracy", reported_value=0.9)
    return VerificationBundle(
        verification_authority="auto_planned",
        authority_evidence_sha256="f" * 64,
        claim=claim,
        manuscript=DocumentFingerprint(name="paper.pdf", sha256="d" * 64, size_bytes=20),
        provenance=ProvenanceManifest(files=[], file_count=0, total_bytes=0, tree_digest="a" * 64),
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
            [Observation(value=0.9)],
            VerificationPolicy(kind="absolute", tolerance=0.01),
        ),
    )


def _build():
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
        image_ref="agnxiv-env:test",
        image_id="sha256:" + "c" * 64,
        base_image_id="sha256:" + "e" * 64,
        stdout_sha256="3" * 64,
        stderr_sha256="4" * 64,
    )


def _trusted(item):
    private, public = _keys()
    registry = TrustedAuthorityRegistry(
        keys=[TrustedAuthorityKey(issuer="review-board", key_id="key-1", public_key_pem=public)]
    )
    scope = authority_scope_for_bundle(
        item,
        issuer="review-board",
        key_id="key-1",
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    )
    item.authority_attestations = [sign_authority_scope(scope, private)]
    return registry


def test_strict_gate_rejects_self_asserted_authority():
    gated = gate_hosted_verdict(_bundle(), _build(), require_registry_authority=True)
    assert gated.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert any("registry is not configured" in reason for reason in gated.verdict_gate_reasons)


def test_strict_gate_accepts_exact_registered_signature():
    item = _bundle()
    gated = gate_hosted_verdict(
        item,
        _build(),
        trusted_authority_registry=_trusted(item),
        require_registry_authority=True,
        authority_validation_time=NOW,
    )
    assert gated.record.verdict == Verdict.VERIFIED


def test_registered_signature_cannot_cross_claim():
    item = _bundle()
    registry = _trusted(item)
    item.claim.id = "C2"
    gated = gate_hosted_verdict(
        item,
        _build(),
        trusted_authority_registry=registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
    )
    assert gated.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert any("different scientific object" in reason for reason in gated.verdict_gate_reasons)


def test_future_issued_signature_fails_closed():
    item = _bundle()
    private, public = _keys()
    registry = TrustedAuthorityRegistry(
        keys=[TrustedAuthorityKey(issuer="review-board", key_id="key-1", public_key_pem=public)]
    )
    scope = authority_scope_for_bundle(
        item,
        issuer="review-board",
        key_id="key-1",
        issued_at=NOW + timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    )
    item.authority_attestations = [sign_authority_scope(scope, private)]
    gated = gate_hosted_verdict(
        item,
        _build(),
        trusted_authority_registry=registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
    )
    assert gated.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert any("issued in the future" in reason for reason in gated.verdict_gate_reasons)


def test_two_keys_in_one_trust_domain_do_not_form_independent_quorum():
    item = _bundle()
    private_a, public_a = _keys()
    private_b = Ed25519PrivateKey.from_private_bytes(b"\x08" * 32)
    public_b = private_b.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    registry = TrustedAuthorityRegistry(
        minimum_signatures=2,
        minimum_trust_domains=2,
        keys=[
            TrustedAuthorityKey(
                issuer="board-a",
                key_id="key-1",
                public_key_pem=public_a,
                trust_domain="shared-operator",
            ),
            TrustedAuthorityKey(
                issuer="board-b",
                key_id="key-2",
                public_key_pem=public_b,
                trust_domain="shared-operator",
            ),
        ],
    )
    item.authority_attestations = [
        sign_authority_scope(
            authority_scope_for_bundle(
                item,
                issuer=issuer,
                key_id=key_id,
                issued_at=NOW - timedelta(minutes=1),
                expires_at=NOW + timedelta(hours=1),
            ),
            private,
        )
        for issuer, key_id, private in (
            ("board-a", "key-1", private_a),
            ("board-b", "key-2", private_b.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )),
        )
    ]
    gated = gate_hosted_verdict(
        item,
        _build(),
        trusted_authority_registry=registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
    )
    assert gated.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert any("domain quorum is not met" in reason for reason in gated.verdict_gate_reasons)


def test_two_explicit_trust_domains_form_independent_quorum():
    item = _bundle()
    credentials = []
    registry_keys = []
    for seed, issuer, domain in ((7, "board-a", "operator-a"), (8, "board-b", "operator-b")):
        private = Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32)
        private_pem = private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        registry_keys.append(
            TrustedAuthorityKey(
                issuer=issuer,
                key_id=f"key-{seed}",
                public_key_pem=private.public_key().public_bytes(
                    serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                ).decode(),
                trust_domain=domain,
            )
        )
        credentials.append((issuer, f"key-{seed}", private_pem))
    registry = TrustedAuthorityRegistry(
        minimum_signatures=2,
        minimum_trust_domains=2,
        keys=registry_keys,
    )
    item.authority_attestations = [
        sign_authority_scope(
            authority_scope_for_bundle(
                item,
                issuer=issuer,
                key_id=key_id,
                issued_at=NOW - timedelta(minutes=1),
                expires_at=NOW + timedelta(hours=1),
            ),
            private,
        )
        for issuer, key_id, private in credentials
    ]
    gated = gate_hosted_verdict(
        item,
        _build(),
        trusted_authority_registry=registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
    )
    assert gated.record.verdict == Verdict.VERIFIED


def test_missing_domain_metadata_cannot_satisfy_multi_domain_quorum():
    item = _bundle()
    private, public = _keys()
    registry = TrustedAuthorityRegistry(
        minimum_trust_domains=2,
        keys=[TrustedAuthorityKey(issuer="board", key_id="key", public_key_pem=public)],
    )
    item.authority_attestations = [
        sign_authority_scope(
            authority_scope_for_bundle(
                item,
                issuer="board",
                key_id="key",
                issued_at=NOW - timedelta(minutes=1),
                expires_at=NOW + timedelta(hours=1),
            ),
            private,
        )
    ]
    gated = gate_hosted_verdict(
        item,
        _build(),
        trusted_authority_registry=registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
    )
    assert gated.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert any("lacks an explicit trust domain" in reason for reason in gated.verdict_gate_reasons)
