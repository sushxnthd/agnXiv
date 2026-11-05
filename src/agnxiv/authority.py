from __future__ import annotations

import base64
import binascii
import hashlib
import itertools
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AuthorityScope(BaseModel):
    schema_version: str = "agnxiv.authority-scope/2"
    issuer: str = Field(min_length=1)
    key_id: str = Field(min_length=1)
    manuscript_sha256: str
    repository_tree_sha256: str
    claim_id: str
    metric: str | None = None
    authority_evidence_sha256: str
    authority_registry_sha256: str = Field(default="", min_length=0, max_length=64)
    issued_at: datetime
    expires_at: datetime


class AuthorityAttestation(BaseModel):
    scope: AuthorityScope
    signature_b64: str


class TrustedAuthorityKey(BaseModel):
    issuer: str
    key_id: str
    public_key_pem: str
    trust_domain: str | None = Field(default=None, min_length=1)
    status: Literal["active", "revoked"] = "active"


class TrustedAuthorityRegistry(BaseModel):
    schema_version: str = "agnxiv.authority-registry/3"
    registry_namespace: str = Field(default="default", min_length=1)
    registry_epoch: int = Field(default=0, ge=0)
    minimum_signatures: int = Field(default=1, ge=1)
    minimum_trust_domains: int = Field(default=1, ge=1)
    keys: list[TrustedAuthorityKey] = Field(default_factory=list)


class TrustedRegistryCheckpoint(BaseModel):
    """External monotonic floor bound to one authority-registry namespace."""

    schema_version: str = "agnxiv.authority-registry-checkpoint/1"
    registry_namespace: str = Field(min_length=1)
    minimum_registry_epoch: int = Field(ge=0)


class RegistryCheckpointScope(BaseModel):
    """Canonical freshness statement issued outside the protected registry."""

    schema_version: str = "agnxiv.authority-registry-checkpoint-scope/2"
    issuer: str = Field(min_length=1)
    key_id: str = Field(min_length=1)
    registry_namespace: str = Field(min_length=1)
    minimum_registry_epoch: int = Field(ge=0)
    authority_registry_sha256: str = Field(default="", min_length=0, max_length=64)
    previous_statement_sha256: str = Field(default="", min_length=0, max_length=64)


class SignedRegistryCheckpoint(BaseModel):
    scope: RegistryCheckpointScope
    signature_b64: str


class TrustedRegistryCheckpointKey(BaseModel):
    issuer: str = Field(min_length=1)
    key_id: str = Field(min_length=1)
    public_key_pem: str = Field(min_length=1)
    trust_domain: str | None = Field(default=None, min_length=1)
    status: Literal["active", "revoked"] = "active"


class RegistryCheckpointQuorumPolicy(BaseModel):
    minimum_signatures: int = Field(default=2, ge=1)
    minimum_trust_domains: int = Field(default=2, ge=1)


class RegistryCheckpointConsumerScope(BaseModel):
    """Trusted local identity consuming a committed checkpoint history."""

    schema_version: str = "agnxiv.registry-checkpoint-consumer-scope/1"
    repository: str = Field(min_length=1)
    workflow_ref: str = Field(min_length=1)
    environment: str = Field(min_length=1)


class RegistryCheckpointExecutionScope(BaseModel):
    """Trusted identity of one workflow execution consuming a commitment."""

    schema_version: str = "agnxiv.registry-checkpoint-execution-scope/1"
    workflow_run_id: str = Field(min_length=1)
    workflow_run_attempt: int = Field(ge=1)
    workflow_job_id: str = Field(min_length=1)


class RegistryCheckpointArtifactScope(BaseModel):
    """Canonical scientific object consumed by one workflow execution."""

    schema_version: str = "agnxiv.registry-checkpoint-artifact-scope/1"
    manuscript_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    repository_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    claim_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RegistryCheckpointArtifactDigestProfile(BaseModel):
    """Versioned derivation semantics for every committed artifact digest."""

    schema_version: str = "agnxiv.registry-checkpoint-artifact-digest-profile/1"
    manuscript: Literal["raw-bytes-v1", "normalized-text-v1"]
    repository_tree: Literal["git-tree-v1", "archive-bytes-v1"]
    claim_manifest: Literal["jcs-json-v1", "raw-json-v1"]
    evidence_bundle: Literal["merkle-manifest-v1", "archive-bytes-v1"]


class RegistryCheckpointDigestProducerScope(BaseModel):
    """Measured implementation identity of the artifact-digest producer."""

    schema_version: str = "agnxiv.registry-checkpoint-digest-producer-scope/1"
    producer_id: str = Field(min_length=1)
    implementation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    toolchain_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RegistryCheckpointDigestAttestationScope(BaseModel):
    """Canonical provenance evidence for one measured digest producer."""

    schema_version: str = "agnxiv.registry-checkpoint-digest-attestation-scope/1"
    predicate_type: str = Field(min_length=1)
    provenance_statement_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    attestation_signer_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transparency_inclusion_witness_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SignedRegistryCheckpointDigestAttestation(BaseModel):
    """Ed25519-authenticated digest-producer provenance evidence."""

    scope: RegistryCheckpointDigestAttestationScope
    signature_b64: str


class RegistryCheckpointTransparencyInclusionWitness(BaseModel):
    """Canonical RFC 6962-style inclusion witness for a provenance statement."""

    schema_version: str = "agnxiv.registry-checkpoint-transparency-inclusion/1"
    log_id: str = Field(min_length=1)
    tree_size: int = Field(ge=1)
    leaf_index: int = Field(ge=0)
    root_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    audit_path_sha256: list[str] = Field(max_length=64)


