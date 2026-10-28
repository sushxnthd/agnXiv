from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from agnxiv.authority import (
    RegistryCheckpointQuorumPolicy,
    RegistryCheckpointScope,
    TrustedAuthorityKey,
    TrustedAuthorityRegistry,
    TrustedRegistryCheckpoint,
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


def _checkpoint_keys():
    private = Ed25519PrivateKey.from_private_bytes(b"\x09" * 32)
    return private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ), private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def _checkpoint_credential(seed):
    private = Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32)
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
        registry=registry,
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
        registry=registry,
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
                registry=registry,
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
                registry=registry,
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
                registry=registry,
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


def test_registry_digest_is_deterministic_and_policy_complete():
    _, public = _keys()
    registry = TrustedAuthorityRegistry(
        minimum_signatures=2,
        minimum_trust_domains=2,
        keys=[
            TrustedAuthorityKey(
                issuer="board",
                key_id="key",
                public_key_pem=public,
                trust_domain="operator-a",
            )
        ],
    )
    assert authority_registry_sha256(registry) == authority_registry_sha256(
        registry.model_copy(deep=True)
    )
    remapped = registry.model_copy(deep=True)
    remapped.keys[0].trust_domain = "operator-b"
    assert authority_registry_sha256(registry) != authority_registry_sha256(remapped)
    revoked = registry.model_copy(deep=True)
    revoked.keys[0].status = "revoked"
    assert authority_registry_sha256(registry) != authority_registry_sha256(revoked)
    advanced = registry.model_copy(update={"registry_epoch": 1})
    assert authority_registry_sha256(registry) != authority_registry_sha256(advanced)
    namespaced = registry.model_copy(update={"registry_namespace": "production"})
    assert authority_registry_sha256(registry) != authority_registry_sha256(namespaced)


def test_exact_old_snapshot_requires_independent_freshness_floor():
    item = _bundle()
    private, public = _keys()
    old_registry = TrustedAuthorityRegistry(
        registry_epoch=40,
        keys=[TrustedAuthorityKey(issuer="board", key_id="key", public_key_pem=public)],
    )
    scope = authority_scope_for_bundle(
        item,
        registry=old_registry,
        issuer="board",
        key_id="key",
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    )
    item.authority_attestations = [sign_authority_scope(scope, private)]

    replayed = gate_hosted_verdict(
        item,
        _build(),
        trusted_authority_registry=old_registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
    )
    assert replayed.record.verdict == Verdict.VERIFIED

    fresh = gate_hosted_verdict(
        item,
        _build(),
        trusted_authority_registry=old_registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
        trusted_minimum_registry_epoch=41,
        require_registry_freshness=True,
    )
    assert fresh.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert any("below trusted freshness floor" in reason for reason in fresh.verdict_gate_reasons)


def test_current_registry_epoch_satisfies_freshness_floor():
    item = _bundle()
    private, public = _keys()
    registry = TrustedAuthorityRegistry(
        registry_epoch=41,
        keys=[TrustedAuthorityKey(issuer="board", key_id="key", public_key_pem=public)],
    )
    scope = authority_scope_for_bundle(
        item,
        registry=registry,
        issuer="board",
        key_id="key",
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    )
    item.authority_attestations = [sign_authority_scope(scope, private)]
    gated = gate_hosted_verdict(
        item,
        _build(),
        trusted_authority_registry=registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
        trusted_minimum_registry_epoch=41,
        require_registry_freshness=True,
    )
    assert gated.record.verdict == Verdict.VERIFIED


def test_required_registry_freshness_without_floor_fails_closed():
    item = _bundle()
    registry = _trusted(item)
    gated = gate_hosted_verdict(
        item,
        _build(),
        trusted_authority_registry=registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
        require_registry_freshness=True,
    )
    assert gated.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert any("freshness floor is not configured" in reason for reason in gated.verdict_gate_reasons)


def test_scoped_checkpoint_rejects_foreign_registry_namespace():
    item = _bundle()
    private, public = _keys()
    registry = TrustedAuthorityRegistry(
        registry_namespace="production-release",
        registry_epoch=41,
        keys=[TrustedAuthorityKey(issuer="board", key_id="key", public_key_pem=public)],
    )
    scope = authority_scope_for_bundle(
        item,
        registry=registry,
        issuer="board",
        key_id="key",
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    )
    item.authority_attestations = [sign_authority_scope(scope, private)]

    unscoped = gate_hosted_verdict(
        item,
        _build(),
        trusted_authority_registry=registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
        trusted_minimum_registry_epoch=41,
        require_registry_freshness=True,
    )
    scoped = gate_hosted_verdict(
        item,
        _build(),
        trusted_authority_registry=registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
        trusted_registry_checkpoint=TrustedRegistryCheckpoint(
            registry_namespace="staging-release",
            minimum_registry_epoch=41,
        ),
        require_registry_checkpoint_scope=True,
    )

    assert unscoped.record.verdict == Verdict.VERIFIED
    assert scoped.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert any("namespace does not match" in reason for reason in scoped.verdict_gate_reasons)


