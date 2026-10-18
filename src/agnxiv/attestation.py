from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class VerificationAttestation(BaseModel):
    schema_version: str = "agnxiv.attestation/0.1"
    verifier: str = "AgnXiv"
    bundle_sha256: str
    repository_tree_sha256: str
    claim_id: str
    verdict: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def canonical_json_sha256(value: Any) -> str:
    """Hash a JSON-compatible value using a deterministic serialization."""
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def attest_bundle(bundle: Any) -> VerificationAttestation:
    """Create a content-bound attestation for a VerificationBundle-like object."""
    payload = bundle.model_dump(mode="json")
    bundle_digest = canonical_json_sha256(payload)
    return VerificationAttestation(
        bundle_sha256=bundle_digest,
        repository_tree_sha256=bundle.provenance.tree_digest,
        claim_id=bundle.claim.id,
        verdict=bundle.record.verdict.value,
    )
