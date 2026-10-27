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
    schema_version: str = "agnxiv.authority-registry/2"
    registry_epoch: int = Field(default=0, ge=0)
    minimum_signatures: int = Field(default=1, ge=1)
    minimum_trust_domains: int = Field(default=1, ge=1)
    keys: list[TrustedAuthorityKey] = Field(default_factory=list)


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
    if trusted_minimum_registry_epoch is not None and trusted_minimum_registry_epoch < 0:
        failures.append("trusted registry freshness floor is invalid")
    elif trusted_minimum_registry_epoch is not None:
        if registry.registry_epoch < trusted_minimum_registry_epoch:
            failures.append(
                "authority registry epoch is below trusted freshness floor: "
                f"{registry.registry_epoch}/{trusted_minimum_registry_epoch}"
            )
    elif require_registry_freshness:
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