def canonical_authority_registry_payload(registry: TrustedAuthorityRegistry) -> bytes:
    """Return the exact deterministic policy payload interpreted by the gate."""
    return json.dumps(
        registry.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def authority_registry_sha256(registry: TrustedAuthorityRegistry) -> str:
    return hashlib.sha256(canonical_authority_registry_payload(registry)).hexdigest()


def canonical_registry_checkpoint_payload(scope: RegistryCheckpointScope) -> bytes:
    return json.dumps(
        scope.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def registry_checkpoint_statement_sha256(
    registry_namespace: str,
    minimum_registry_epoch: int,
    authority_registry_sha256: str,
) -> str:
    """Digest one quorum statement independently of its signer set."""
    payload = json.dumps(
        {
            "authority_registry_sha256": authority_registry_sha256,
            "minimum_registry_epoch": minimum_registry_epoch,
            "registry_namespace": registry_namespace,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def registry_checkpoint_linked_statement_sha256(
    registry_namespace: str,
    minimum_registry_epoch: int,
    authority_registry_sha256: str,
    previous_statement_sha256: str,
) -> str:
    """Digest one statement and its predecessor commitment, excluding signers."""
    payload = json.dumps(
        {
            "authority_registry_sha256": authority_registry_sha256,
            "minimum_registry_epoch": minimum_registry_epoch,
            "previous_statement_sha256": previous_statement_sha256,
            "registry_namespace": registry_namespace,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def registry_checkpoint_scoped_history_commitment_sha256(
    history_commitment_sha256: str,
    consumer_scope: RegistryCheckpointConsumerScope,
) -> str:
    """Bind one verified recursive history to its trusted local consumer."""
    payload = json.dumps(
        {
            "consumer_scope": consumer_scope.model_dump(mode="json"),
            "history_commitment_sha256": history_commitment_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def registry_checkpoint_execution_scoped_history_commitment_sha256(
    scoped_history_commitment_sha256: str,
    execution_scope: RegistryCheckpointExecutionScope,
) -> str:
    """Bind one consumer-scoped history commitment to one execution."""
    payload = json.dumps(
        {
            "execution_scope": execution_scope.model_dump(mode="json"),
            "scoped_history_commitment_sha256": scoped_history_commitment_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def registry_checkpoint_artifact_scoped_history_commitment_sha256(
    execution_scoped_history_commitment_sha256: str,
    artifact_scope: RegistryCheckpointArtifactScope,
) -> str:
    """Bind one execution-scoped history commitment to one scientific artifact."""
    payload = json.dumps(
        {
            "artifact_scope": artifact_scope.model_dump(mode="json"),
            "execution_scoped_history_commitment_sha256": (
                execution_scoped_history_commitment_sha256
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def registry_checkpoint_digest_profile_scoped_history_commitment_sha256(
    artifact_scoped_history_commitment_sha256: str,
    digest_profile: RegistryCheckpointArtifactDigestProfile,
) -> str:
    """Bind an artifact commitment to explicit digest derivation semantics."""
    payload = json.dumps(
        {
            "artifact_scoped_history_commitment_sha256": (
                artifact_scoped_history_commitment_sha256
            ),
            "digest_profile": digest_profile.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def registry_checkpoint_digest_producer_scoped_history_commitment_sha256(
    digest_profile_scoped_history_commitment_sha256: str,
    producer_scope: RegistryCheckpointDigestProducerScope,
) -> str:
    """Bind digest semantics to one measured producer implementation."""
    payload = json.dumps(
        {
            "digest_profile_scoped_history_commitment_sha256": (
                digest_profile_scoped_history_commitment_sha256
            ),
            "producer_scope": producer_scope.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def registry_checkpoint_digest_attestation_scoped_history_commitment_sha256(
    digest_producer_scoped_history_commitment_sha256: str,
    attestation_scope: RegistryCheckpointDigestAttestationScope,
) -> str:
    """Bind measured producer identity to its exact provenance evidence."""
    payload = json.dumps(
        {
            "attestation_scope": attestation_scope.model_dump(mode="json"),
            "digest_producer_scoped_history_commitment_sha256": (
                digest_producer_scoped_history_commitment_sha256
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_registry_checkpoint_digest_attestation_payload(
    scope: RegistryCheckpointDigestAttestationScope,
) -> bytes:
    return json.dumps(
        scope.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def canonical_registry_checkpoint_transparency_inclusion_payload(
    witness: RegistryCheckpointTransparencyInclusionWitness,
) -> bytes:
    return json.dumps(
        witness.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def registry_checkpoint_transparency_inclusion_witness_sha256(
    witness: RegistryCheckpointTransparencyInclusionWitness,
) -> str:
    return hashlib.sha256(
        canonical_registry_checkpoint_transparency_inclusion_payload(witness)
    ).hexdigest()


def verify_registry_checkpoint_transparency_inclusion(
    provenance_statement_sha256: str,
    witness: RegistryCheckpointTransparencyInclusionWitness,
) -> bool:
    """Verify an RFC 6962-style proof against the witness's committed root."""
    if witness.leaf_index >= witness.tree_size:
        return False
    try:
        value = hashlib.sha256(
            b"\x00" + bytes.fromhex(provenance_statement_sha256)
        ).digest()
        node_index = witness.leaf_index
        last_node = witness.tree_size - 1
        for encoded_sibling in witness.audit_path_sha256:
            if len(encoded_sibling) != 64:
                return False
            sibling = bytes.fromhex(encoded_sibling)
            if node_index & 1 or node_index == last_node:
                if node_index == last_node and not (node_index & 1):
                    while node_index and not (node_index & 1):
                        node_index >>= 1
                        last_node >>= 1
                value = hashlib.sha256(b"\x01" + sibling + value).digest()
            else:
                value = hashlib.sha256(b"\x01" + value + sibling).digest()
            node_index >>= 1
            last_node >>= 1
    except ValueError:
        return False
    return last_node == 0 and value.hex() == witness.root_sha256


def registry_checkpoint_digest_attestation_key_sha256(
    public_key_pem: str | bytes,
) -> str:
    """Return a canonical SubjectPublicKeyInfo fingerprint for an Ed25519 key."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    encoded = public_key_pem.encode() if isinstance(public_key_pem, str) else public_key_pem
    key = serialization.load_pem_public_key(encoded)
    if not isinstance(key, Ed25519PublicKey):
        raise TypeError("digest attestation public key is not Ed25519")
    der = key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(der).hexdigest()


def sign_registry_checkpoint_digest_attestation(
    scope: RegistryCheckpointDigestAttestationScope,
    private_key_pem: bytes,
) -> SignedRegistryCheckpointDigestAttestation:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = serialization.load_pem_private_key(private_key_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("digest attestation private key is not Ed25519")
    signature = key.sign(canonical_registry_checkpoint_digest_attestation_payload(scope))
    return SignedRegistryCheckpointDigestAttestation(
        scope=scope,
        signature_b64=base64.b64encode(signature).decode("ascii"),
    )


def sign_registry_checkpoint(
    scope: RegistryCheckpointScope,
    private_key_pem: bytes,
) -> SignedRegistryCheckpoint:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = serialization.load_pem_private_key(private_key_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("registry checkpoint private key is not Ed25519")
    return SignedRegistryCheckpoint(
        scope=scope,
        signature_b64=base64.b64encode(
            key.sign(canonical_registry_checkpoint_payload(scope))
        ).decode("ascii"),
    )


def canonical_authority_payload(scope: AuthorityScope) -> bytes:
    return json.dumps(
        scope.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sign_authority_scope(scope: AuthorityScope, private_key_pem: bytes) -> AuthorityAttestation:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = serialization.load_pem_private_key(private_key_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("authority private key is not Ed25519")
    return AuthorityAttestation(
        scope=scope,
        signature_b64=base64.b64encode(key.sign(canonical_authority_payload(scope))).decode(
            "ascii"
        ),
    )


def authority_scope_for_bundle(
    bundle: Any,
    *,
    registry: TrustedAuthorityRegistry,
    issuer: str,
    key_id: str,
    issued_at: datetime,
    expires_at: datetime,
) -> AuthorityScope:
    return AuthorityScope(
        issuer=issuer,
        key_id=key_id,
        manuscript_sha256=(bundle.manuscript.sha256 if bundle.manuscript is not None else ""),
        repository_tree_sha256=bundle.provenance.tree_digest,
        claim_id=bundle.claim.id,
        metric=bundle.claim.metric,
        authority_evidence_sha256=bundle.authority_evidence_sha256 or "",
        authority_registry_sha256=authority_registry_sha256(registry),
        issued_at=issued_at,
        expires_at=expires_at,
    )


def authority_registry_blockers(
    bundle: Any,
    registry: TrustedAuthorityRegistry | None,
    *,
    now: datetime | None = None,
    trusted_minimum_registry_epoch: int | None = None,
    require_registry_freshness: bool = False,
    trusted_registry_checkpoint: TrustedRegistryCheckpoint | None = None,
    require_registry_checkpoint_scope: bool = False,
    signed_registry_checkpoint: SignedRegistryCheckpoint | None = None,
    signed_registry_checkpoints: list[SignedRegistryCheckpoint] | None = None,
    observed_registry_checkpoints: list[SignedRegistryCheckpoint] | None = None,
    trusted_registry_checkpoint_keys: list[TrustedRegistryCheckpointKey] | None = None,
    require_authenticated_registry_checkpoint: bool = False,
    registry_checkpoint_quorum: RegistryCheckpointQuorumPolicy | None = None,
    require_registry_checkpoint_quorum: bool = False,
    require_registry_checkpoint_snapshot: bool = False,
    require_registry_checkpoint_history: bool = False,
    require_registry_checkpoint_chain: bool = False,
    require_registry_checkpoint_transitive_chain: bool = False,
    trusted_registry_checkpoint_root_statement_sha256: str | None = None,
    require_registry_checkpoint_root: bool = False,
    trusted_registry_checkpoint_tip_statement_sha256: str | None = None,
    require_registry_checkpoint_tip: bool = False,
    trusted_registry_checkpoint_history_commitment_sha256: str | None = None,
    require_registry_checkpoint_history_commitment: bool = False,
    registry_checkpoint_consumer_scope: RegistryCheckpointConsumerScope | None = None,
    trusted_registry_checkpoint_scoped_history_commitment_sha256: str | None = None,
    require_registry_checkpoint_consumer_scope: bool = False,
    registry_checkpoint_execution_scope: RegistryCheckpointExecutionScope | None = None,
    trusted_registry_checkpoint_execution_scoped_history_commitment_sha256: str | None = None,
    require_registry_checkpoint_execution_scope: bool = False,
    registry_checkpoint_artifact_scope: RegistryCheckpointArtifactScope | None = None,
    trusted_registry_checkpoint_artifact_scoped_history_commitment_sha256: str | None = None,
    require_registry_checkpoint_artifact_scope: bool = False,
    registry_checkpoint_artifact_digest_profile: RegistryCheckpointArtifactDigestProfile | None = None,
    trusted_registry_checkpoint_digest_profile_scoped_history_commitment_sha256: str | None = None,
    require_registry_checkpoint_artifact_digest_profile: bool = False,
    registry_checkpoint_digest_producer_scope: RegistryCheckpointDigestProducerScope | None = None,
    trusted_registry_checkpoint_digest_producer_scoped_history_commitment_sha256: str | None = None,
    require_registry_checkpoint_digest_producer_scope: bool = False,
    registry_checkpoint_digest_attestation_scope: RegistryCheckpointDigestAttestationScope | None = None,
    trusted_registry_checkpoint_digest_attestation_scoped_history_commitment_sha256: str | None = None,
    require_registry_checkpoint_digest_attestation_scope: bool = False,
    signed_registry_checkpoint_digest_attestation: SignedRegistryCheckpointDigestAttestation | None = None,
    trusted_registry_checkpoint_digest_attestation_public_key_pem: str | None = None,
    require_registry_checkpoint_digest_attestation_authentication: bool = False,
    registry_checkpoint_transparency_inclusion_witness: RegistryCheckpointTransparencyInclusionWitness | None = None,
    require_registry_checkpoint_transparency_inclusion: bool = False,
) -> list[str]:
    if registry is None:
        return ["trusted authority registry is not configured"]
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    key_map = {(key.issuer, key.key_id): key for key in registry.keys}
    registry_digest = authority_registry_sha256(registry)
    accepted: set[tuple[str, str]] = set()
    accepted_domains: set[str] = set()
    failures: list[str] = []
    authenticated_checkpoint = None
    signed_many = list(signed_registry_checkpoints or [])
    observed_many = list(observed_registry_checkpoints or [])
    if signed_registry_checkpoint is not None and signed_many:
        failures.append("both singular and quorum registry checkpoints are configured")
    signed_candidates = (
        signed_many
        if signed_many
        else ([signed_registry_checkpoint] if signed_registry_checkpoint is not None else [])
    )
    if trusted_registry_checkpoint is not None and signed_candidates:
        failures.append("both unauthenticated and signed registry checkpoints are configured")
    checkpoint_keys = {
        (key.issuer, key.key_id): key for key in (trusted_registry_checkpoint_keys or [])
    }
    valid_checkpoints: list[tuple[RegistryCheckpointScope, TrustedRegistryCheckpointKey]] = []
    valid_observed: list[tuple[RegistryCheckpointScope, TrustedRegistryCheckpointKey]] = []

    def validate_checkpoints(signed_rows, destination, *, observed=False):
        prefix = "observed " if observed else ""
        for signed_checkpoint in signed_rows:
            checkpoint_scope = signed_checkpoint.scope
            checkpoint_key = checkpoint_keys.get((checkpoint_scope.issuer, checkpoint_scope.key_id))
            if checkpoint_key is None:
                failures.append(
                    f"{prefix}signed registry checkpoint uses an untrusted issuer or key"
                )
            elif checkpoint_key.status != "active":
                failures.append(f"{prefix}signed registry checkpoint uses a revoked key")
            else:
                try:
                    from cryptography.exceptions import InvalidSignature
                    from cryptography.hazmat.primitives import serialization
                    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                        Ed25519PublicKey,
                    )

                    signature = base64.b64decode(signed_checkpoint.signature_b64, validate=True)
                    public_key = serialization.load_pem_public_key(
                        checkpoint_key.public_key_pem.encode()
                    )
                    if not isinstance(public_key, Ed25519PublicKey):
                        failures.append(f"{prefix}trusted registry checkpoint key is not Ed25519")
                    else:
                        public_key.verify(
                            signature,
                            canonical_registry_checkpoint_payload(checkpoint_scope),
                        )
                        destination.append((checkpoint_scope, checkpoint_key))
                except (ValueError, TypeError, binascii.Error):
                    failures.append(
                        f"{prefix}registry checkpoint signature encoding or key is invalid"
                    )
                except InvalidSignature:
                    failures.append(f"{prefix}registry checkpoint signature is invalid")

    validate_checkpoints(signed_candidates, valid_checkpoints)
    validate_checkpoints(observed_many, valid_observed, observed=True)
    quorum = registry_checkpoint_quorum or RegistryCheckpointQuorumPolicy()

    def qualifying_statements(valid_rows):
        groups: dict[
            tuple[str, int, str, str],
            tuple[set[tuple[str, str]], set[str]],
        ] = {}
        for scope, key in valid_rows:
            identities, domains = groups.setdefault(
                (
                    scope.registry_namespace,
                    scope.minimum_registry_epoch,
                    scope.authority_registry_sha256,
                    scope.previous_statement_sha256,
                ),
                (set(), set()),
            )
            identities.add((scope.issuer, scope.key_id))
            if key.trust_domain is not None:
                domains.add(key.trust_domain)
        return [
            statement
            for statement, (identities, domains) in groups.items()
            if len(identities) >= quorum.minimum_signatures
            and len(domains) >= quorum.minimum_trust_domains
        ]

    qualifying_observed = qualifying_statements(valid_observed)
    qualifying_current = []
    if signed_many:
        qualifying = qualifying_statements(valid_checkpoints)
        qualifying_current = qualifying
        statement_digests: dict[tuple[str, int], set[str]] = {}
        for namespace, epoch, digest, _ in qualifying:
            statement_digests.setdefault((namespace, epoch), set()).add(digest)
        equivocating = any(len(digests) > 1 for digests in statement_digests.values())
        namespaces = {namespace for namespace, _, _, _ in qualifying}
        if equivocating:
            failures.append("registry checkpoint quorum equivocates at one namespace and epoch")
        elif len(namespaces) > 1:
            failures.append("registry checkpoint quorum endorses conflicting namespaces")
        elif qualifying:
            namespace = next(iter(namespaces))
            floor = max(
                epoch
                for candidate_namespace, epoch, _, _ in qualifying
                if candidate_namespace == namespace
            )
            authenticated_checkpoint = next(
                scope
                for scope, _ in valid_checkpoints
                if scope.registry_namespace == namespace
                and scope.minimum_registry_epoch == floor
                and (
                    scope.registry_namespace,
                    scope.minimum_registry_epoch,
                    scope.authority_registry_sha256,
                    scope.previous_statement_sha256,
                )
                in qualifying
            )
        else:
            failures.append("registry checkpoint quorum is not satisfied")
    elif valid_checkpoints:
        authenticated_checkpoint = valid_checkpoints[0][0]
    elif require_authenticated_registry_checkpoint:
        failures.append("authenticated registry checkpoint is not configured")
    if require_registry_checkpoint_quorum and not signed_many:
        failures.append("registry checkpoint quorum is not configured")
    if require_registry_checkpoint_history and not observed_many:
        failures.append("persisted registry checkpoint history is not configured")
    history_digests: dict[tuple[str, int], set[str]] = {}
    for namespace, epoch, digest, _ in [
        *qualifying_statements(valid_checkpoints),
        *qualifying_observed,
    ]:
        history_digests.setdefault((namespace, epoch), set()).add(digest)
    if any(len(digests) > 1 for digests in history_digests.values()):
        failures.append(
            "persisted registry checkpoint history equivocates at one namespace and epoch"
        )
    if (
        require_registry_checkpoint_chain
        or require_registry_checkpoint_transitive_chain
        or require_registry_checkpoint_root
        or require_registry_checkpoint_tip
        or require_registry_checkpoint_history_commitment
        or require_registry_checkpoint_consumer_scope
        or require_registry_checkpoint_execution_scope
        or require_registry_checkpoint_artifact_scope
        or require_registry_checkpoint_artifact_digest_profile
    ):
        if not qualifying_current or not qualifying_observed:
            failures.append("registry checkpoint history chain is not configured")
        elif authenticated_checkpoint is not None:
            namespace = authenticated_checkpoint.registry_namespace
            current_epoch = authenticated_checkpoint.minimum_registry_epoch
            current_digest = authenticated_checkpoint.authority_registry_sha256
            historical = [
                statement
                for statement in qualifying_observed
                if statement[0] == namespace
            ]
            if not historical:
                failures.append(
                    "registry checkpoint history chain has no prior quorum in the current namespace"
                )
            else:
                latest_epoch = max(statement[1] for statement in historical)
                latest = {
                    statement[:3]
                    for statement in historical
                    if statement[1] == latest_epoch
                }
                if len(latest) != 1:
                    failures.append(
                        "registry checkpoint history chain has an ambiguous latest statement"
                    )
                elif current_epoch <= latest_epoch:
                    failures.append(
                        "registry checkpoint history chain does not advance the epoch"
                    )
                else:
                    latest_statement = next(iter(latest))
                    expected_link = (
                        registry_checkpoint_linked_statement_sha256(
                            *next(
                                statement
                                for statement in historical
                                if statement[:3] == latest_statement
                            )
                        )
                        if require_registry_checkpoint_history_commitment
                        else registry_checkpoint_statement_sha256(*latest_statement)
                    )
                    links = {
                        statement[3]
                        for statement in qualifying_current
                        if statement[:3] == (namespace, current_epoch, current_digest)
                    }
                    if len(links) != 1:
                        failures.append(
                            "registry checkpoint quorum disagrees on its history-chain link"
                        )
                    else:
                        link = next(iter(links))
                        if len(link) != 64 or any(
                            character not in "0123456789abcdef" for character in link
                        ):
                            failures.append(
                                "registry checkpoint history-chain link is missing or invalid"
                            )
                        elif link != expected_link:
                            failures.append(
                                "registry checkpoint history-chain link does not match the latest retained quorum"
                            )

    if (
        require_registry_checkpoint_transitive_chain
        or require_registry_checkpoint_root
        or require_registry_checkpoint_tip
        or require_registry_checkpoint_history_commitment
        or require_registry_checkpoint_consumer_scope
        or require_registry_checkpoint_execution_scope
        or require_registry_checkpoint_artifact_scope
        or require_registry_checkpoint_artifact_digest_profile
    ) and qualifying_observed:
        if authenticated_checkpoint is None:
            failures.append("transitive registry checkpoint history chain is not configured")
        else:
            namespace = authenticated_checkpoint.registry_namespace
            historical = sorted(
                (statement for statement in qualifying_observed if statement[0] == namespace),
                key=lambda statement: statement[1],
            )
            by_epoch: dict[int, set[tuple[str, int, str, str]]] = {}
            for statement in historical:
                by_epoch.setdefault(statement[1], set()).add(statement)
            if any(len(statements) != 1 for statements in by_epoch.values()):
                failures.append(
                    "transitive registry checkpoint history chain has an ambiguous retained epoch"
                )
            else:
                ordered = [next(iter(by_epoch[epoch])) for epoch in sorted(by_epoch)]
                for predecessor, successor in itertools.pairwise(ordered):
                    if successor[1] <= predecessor[1]:
                        failures.append(
                            "transitive registry checkpoint history chain does not advance the epoch"
                        )
                        break
                    link = successor[3]
                    if len(link) != 64 or any(
                        character not in "0123456789abcdef" for character in link
                    ):
                        failures.append(
                            "transitive registry checkpoint history-chain link is missing or invalid"
                        )
                        break
                    expected_link = (
                        registry_checkpoint_linked_statement_sha256(*predecessor)
                        if require_registry_checkpoint_history_commitment
                        else registry_checkpoint_statement_sha256(*predecessor[:3])
                    )
                    if link != expected_link:
                        failures.append(
                            "transitive registry checkpoint history-chain link does not match the adjacent retained quorum"
                        )
                        break

    if require_registry_checkpoint_root:
        root_pin = trusted_registry_checkpoint_root_statement_sha256 or ""
        if len(root_pin) != 64 or any(
            character not in "0123456789abcdef" for character in root_pin
        ):
            failures.append(
                "trusted registry checkpoint root statement digest is not configured or invalid"
            )
        elif authenticated_checkpoint is None or not qualifying_observed:
            failures.append("trusted registry checkpoint root cannot be matched to history")
        else:
            namespace = authenticated_checkpoint.registry_namespace
            historical = [
                statement
                for statement in qualifying_observed
                if statement[0] == namespace
            ]
            if not historical:
                failures.append(
                    "trusted registry checkpoint root has no history in the current namespace"
                )
            else:
                root_epoch = min(statement[1] for statement in historical)
                roots = {
                    statement[:3]
                    for statement in historical
                    if statement[1] == root_epoch
                }
                if len(roots) != 1:
                    failures.append(
                        "trusted registry checkpoint root has an ambiguous oldest statement"
                    )
                else:
                    supplied_root = registry_checkpoint_statement_sha256(
                        *next(iter(roots))
                    )
                    if supplied_root != root_pin:
                        failures.append(
                            "oldest supplied registry checkpoint does not match the trusted root statement"
                        )

    if require_registry_checkpoint_tip:
        if not require_registry_checkpoint_root:
            failures.append(
                "trusted registry checkpoint tip requires trusted root mode"
            )
        tip_pin = trusted_registry_checkpoint_tip_statement_sha256 or ""
        if len(tip_pin) != 64 or any(
            character not in "0123456789abcdef" for character in tip_pin
        ):
            failures.append(
                "trusted registry checkpoint tip statement digest is not configured or invalid"
            )
        elif authenticated_checkpoint is None:
            failures.append("trusted registry checkpoint tip cannot be matched to current quorum")
        else:
            supplied_tip = registry_checkpoint_statement_sha256(
                authenticated_checkpoint.registry_namespace,
                authenticated_checkpoint.minimum_registry_epoch,
                authenticated_checkpoint.authority_registry_sha256,
            )
            if supplied_tip != tip_pin:
                failures.append(
                    "current registry checkpoint does not match the trusted tip statement"
                )

    if require_registry_checkpoint_history_commitment:
        if not (
            require_registry_checkpoint_transitive_chain
            and require_registry_checkpoint_root
            and require_registry_checkpoint_tip
        ):
            failures.append(
                "trusted registry checkpoint history commitment requires transitive root-and-tip mode"
            )
        commitment = trusted_registry_checkpoint_history_commitment_sha256 or ""
        if len(commitment) != 64 or any(
            character not in "0123456789abcdef" for character in commitment
        ):
            failures.append(
                "trusted registry checkpoint history commitment is not configured or invalid"
            )
        elif authenticated_checkpoint is None or not qualifying_observed:
            failures.append(
                "trusted registry checkpoint history commitment cannot be matched to history"
            )
        else:
            namespace = authenticated_checkpoint.registry_namespace
            historical = sorted(
                (statement for statement in qualifying_observed if statement[0] == namespace),
                key=lambda statement: statement[1],
            )
            by_epoch: dict[int, set[tuple[str, int, str, str]]] = {}
            for statement in historical:
                by_epoch.setdefault(statement[1], set()).add(statement)
            current_statements = {
                statement
                for statement in qualifying_current
                if statement[:3]
                == (
                    namespace,
                    authenticated_checkpoint.minimum_registry_epoch,
                    authenticated_checkpoint.authority_registry_sha256,
                )
            }
            if any(len(statements) != 1 for statements in by_epoch.values()) or len(
                current_statements
            ) != 1:
                failures.append(
                    "recursive registry checkpoint history commitment is ambiguous"
                )
            else:
                ordered = [next(iter(by_epoch[epoch])) for epoch in sorted(by_epoch)]
                ordered.append(next(iter(current_statements)))
                for predecessor, successor in itertools.pairwise(ordered):
                    expected_link = registry_checkpoint_linked_statement_sha256(
                        *predecessor
                    )
                    if successor[3] != expected_link:
                        failures.append(
                            "recursive registry checkpoint history link does not match the adjacent committed quorum"
                        )
                        break
                supplied_commitment = registry_checkpoint_linked_statement_sha256(
                    *ordered[-1]
                )
                if supplied_commitment != commitment:
                    failures.append(
                        "current registry checkpoint history does not match the trusted recursive commitment"
                    )

    if require_registry_checkpoint_consumer_scope:
        if not require_registry_checkpoint_history_commitment:
            failures.append(
                "consumer-scoped registry checkpoint commitment requires recursive history-commitment mode"
            )
        if registry_checkpoint_consumer_scope is None:
            failures.append("registry checkpoint consumer scope is not configured")
        scoped_commitment = (
            trusted_registry_checkpoint_scoped_history_commitment_sha256 or ""
        )
        if len(scoped_commitment) != 64 or any(
            character not in "0123456789abcdef" for character in scoped_commitment
        ):
            failures.append(
                "trusted consumer-scoped registry checkpoint commitment is not configured or invalid"
            )
        elif registry_checkpoint_consumer_scope is not None:
            history_commitment = (
                trusted_registry_checkpoint_history_commitment_sha256 or ""
            )
            supplied_scoped = registry_checkpoint_scoped_history_commitment_sha256(
                history_commitment,
                registry_checkpoint_consumer_scope,
            )
            if supplied_scoped != scoped_commitment:
                failures.append(
                    "registry checkpoint history commitment is bound to a different consumer scope"
                )

    if require_registry_checkpoint_execution_scope:
        if not require_registry_checkpoint_consumer_scope:
            failures.append(
                "execution-scoped registry checkpoint commitment requires consumer-scope mode"
            )
        if registry_checkpoint_execution_scope is None:
            failures.append("registry checkpoint execution scope is not configured")
        execution_commitment = (
            trusted_registry_checkpoint_execution_scoped_history_commitment_sha256 or ""
        )
        if len(execution_commitment) != 64 or any(
            character not in "0123456789abcdef" for character in execution_commitment
        ):
            failures.append(
                "trusted execution-scoped registry checkpoint commitment is not configured or invalid"
            )
        elif registry_checkpoint_execution_scope is not None:
            scoped_commitment = (
                trusted_registry_checkpoint_scoped_history_commitment_sha256 or ""
            )
            supplied_execution = (
                registry_checkpoint_execution_scoped_history_commitment_sha256(
                    scoped_commitment,
                    registry_checkpoint_execution_scope,
                )
            )
            if supplied_execution != execution_commitment:
                failures.append(
                    "registry checkpoint history commitment is bound to a different execution scope"
                )

    if require_registry_checkpoint_artifact_scope:
        if not require_registry_checkpoint_execution_scope:
            failures.append(
                "artifact-scoped registry checkpoint commitment requires execution-scope mode"
            )
        if registry_checkpoint_artifact_scope is None:
            failures.append("registry checkpoint artifact scope is not configured")
        artifact_commitment = (
            trusted_registry_checkpoint_artifact_scoped_history_commitment_sha256 or ""
        )
        if len(artifact_commitment) != 64 or any(
            character not in "0123456789abcdef" for character in artifact_commitment
        ):
            failures.append(
                "trusted artifact-scoped registry checkpoint commitment is not configured or invalid"
            )
        elif registry_checkpoint_artifact_scope is not None:
            execution_commitment = (
                trusted_registry_checkpoint_execution_scoped_history_commitment_sha256
                or ""
            )
            supplied_artifact = (
                registry_checkpoint_artifact_scoped_history_commitment_sha256(
                    execution_commitment,
                    registry_checkpoint_artifact_scope,
                )
            )
            if supplied_artifact != artifact_commitment:
                failures.append(
                    "registry checkpoint history commitment is bound to a different artifact scope"
                )

    if require_registry_checkpoint_artifact_digest_profile:
        if not require_registry_checkpoint_artifact_scope:
            failures.append(
                "artifact digest-profile commitment requires artifact-scope mode"
            )
        if registry_checkpoint_artifact_digest_profile is None:
            failures.append("registry checkpoint artifact digest profile is not configured")
        profile_commitment = (
            trusted_registry_checkpoint_digest_profile_scoped_history_commitment_sha256
            or ""
        )
        if len(profile_commitment) != 64 or any(
            character not in "0123456789abcdef" for character in profile_commitment
        ):
            failures.append(
                "trusted digest-profile-scoped registry checkpoint commitment is not configured or invalid"
            )
        elif registry_checkpoint_artifact_digest_profile is not None:
            artifact_commitment = (
                trusted_registry_checkpoint_artifact_scoped_history_commitment_sha256
                or ""
            )
            supplied_profile = (
                registry_checkpoint_digest_profile_scoped_history_commitment_sha256(
                    artifact_commitment,
                    registry_checkpoint_artifact_digest_profile,
                )
            )
            if supplied_profile != profile_commitment:
                failures.append(
                    "registry checkpoint history commitment is bound to a different artifact digest profile"
                )

    if require_registry_checkpoint_digest_producer_scope:
        if not require_registry_checkpoint_artifact_digest_profile:
            failures.append(
                "digest-producer commitment requires artifact digest-profile mode"
            )
        if registry_checkpoint_digest_producer_scope is None:
            failures.append("registry checkpoint digest producer scope is not configured")
        producer_commitment = (
            trusted_registry_checkpoint_digest_producer_scoped_history_commitment_sha256
            or ""
        )
        if len(producer_commitment) != 64 or any(
            character not in "0123456789abcdef" for character in producer_commitment
        ):
            failures.append(
                "trusted digest-producer-scoped registry checkpoint commitment is not configured or invalid"
            )
        elif registry_checkpoint_digest_producer_scope is not None:
            profile_commitment = (
                trusted_registry_checkpoint_digest_profile_scoped_history_commitment_sha256
                or ""
            )
            supplied_producer = (
                registry_checkpoint_digest_producer_scoped_history_commitment_sha256(
                    profile_commitment,
                    registry_checkpoint_digest_producer_scope,
                )
            )
            if supplied_producer != producer_commitment:
                failures.append(
                    "registry checkpoint history commitment is bound to a different digest producer"
                )

    if require_registry_checkpoint_digest_attestation_scope:
        if not require_registry_checkpoint_digest_producer_scope:
            failures.append(
                "digest-attestation commitment requires digest-producer mode"
            )
        if registry_checkpoint_digest_attestation_scope is None:
            failures.append("registry checkpoint digest attestation scope is not configured")
        attestation_commitment = (
            trusted_registry_checkpoint_digest_attestation_scoped_history_commitment_sha256
            or ""
        )
        if len(attestation_commitment) != 64 or any(
            character not in "0123456789abcdef" for character in attestation_commitment
        ):
            failures.append(
                "trusted digest-attestation-scoped registry checkpoint commitment is not configured or invalid"
            )
        elif registry_checkpoint_digest_attestation_scope is not None:
            producer_commitment = (
                trusted_registry_checkpoint_digest_producer_scoped_history_commitment_sha256
                or ""
            )
            supplied_attestation = (
                registry_checkpoint_digest_attestation_scoped_history_commitment_sha256(
                    producer_commitment,
                    registry_checkpoint_digest_attestation_scope,
                )
            )
            if supplied_attestation != attestation_commitment:
                failures.append(
                    "registry checkpoint history commitment is bound to different digest-producer attestation evidence"
                )

    if require_registry_checkpoint_digest_attestation_authentication:
        if not require_registry_checkpoint_digest_attestation_scope:
            failures.append(
                "digest-attestation authentication requires digest-attestation scope mode"
            )
        if signed_registry_checkpoint_digest_attestation is None:
            failures.append("signed registry checkpoint digest attestation is not configured")
        if not trusted_registry_checkpoint_digest_attestation_public_key_pem:
            failures.append("trusted registry checkpoint digest attestation key is not configured")
        elif signed_registry_checkpoint_digest_attestation is not None:
            signed_attestation = signed_registry_checkpoint_digest_attestation
            if signed_attestation.scope != registry_checkpoint_digest_attestation_scope:
                failures.append(
                    "signed registry checkpoint digest attestation scope does not match configured scope"
                )
            try:
                from cryptography.exceptions import InvalidSignature
                from cryptography.hazmat.primitives import serialization
                from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                    Ed25519PublicKey,
                )

                public_key = serialization.load_pem_public_key(
                    trusted_registry_checkpoint_digest_attestation_public_key_pem.encode()
                )
                if not isinstance(public_key, Ed25519PublicKey):
                    failures.append(
                        "trusted registry checkpoint digest attestation key is not Ed25519"
                    )
                else:
                    configured_scope = registry_checkpoint_digest_attestation_scope
                    fingerprint = registry_checkpoint_digest_attestation_key_sha256(
                        trusted_registry_checkpoint_digest_attestation_public_key_pem
                    )
                    if (
                        configured_scope is None
                        or fingerprint != configured_scope.attestation_signer_key_sha256
                    ):
                        failures.append(
                            "trusted registry checkpoint digest attestation key fingerprint does not match scope"
                        )
                    signature = base64.b64decode(
                        signed_attestation.signature_b64, validate=True
                    )
                    public_key.verify(
                        signature,
                        canonical_registry_checkpoint_digest_attestation_payload(
                            signed_attestation.scope
                        ),
                    )
            except (binascii.Error, ValueError, TypeError, InvalidSignature):
                failures.append("registry checkpoint digest attestation signature is invalid")

    if require_registry_checkpoint_transparency_inclusion:
        if not require_registry_checkpoint_digest_attestation_authentication:
            failures.append(
                "transparency inclusion requires digest-attestation authentication mode"
            )
        witness = registry_checkpoint_transparency_inclusion_witness
        if witness is None:
            failures.append("registry checkpoint transparency inclusion witness is not configured")
        elif registry_checkpoint_digest_attestation_scope is None:
            failures.append(
                "transparency inclusion requires a configured digest-attestation scope"
            )
        else:
            witness_digest = registry_checkpoint_transparency_inclusion_witness_sha256(
                witness
            )
            if (
                witness_digest
                != registry_checkpoint_digest_attestation_scope.transparency_inclusion_witness_sha256
            ):
                failures.append(
                    "transparency inclusion witness does not match digest-attestation scope"
                )
            elif not verify_registry_checkpoint_transparency_inclusion(
                registry_checkpoint_digest_attestation_scope.provenance_statement_sha256,
                witness,
            ):
                failures.append(
                    "registry checkpoint transparency inclusion proof is invalid"
                )

    effective_checkpoint = authenticated_checkpoint or trusted_registry_checkpoint
    if effective_checkpoint is not None:
        if effective_checkpoint.registry_namespace != registry.registry_namespace:
            failures.append(
                "trusted registry checkpoint namespace does not match authority registry: "
                f"{effective_checkpoint.registry_namespace}/"
                f"{registry.registry_namespace}"
            )
        elif registry.registry_epoch < effective_checkpoint.minimum_registry_epoch:
            failures.append(
                "authority registry epoch is below scoped trusted checkpoint: "
                f"{registry.registry_epoch}/"
                f"{effective_checkpoint.minimum_registry_epoch}"
            )
        if require_registry_checkpoint_snapshot:
            checkpoint_digest = getattr(effective_checkpoint, "authority_registry_sha256", "")
            if len(checkpoint_digest) != 64 or any(
                character not in "0123456789abcdef" for character in checkpoint_digest
            ):
                failures.append(
                    "registry checkpoint does not bind a valid authority registry digest"
                )
            elif checkpoint_digest != registry_digest:
                failures.append(
                    "registry checkpoint authority registry digest does not match supplied snapshot"
                )
    elif require_registry_checkpoint_scope and not signed_candidates:
        failures.append("scoped trusted registry checkpoint is not configured")
    if trusted_minimum_registry_epoch is not None and trusted_minimum_registry_epoch < 0:
        failures.append("trusted registry freshness floor is invalid")
    elif trusted_minimum_registry_epoch is not None:
        if registry.registry_epoch < trusted_minimum_registry_epoch:
            failures.append(
                "authority registry epoch is below trusted freshness floor: "
                f"{registry.registry_epoch}/{trusted_minimum_registry_epoch}"
            )
    elif require_registry_freshness and effective_checkpoint is None:
        failures.append("trusted registry freshness floor is not configured")
    for attestation in bundle.authority_attestations:
        scope = attestation.scope
        identity = (scope.issuer, scope.key_id)
        key = key_map.get(identity)
        if key is None:
            failures.append("authority attestation uses an unregistered issuer or key")
            continue
        if key.status != "active":
            failures.append("authority attestation uses a revoked registry key")
            continue
        if scope.authority_registry_sha256 != registry_digest:
            failures.append("authority attestation is bound to a different registry snapshot")
            continue
        expected = authority_scope_for_bundle(
            bundle,
            registry=registry,
            issuer=scope.issuer,
            key_id=scope.key_id,
            issued_at=scope.issued_at,
            expires_at=scope.expires_at,
        )
        if scope != expected:
            failures.append("authority attestation is bound to a different scientific object")
            continue
        if scope.issued_at.tzinfo is None or scope.expires_at.tzinfo is None:
            failures.append("authority attestation validity window lacks a timezone")
            continue
        if scope.issued_at > current:
            failures.append("authority attestation was issued in the future")
            continue
        if scope.expires_at <= current or scope.expires_at <= scope.issued_at:
            failures.append("authority attestation is expired or has an invalid validity window")
            continue
        try:
            signature = base64.b64decode(attestation.signature_b64, validate=True)
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

            public_key = serialization.load_pem_public_key(key.public_key_pem.encode())
            if not isinstance(public_key, Ed25519PublicKey):
                failures.append("registered authority key is not Ed25519")
                continue
            public_key.verify(signature, canonical_authority_payload(scope))
        except (ValueError, TypeError, binascii.Error):
            failures.append("authority attestation signature encoding or key is invalid")
            continue
        except InvalidSignature:
            failures.append("authority attestation signature is invalid")
            continue
        accepted.add(identity)
        if key.trust_domain is not None:
            accepted_domains.add(key.trust_domain)
        elif registry.minimum_trust_domains == 1:
            # Preserve the version-1 single-authority contract. Explicit domain
            # metadata is mandatory as soon as independent domains are claimed.
            accepted_domains.add(key.issuer)
        else:
            failures.append("registered authority key lacks an explicit trust domain")
    if len(accepted) < registry.minimum_signatures:
        failures.append(
            "trusted authority quorum is not met: "
            f"{len(accepted)}/{registry.minimum_signatures} valid signatures"
        )
    if len(accepted_domains) < registry.minimum_trust_domains:
        failures.append(
            "trusted authority domain quorum is not met: "
            f"{len(accepted_domains)}/{registry.minimum_trust_domains} valid trust domains"
        )
    return failures