def test_matching_scoped_checkpoint_preserves_decisive_verdict():
    item = _bundle()
    registry = _trusted(item).model_copy(
        update={"registry_namespace": "external-audit", "registry_epoch": 9}
    )
    # Re-sign because namespace and epoch are part of the canonical registry digest.
    private, _ = _keys()
    scope = authority_scope_for_bundle(
        item,
        registry=registry,
        issuer="review-board",
        key_id="key-1",
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    )
    item.authority_attestations = [sign_authority_scope(scope, private)]
    gated = gate_hosted_verdict(
        item,
        _build(),
        trusted_authority_registry=registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
        trusted_registry_checkpoint=TrustedRegistryCheckpoint(
            registry_namespace="external-audit",
            minimum_registry_epoch=9,
        ),
        require_registry_checkpoint_scope=True,
    )

    assert gated.record.verdict == Verdict.VERIFIED


def test_required_scoped_checkpoint_without_checkpoint_fails_closed():
    item = _bundle()
    gated = gate_hosted_verdict(
        item,
        _build(),
        trusted_authority_registry=_trusted(item),
        require_registry_authority=True,
        authority_validation_time=NOW,
        require_registry_checkpoint_scope=True,
    )

    assert gated.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert any("scoped trusted registry checkpoint is not configured" in reason for reason in gated.verdict_gate_reasons)


@pytest.mark.parametrize(
    "payload",
    (
        {"registry_namespace": "", "minimum_registry_epoch": 1},
        {"registry_namespace": "production", "minimum_registry_epoch": -1},
    ),
)
def test_malformed_scoped_checkpoint_is_invalid(payload):
    with pytest.raises(ValidationError):
        TrustedRegistryCheckpoint(**payload)


def _authenticated_checkpoint_case():
    item = _bundle()
    registry = _trusted(item).model_copy(
        update={"registry_namespace": "production-release", "registry_epoch": 41}
    )
    authority_private, _ = _keys()
    item.authority_attestations = [
        sign_authority_scope(
            authority_scope_for_bundle(
                item,
                registry=registry,
                issuer="review-board",
                key_id="key-1",
                issued_at=NOW - timedelta(minutes=1),
                expires_at=NOW + timedelta(hours=1),
            ),
            authority_private,
        )
    ]
    checkpoint_private, checkpoint_public = _checkpoint_keys()
    scope = RegistryCheckpointScope(
        issuer="checkpoint-board",
        key_id="checkpoint-1",
        registry_namespace="production-release",
        minimum_registry_epoch=41,
    )
    signed = sign_registry_checkpoint(scope, checkpoint_private)
    keys = [
        TrustedRegistryCheckpointKey(
            issuer="checkpoint-board",
            key_id="checkpoint-1",
            public_key_pem=checkpoint_public,
        )
    ]
    return item, registry, signed, keys


def test_authenticated_checkpoint_preserves_decisive_verdict():
    item, registry, checkpoint, keys = _authenticated_checkpoint_case()
    gated = gate_hosted_verdict(
        item,
        _build(),
        trusted_authority_registry=registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
        signed_registry_checkpoint=checkpoint,
        trusted_registry_checkpoint_keys=keys,
        require_authenticated_registry_checkpoint=True,
    )
    assert gated.record.verdict == Verdict.VERIFIED


def test_checkpoint_signature_cannot_be_reinterpreted_at_lower_epoch():
    item, registry, checkpoint, keys = _authenticated_checkpoint_case()
    forged = checkpoint.model_copy(deep=True)
    forged.scope.minimum_registry_epoch = 1
    gated = gate_hosted_verdict(
        item,
        _build(),
        trusted_authority_registry=registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
        signed_registry_checkpoint=forged,
        trusted_registry_checkpoint_keys=keys,
        require_authenticated_registry_checkpoint=True,
    )
    assert gated.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert any("checkpoint signature is invalid" in reason for reason in gated.verdict_gate_reasons)


def test_authenticated_checkpoint_rejects_untrusted_or_revoked_key():
    item, registry, checkpoint, keys = _authenticated_checkpoint_case()
    for supplied_keys, expected in (
        ([], "untrusted issuer or key"),
        ([keys[0].model_copy(update={"status": "revoked"})], "revoked key"),
    ):
        gated = gate_hosted_verdict(
            item.model_copy(deep=True),
            _build(),
            trusted_authority_registry=registry,
            require_registry_authority=True,
            authority_validation_time=NOW,
            signed_registry_checkpoint=checkpoint,
            trusted_registry_checkpoint_keys=supplied_keys,
            require_authenticated_registry_checkpoint=True,
        )
        assert gated.record.verdict == Verdict.UNABLE_TO_VERIFY
        assert any(expected in reason for reason in gated.verdict_gate_reasons)


