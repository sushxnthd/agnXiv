from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field

from .attestation import canonical_json_sha256

STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://agnxiv.org/attestation/verification/v1"
PAYLOAD_TYPE = "application/vnd.in-toto+json"


class AttestationSignatureError(ValueError):
    """A verification statement or DSSE signature could not be trusted."""


class DSSESignature(BaseModel):
    keyid: str = ""
    sig: str


class DSSEEnvelope(BaseModel):
    payloadType: str
    payload: str
    signatures: list[DSSESignature] = Field(min_length=1)


def canonical_statement_bytes(statement: dict[str, Any]) -> bytes:
    """Serialize a statement deterministically for signing."""
    return json.dumps(
        statement,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def build_verification_statement(bundle: Any) -> dict[str, Any]:
    """Represent an AgnXiv bundle as an in-toto Statement v1."""
    subjects: list[dict[str, Any]] = [
        {
            "name": "research-repository",
            "digest": {"sha256": bundle.provenance.tree_digest},
        }
    ]

    if bundle.verification_spec_sha256 is not None:
        subjects.append(
            {
                "name": "verification-spec",
                "digest": {"sha256": bundle.verification_spec_sha256},
            }
        )

    if bundle.manuscript is not None:
        subjects.append(
            {
                "name": f"manuscript:{bundle.manuscript.name}",
                "digest": {"sha256": bundle.manuscript.sha256},
            }
        )

    for index, artifact in enumerate(bundle.artifacts):
        subjects.append(
            {
                "name": f"artifact:{index:03d}:{artifact.name}",
                "digest": {"sha256": artifact.sha256},
            }
        )

    execution: dict[str, Any] | None = None
    if bundle.execution is not None:
        execution = {
            "imageId": bundle.execution.image_id,
            "command": bundle.execution.command,
            "stdoutSha256": bundle.execution.stdout_sha256,
            "stderrSha256": bundle.execution.stderr_sha256,
            "sourceUnchanged": bundle.execution.source_unchanged,
            "artifactsUnchanged": bundle.execution.artifacts_unchanged,
            "artifactMounts": bundle.execution.artifact_mounts,
        }

    git = bundle.provenance.git
    source = {
        "treeSha256": bundle.provenance.tree_digest,
        "gitCommit": git.commit if git is not None else None,
        "gitBranch": git.branch if git is not None else None,
        "gitDirty": git.dirty if git is not None else None,
    }

    record = bundle.record
    return {
        "_type": STATEMENT_TYPE,
        "subject": subjects,
        "predicateType": PREDICATE_TYPE,
        "predicate": {
            "schemaVersion": "agnxiv.verification/v1",
            "bundleSha256": canonical_json_sha256(bundle.model_dump(mode="json")),
            "source": source,
            "claim": bundle.claim.model_dump(mode="json"),
            "verificationPolicy": record.policy.model_dump(mode="json"),
            "result": {
                "verdict": record.verdict.value,
                "expected": record.expected,
                "observedMean": record.observed_mean,
                "absoluteError": record.absolute_error,
                "relativeError": record.relative_error,
                "rationale": record.rationale,
                "createdAt": record.created_at.isoformat(),
            },
            "observation": {
                "method": bundle.observation_method,
                "locator": bundle.observation_locator,
            },
            "execution": execution,
        },
    }


def dsse_pre_auth_encoding(payload_type: str, payload: bytes) -> bytes:
    """Return DSSE v1 pre-authentication encoding."""
    type_bytes = payload_type.encode("utf-8")
    return (
        b"DSSEv1 "
        + str(len(type_bytes)).encode("ascii")
        + b" "
        + type_bytes
        + b" "
        + str(len(payload)).encode("ascii")
        + b" "
        + payload
    )


def generate_ed25519_keypair() -> tuple[bytes, bytes, str]:
    """Generate an Ed25519 PEM keypair and stable public-key identifier."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    raw_public = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    key_id = hashlib.sha256(raw_public).hexdigest()
    return private_pem, public_pem, key_id


def _load_ed25519_private_key(private_key_pem: bytes):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = serialization.load_pem_private_key(private_key_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise AttestationSignatureError("private key is not Ed25519")
    return key


def _load_ed25519_public_key(public_key_pem: bytes):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    key = serialization.load_pem_public_key(public_key_pem)
    if not isinstance(key, Ed25519PublicKey):
        raise AttestationSignatureError("public key is not Ed25519")
    return key


def _key_id(public_key: Any) -> str:
    from cryptography.hazmat.primitives import serialization

    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(raw).hexdigest()


def sign_statement_ed25519(
    statement: dict[str, Any],
    private_key_pem: bytes,
) -> DSSEEnvelope:
    """Sign an in-toto statement in a standards-compatible DSSE envelope."""
    private_key = _load_ed25519_private_key(private_key_pem)
    payload = canonical_statement_bytes(statement)
    pae = dsse_pre_auth_encoding(PAYLOAD_TYPE, payload)
    signature = private_key.sign(pae)
    key_id = _key_id(private_key.public_key())

    return DSSEEnvelope(
        payloadType=PAYLOAD_TYPE,
        payload=base64.b64encode(payload).decode("ascii"),
        signatures=[
            DSSESignature(
                keyid=key_id,
                sig=base64.b64encode(signature).decode("ascii"),
            )
        ],
    )


def verify_statement_ed25519(
    envelope: DSSEEnvelope,
    public_key_pem: bytes,
) -> dict[str, Any]:
    """Verify a single-signature AgnXiv DSSE envelope and return its statement."""
    from cryptography.exceptions import InvalidSignature

    if envelope.payloadType != PAYLOAD_TYPE:
        raise AttestationSignatureError("unexpected DSSE payload type")
    if len(envelope.signatures) != 1:
        raise AttestationSignatureError("AgnXiv requires exactly one DSSE signature")

    try:
        payload = base64.b64decode(envelope.payload, validate=True)
        signature = base64.b64decode(envelope.signatures[0].sig, validate=True)
    except ValueError as exc:
        raise AttestationSignatureError("invalid base64 in DSSE envelope") from exc

    public_key = _load_ed25519_public_key(public_key_pem)
    expected_key_id = _key_id(public_key)
    supplied_key_id = envelope.signatures[0].keyid
    if supplied_key_id and supplied_key_id != expected_key_id:
        raise AttestationSignatureError("DSSE key identifier does not match public key")

    pae = dsse_pre_auth_encoding(envelope.payloadType, payload)
    try:
        public_key.verify(signature, pae)
    except InvalidSignature as exc:
        raise AttestationSignatureError("invalid DSSE signature") from exc

    try:
        statement = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise AttestationSignatureError("DSSE payload is not valid JSON") from exc

    if not isinstance(statement, dict):
        raise AttestationSignatureError("DSSE payload is not an in-toto statement")
    if statement.get("_type") != STATEMENT_TYPE:
        raise AttestationSignatureError("unexpected in-toto statement type")
    if statement.get("predicateType") != PREDICATE_TYPE:
        raise AttestationSignatureError("unexpected AgnXiv predicate type")

    return statement
