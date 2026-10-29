from __future__ import annotations

import base64
import binascii
import hashlib
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

    schema_version: str = "agnxiv.authority-registry-checkpoint-scope/1"
    issuer: str = Field(min_length=1)
    key_id: str = Field(min_length=1)
    registry_namespace: str = Field(min_length=1)
    minimum_registry_epoch: int = Field(ge=0)
    authority_registry_sha256: str = Field(default="", min_length=0, max_length=64)


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
            tuple[str, int, str],
            tuple[set[tuple[str, str]], set[str]],
        ] = {}
        for scope, key in valid_rows:
            identities, domains = groups.setdefault(
                (
                    scope.registry_namespace,
                    scope.minimum_registry_epoch,
                    scope.authority_registry_sha256,
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
    if signed_many:
        qualifying = qualifying_statements(valid_checkpoints)
        statement_digests: dict[tuple[str, int], set[str]] = {}
        for namespace, epoch, digest in qualifying:
            statement_digests.setdefault((namespace, epoch), set()).add(digest)
        equivocating = any(len(digests) > 1 for digests in statement_digests.values())
        namespaces = {namespace for namespace, _, _ in qualifying}
        if equivocating:
            failures.append("registry checkpoint quorum equivocates at one namespace and epoch")
        elif len(namespaces) > 1:
            failures.append("registry checkpoint quorum endorses conflicting namespaces")
        elif qualifying:
            namespace = next(iter(namespaces))
            floor = max(
                epoch
                for candidate_namespace, epoch, _ in qualifying
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
    for namespace, epoch, digest in [
        *qualifying_statements(valid_checkpoints),
        *qualifying_observed,
    ]:
        history_digests.setdefault((namespace, epoch), set()).add(digest)
    if any(len(digests) > 1 for digests in history_digests.values()):
        failures.append(
            "persisted registry checkpoint history equivocates at one namespace and epoch"
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
