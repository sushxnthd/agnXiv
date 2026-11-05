#!/usr/bin/env python3
"""Execute the frozen digest-attestation authentication attack matrix."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from verify_authority_registry_checkpoint_artifact_scope import (
    CONSUMER,
    EXECUTION,
    artifact_scope,
    envelopes,
)
from verify_authority_registry_checkpoint_digest_producer import (
    TRUSTED as PRODUCER,
)
from verify_authority_registry_checkpoint_digest_profile import TRUSTED as PROFILE
from verify_authority_registry_checkpoint_history_commitment import (
    FAMILIES,
    attest,
    bundle,
    chain,
    gate,
)

from agnxiv.authority import (
    RegistryCheckpointDigestAttestationScope,
    SignedRegistryCheckpointDigestAttestation,
    registry_checkpoint_digest_attestation_key_sha256,
    registry_checkpoint_digest_attestation_scoped_history_commitment_sha256,
    registry_checkpoint_digest_producer_scoped_history_commitment_sha256,
    registry_checkpoint_digest_profile_scoped_history_commitment_sha256,
    sign_registry_checkpoint_digest_attestation,
)
from agnxiv.models import Verdict

OUT = Path(
    "research/results/authority-registry-checkpoint-digest-attestation-auth.json.gz"
)
SUMMARY = Path(
    "research/results/authority-registry-checkpoint-digest-attestation-auth-summary.json"
)


def key_material(seed):
    private = Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32)
    return (
        private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
        private.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode(),
    )


TRUSTED_PRIVATE, TRUSTED_PUBLIC = key_material(11)
ROGUE_PRIVATE, ROGUE_PUBLIC = key_material(12)
TRUSTED = RegistryCheckpointDigestAttestationScope(
    predicate_type="https://slsa.dev/provenance/v1",
    provenance_statement_sha256="4" * 64,
    attestation_signer_key_sha256=registry_checkpoint_digest_attestation_key_sha256(
        TRUSTED_PUBLIC
    ),
    transparency_inclusion_witness_sha256="6" * 64,
)
REPLAY_SCOPE = TRUSTED.model_copy(update={"provenance_statement_sha256": "7" * 64})
FAMILIES_AUTH = (
    "missing_signature",
    "malformed_signature",
    "untrusted_signer",
    "replayed_scope",
)


def signed_for(family, control):
    if control:
        return sign_registry_checkpoint_digest_attestation(TRUSTED, TRUSTED_PRIVATE)
    if family == "missing_signature":
        return None
    if family == "malformed_signature":
        return SignedRegistryCheckpointDigestAttestation(
            scope=TRUSTED, signature_b64="%%%"
        )
    if family == "untrusted_signer":
        return sign_registry_checkpoint_digest_attestation(TRUSTED, ROGUE_PRIVATE)
    if family == "replayed_scope":
        return sign_registry_checkpoint_digest_attestation(
            REPLAY_SCOPE, TRUSTED_PRIVATE
        )
    raise AssertionError(family)


def run_case(case, family_index, *, control=False):
    family = FAMILIES_AUTH[family_index]
    rows = chain(FAMILIES[family_index], recursive=True, fork=False)
    item = bundle(case)
    attest(item, rows["final"])
    scope = artifact_scope(item)
    consumer, execution, artifact = envelopes(rows["commitment"], scope)
    profile = registry_checkpoint_digest_profile_scoped_history_commitment_sha256(
        artifact, PROFILE
    )
    producer = registry_checkpoint_digest_producer_scoped_history_commitment_sha256(
        profile, PRODUCER
    )
    attestation_commitment = (
        registry_checkpoint_digest_attestation_scoped_history_commitment_sha256(
            producer, TRUSTED
        )
    )
    signed = signed_for(family, control)
    common = {
        "commitment": rows["commitment"],
        "require_commitment": True,
        "consumer_scope": CONSUMER,
        "scoped_commitment": consumer,
        "require_consumer_scope": True,
        "execution_scope": EXECUTION,
        "execution_scoped_commitment": execution,
        "require_execution_scope": True,
        "artifact_scope": scope,
        "artifact_scoped_commitment": artifact,
        "require_artifact_scope": True,
        "digest_profile": PROFILE,
        "digest_profile_scoped_commitment": profile,
        "require_digest_profile": True,
        "producer_scope": PRODUCER,
        "producer_scoped_commitment": producer,
        "require_producer_scope": True,
        "attestation_scope": TRUSTED,
        "attestation_scoped_commitment": attestation_commitment,
        "require_attestation_scope": True,
    }
    parent = gate(item.model_copy(deep=True), rows, **common)
    corrected = gate(
        item.model_copy(deep=True),
        rows,
        **common,
        signed_attestation=signed,
        trusted_attestation_public_key_pem=TRUSTED_PUBLIC,
        require_attestation_authentication=True,
    )
    return {
        "case": case,
        "family": family,
        "control": control,
        "trusted_scope": TRUSTED.model_dump(mode="json"),
        "trusted_public_key_pem": TRUSTED_PUBLIC,
        "rogue_public_key_pem": ROGUE_PUBLIC,
        "signed_attestation": None if signed is None else signed.model_dump(mode="json"),
        "attestation_scoped_definitive": parent.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "authenticated_definitive": corrected.record.verdict != Verdict.UNABLE_TO_VERIFY,
        "authentication_reasons": corrected.verdict_gate_reasons,
    }


def negative_controls():
    rows = chain(FAMILIES[0], recursive=True, fork=False)
    item = bundle(266000)
    attest(item, rows["final"])
    scope = artifact_scope(item)
    consumer, execution, artifact = envelopes(rows["commitment"], scope)
    profile = registry_checkpoint_digest_profile_scoped_history_commitment_sha256(
        artifact, PROFILE
    )
    producer = registry_checkpoint_digest_producer_scoped_history_commitment_sha256(
        profile, PRODUCER
    )
    commitment = registry_checkpoint_digest_attestation_scoped_history_commitment_sha256(
        producer, TRUSTED
    )
    signed = sign_registry_checkpoint_digest_attestation(TRUSTED, TRUSTED_PRIVATE)

    def blocked(**overrides):
        result = gate(
            item.model_copy(deep=True),
            rows,
            commitment=rows["commitment"],
            require_commitment=True,
            consumer_scope=CONSUMER,
            scoped_commitment=consumer,
            require_consumer_scope=True,
            execution_scope=EXECUTION,
            execution_scoped_commitment=execution,
            require_execution_scope=True,
            artifact_scope=scope,
            artifact_scoped_commitment=artifact,
            require_artifact_scope=True,
            digest_profile=PROFILE,
            digest_profile_scoped_commitment=profile,
            require_digest_profile=True,
            producer_scope=PRODUCER,
            producer_scoped_commitment=producer,
            require_producer_scope=True,
            attestation_scope=TRUSTED,
            attestation_scoped_commitment=commitment,
            require_attestation_scope=overrides.get("require_scope", True),
            signed_attestation=overrides.get("signed", signed),
            trusted_attestation_public_key_pem=overrides.get("key", TRUSTED_PUBLIC),
            require_attestation_authentication=True,
        )
        return result.record.verdict == Verdict.UNABLE_TO_VERIFY

    return {
        "missing_signature_blocked": blocked(signed=None),
        "missing_key_blocked": blocked(key=None),
        "without_scope_mode_blocked": blocked(require_scope=False),
        "wrong_trusted_key_blocked": blocked(key=ROGUE_PUBLIC),
    }


def main():
    attacks = [
        run_case(261000 + 100 * family + offset, family)
        for family in range(4)
        for offset in range(32)
    ]
    controls = [
        run_case(265000 + offset, offset % 4, control=True) for offset in range(32)
    ]
    negatives = negative_controls()
    summary = {
        "attack_total": len(attacks),
        "attestation_scoped_false_passes": sum(
            row["attestation_scoped_definitive"] for row in attacks
        ),
        "authenticated_false_passes": sum(
            row["authenticated_definitive"] for row in attacks
        ),
        "control_total": len(controls),
        "authenticated_controls_passed": sum(
            row["authenticated_definitive"] for row in controls
        ),
        "families_blocked": {
            family: sum(
                row["family"] == family and not row["authenticated_definitive"]
                for row in attacks
            )
            for family in FAMILIES_AUTH
        },
        "negative_controls": negatives,
    }
    summary["passed"] = (
        summary["attestation_scoped_false_passes"] == summary["attack_total"] == 128
        and summary["authenticated_false_passes"] == 0
        and summary["authenticated_controls_passed"]
        == summary["control_total"]
        == 32
        and all(value == 32 for value in summary["families_blocked"].values())
        and all(negatives.values())
    )
    report = {
        "schema": "agnxiv.authority-registry-checkpoint-digest-attestation-auth/1",
        "attacks": attacks,
        "controls": controls,
        "summary": summary,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
    with OUT.open("wb") as raw, gzip.GzipFile(
        filename="", mode="wb", fileobj=raw, mtime=0
    ) as compressed:
        compressed.write(encoded)
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    raise SystemExit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()