def test_raw_checkpoint_cannot_satisfy_authenticated_mode():
    item, registry, _, _ = _authenticated_checkpoint_case()
    gated = gate_hosted_verdict(
        item,
        _build(),
        trusted_authority_registry=registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
        trusted_registry_checkpoint=TrustedRegistryCheckpoint(
            registry_namespace="production-release",
            minimum_registry_epoch=41,
        ),
        require_authenticated_registry_checkpoint=True,
    )
    assert gated.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert any("authenticated registry checkpoint is not configured" in reason for reason in gated.verdict_gate_reasons)


def _quorum_gate(checkpoints, keys):
    item, registry, _, _ = _authenticated_checkpoint_case()
    return gate_hosted_verdict(
        item,
        _build(),
        trusted_authority_registry=registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
        signed_registry_checkpoints=checkpoints,
        trusted_registry_checkpoint_keys=keys,
        registry_checkpoint_quorum=RegistryCheckpointQuorumPolicy(
            minimum_signatures=2,
            minimum_trust_domains=2,
        ),
        require_registry_checkpoint_quorum=True,
    )


def _quorum_material(floors=(41, 41), domains=("operator-a", "operator-b")):
    checkpoints = []
    keys = []
    for index, (floor, domain) in enumerate(zip(floors, domains), start=1):
        private, public = _checkpoint_credential(20 + index)
        scope = RegistryCheckpointScope(
            issuer=f"checkpoint-board-{index}",
            key_id=f"checkpoint-{index}",
            registry_namespace="production-release",
            minimum_registry_epoch=floor,
        )
        checkpoints.append(sign_registry_checkpoint(scope, private))
        keys.append(
            TrustedRegistryCheckpointKey(
                issuer=scope.issuer,
                key_id=scope.key_id,
                public_key_pem=public,
                trust_domain=domain,
            )
        )
    return checkpoints, keys


def test_two_domain_checkpoint_quorum_preserves_decisive_verdict():
    checkpoints, keys = _quorum_material()
    assert _quorum_gate(checkpoints, keys).record.verdict == Verdict.VERIFIED


def test_duplicate_checkpoint_identity_does_not_form_quorum():
    checkpoints, keys = _quorum_material()
    gated = _quorum_gate([checkpoints[0], checkpoints[0]], keys)
    assert gated.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert any("quorum is not satisfied" in reason for reason in gated.verdict_gate_reasons)


def test_same_domain_checkpoint_keys_do_not_form_quorum():
    checkpoints, keys = _quorum_material(domains=("operator-a", "operator-a"))
    gated = _quorum_gate(checkpoints, keys)
    assert gated.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert any("quorum is not satisfied" in reason for reason in gated.verdict_gate_reasons)


def test_disagreeing_checkpoint_floors_do_not_form_quorum():
    checkpoints, keys = _quorum_material(floors=(1, 41))
    gated = _quorum_gate(checkpoints, keys)
    assert gated.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert any("quorum is not satisfied" in reason for reason in gated.verdict_gate_reasons)


def test_revoked_checkpoint_key_does_not_form_quorum():
    checkpoints, keys = _quorum_material()
    keys[1] = keys[1].model_copy(update={"status": "revoked"})
    gated = _quorum_gate(checkpoints, keys)
    assert gated.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert any("revoked key" in reason for reason in gated.verdict_gate_reasons)


def test_negative_registry_epoch_is_invalid():
    with pytest.raises(ValidationError):
        TrustedAuthorityRegistry(registry_epoch=-1)


def test_signature_cannot_be_reinterpreted_under_remapped_registry():
    item = _bundle()
    private, public = _keys()
    signing_registry = TrustedAuthorityRegistry(
        keys=[
            TrustedAuthorityKey(
                issuer="board",
                key_id="key",
                public_key_pem=public,
                trust_domain="operator-a",
            )
        ]
    )
    verification_registry = signing_registry.model_copy(deep=True)
    verification_registry.keys[0].trust_domain = "operator-b"
    scope = authority_scope_for_bundle(
        item,
        registry=signing_registry,
        issuer="board",
        key_id="key",
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    )
    item.authority_attestations = [sign_authority_scope(scope, private)]
    gated = gate_hosted_verdict(
        item,
        _build(),
        trusted_authority_registry=verification_registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
    )
    assert gated.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert any("different registry snapshot" in reason for reason in gated.verdict_gate_reasons)


def test_missing_registry_digest_fails_closed():
    item = _bundle()
    private, public = _keys()
    registry = TrustedAuthorityRegistry(
        keys=[TrustedAuthorityKey(issuer="board", key_id="key", public_key_pem=public)]
    )
    scope = authority_scope_for_bundle(
        item,
        registry=registry,
        issuer="board",
        key_id="key",
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    ).model_copy(update={"authority_registry_sha256": ""})
    item.authority_attestations = [sign_authority_scope(scope, private)]
    gated = gate_hosted_verdict(
        item,
        _build(),
        trusted_authority_registry=registry,
        require_registry_authority=True,
        authority_validation_time=NOW,
    )
    assert gated.record.verdict == Verdict.UNABLE_TO_VERIFY
    assert any("different registry snapshot" in reason for reason in gated.verdict_gate_reasons)
